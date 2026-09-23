# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Run a pretrained policy on a real robot without recording a dataset.

Spacebar toggles pause/resume. While paused the last commanded pose is held.
Escape stops evaluation.

Example:

```shell
lerobot-evaluate \
    --robot.type=piper_follower \
    --robot.port=can0 \
    --robot.cameras="{ wrist: {type: opencv, index_or_path: 12, width: 640, height: 480, fps: 30}, top: {type: opencv, index_or_path: 8, width: 640, height: 480, fps: 30}}" \
    --display_data=true \
    --task="Pick the toy and place it in the yellow box" \
    --policy.path=/home/acb/RIA_lerobot/outputs/train/smolvla_piper_dataset/checkpoints/030000/pretrained_model
```
"""

import logging
import time
from dataclasses import asdict, dataclass, field
from pprint import pformat
from types import SimpleNamespace
from typing import Any

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.cameras.reachy2_camera.configuration_reachy2_camera import Reachy2CameraConfig  # noqa: F401
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig  # noqa: F401
from lerobot.cameras.zmq.configuration_zmq import ZMQCameraConfig  # noqa: F401
from lerobot.configs import parser
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.pipeline_features import aggregate_pipeline_dataset_features, create_initial_features
from lerobot.datasets.utils import build_dataset_frame, combine_feature_dicts
from lerobot.policies.factory import make_policy, make_pre_post_processors
from lerobot.policies.pretrained import PreTrainedPolicy
from lerobot.policies.utils import make_robot_action
from lerobot.processor import (
    PolicyAction,
    PolicyProcessorPipeline,
    RobotAction,
    RobotObservation,
    RobotProcessorPipeline,
    make_default_processors,
)
from lerobot.robots import (  # noqa: F401
    Robot,
    RobotConfig,
    bi_openarm_follower,
    bi_so_follower,
    earthrover_mini_plus,
    hope_jr,
    koch_follower,
    make_robot_from_config,
    omx_follower,
    openarm_follower,
    reachy2,
    so_follower,
    unitree_g1 as unitree_g1_robot,
)
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.control_utils import is_headless, predict_action
from lerobot.utils.import_utils import register_third_party_plugins
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import get_safe_torch_device, init_logging, log_say
from lerobot.utils.visualization_utils import init_rerun, log_rerun_data


@dataclass
class EvaluateConfig:
    robot: RobotConfig
    policy: PreTrainedConfig | None = None
    # Language instruction passed to VLA policies such as SmolVLA.
    task: str = ""
    fps: int = 30
    # None runs until Escape is pressed.
    duration_s: float | None = None
    display_data: bool = False
    display_ip: str | None = None
    display_port: int | None = None
    display_compressed_images: bool = False
    play_sounds: bool = False
    # Start paused so the scene can be set up before the policy moves the robot.
    start_paused: bool = True
    rename_map: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        policy_path = parser.get_path_arg("policy")
        if not policy_path:
            raise ValueError("Provide a pretrained policy with --policy.path=...")

        cli_overrides = parser.get_cli_overrides("policy")
        self.policy = PreTrainedConfig.from_pretrained(policy_path, cli_overrides=cli_overrides)
        self.policy.pretrained_path = policy_path

        if not self.task:
            raise ValueError("Provide a task instruction with --task=...")

    @classmethod
    def __get_path_fields__(cls) -> list[str]:
        return ["policy"]


def init_evaluate_keyboard_listener(start_paused: bool):
    """Listen for Space (pause/resume) and Escape (quit) without blocking the control loop."""
    events = {
        "paused": start_paused,
        "stop": False,
        "_space_held": False,
    }
    listener = None

    if is_headless():
        logging.warning(
            "Headless environment detected. Keyboard pause/resume is unavailable. "
            "Use Ctrl+C to stop evaluation."
        )
        return listener, events

    from pynput import keyboard

    def _log_pause_state():
        if events["paused"]:
            print("Paused. Press SPACE to resume the policy, ESC to quit.")
        else:
            print("Running. Press SPACE to pause, ESC to quit.")

    def on_press(key):
        try:
            if key == keyboard.Key.space:
                if events["_space_held"]:
                    return
                events["_space_held"] = True
                events["paused"] = not events["paused"]
                _log_pause_state()
            elif key == keyboard.Key.esc:
                print("Escape pressed. Stopping evaluation...")
                events["stop"] = True
        except Exception as e:
            print(f"Error handling key press: {e}")

    def on_release(key):
        if key == keyboard.Key.space:
            events["_space_held"] = False

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    _log_pause_state()
    return listener, events


def _hold_action_from_observation(obs: RobotObservation, action_names: list[str]) -> RobotAction:
    missing = [name for name in action_names if name not in obs]
    if missing:
        raise KeyError(f"Cannot hold pose; observation is missing action keys: {missing}")
    return {name: float(obs[name]) for name in action_names}


def evaluate_loop(
    robot: Robot,
    events: dict,
    fps: int,
    dataset_features: dict[str, dict],
    robot_action_processor: RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction],
    robot_observation_processor: RobotProcessorPipeline[RobotObservation, RobotObservation],
    policy: PreTrainedPolicy,
    preprocessor: PolicyProcessorPipeline[dict[str, Any], dict[str, Any]],
    postprocessor: PolicyProcessorPipeline[PolicyAction, PolicyAction],
    task: str,
    duration_s: float | None = None,
    display_data: bool = False,
    display_compressed_images: bool = False,
):
    action_names = list(dataset_features[ACTION]["names"])
    last_robot_action: RobotAction | None = None
    was_paused = events["paused"]
    start_t = time.perf_counter()

    policy.reset()
    preprocessor.reset()
    postprocessor.reset()

    while not events["stop"]:
        loop_start = time.perf_counter()
        paused = events["paused"]

        if was_paused and not paused:
            policy.reset()
            preprocessor.reset()
            postprocessor.reset()
            logging.info("Policy resumed; action queue reset.")
        was_paused = paused

        obs = robot.get_observation()
        obs_processed = robot_observation_processor(obs)

        if paused:
            hold_action = last_robot_action or _hold_action_from_observation(obs_processed, action_names)
            robot_action_to_send = robot_action_processor((hold_action, obs))
            action_values = hold_action
        else:
            observation_frame = build_dataset_frame(dataset_features, obs_processed, prefix=OBS_STR)
            action_values = predict_action(
                observation=observation_frame,
                policy=policy,
                device=get_safe_torch_device(policy.config.device),
                preprocessor=preprocessor,
                postprocessor=postprocessor,
                use_amp=policy.config.use_amp,
                task=task,
                robot_type=robot.robot_type,
            )
            act_processed_policy = make_robot_action(action_values, dataset_features)
            robot_action_to_send = robot_action_processor((act_processed_policy, obs))
            action_values = act_processed_policy

        last_robot_action = robot.send_action(robot_action_to_send)

        if display_data:
            log_rerun_data(
                observation=obs_processed,
                action=action_values,
                compress_images=display_compressed_images,
            )

        dt_s = time.perf_counter() - loop_start
        sleep_time_s = 1 / fps - dt_s
        if sleep_time_s < 0 and not paused:
            logging.warning(
                f"Evaluate loop is running slower ({1 / dt_s:.1f} Hz) than the target FPS ({fps} Hz)."
            )
        precise_sleep(max(sleep_time_s, 0.0))

        if duration_s is not None and time.perf_counter() - start_t >= duration_s:
            logging.info("Reached duration_s=%.1f, stopping evaluation.", duration_s)
            break


@parser.wrap()
def evaluate(cfg: EvaluateConfig) -> None:
    init_logging()
    logging.info(pformat(asdict(cfg)))

    if cfg.display_data:
        init_rerun(session_name="evaluate", ip=cfg.display_ip, port=cfg.display_port)
    display_compressed_images = (
        True
        if (cfg.display_data and cfg.display_ip is not None and cfg.display_port is not None)
        else cfg.display_compressed_images
    )

    robot = make_robot_from_config(cfg.robot)
    _, robot_action_processor, robot_observation_processor = make_default_processors()

    dataset_features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=robot_action_processor,
            initial_features=create_initial_features(action=robot.action_features),
            use_videos=True,
        ),
        aggregate_pipeline_dataset_features(
            pipeline=robot_observation_processor,
            initial_features=create_initial_features(observation=robot.observation_features),
            use_videos=True,
        ),
    )
    ds_meta = SimpleNamespace(features=dataset_features, stats=None)

    policy = make_policy(cfg.policy, ds_meta=ds_meta)
    policy.eval()
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=cfg.policy,
        pretrained_path=cfg.policy.pretrained_path,
        preprocessor_overrides={
            "device_processor": {"device": str(policy.config.device)},
            "rename_observations_processor": {"rename_map": cfg.rename_map},
        },
    )

    listener = None
    try:
        robot.connect()
        listener, events = init_evaluate_keyboard_listener(cfg.start_paused)
        log_say(
            "Evaluation ready. Space pauses or resumes the policy. Escape quits.",
            cfg.play_sounds,
        )
        evaluate_loop(
            robot=robot,
            events=events,
            fps=cfg.fps,
            dataset_features=dataset_features,
            robot_action_processor=robot_action_processor,
            robot_observation_processor=robot_observation_processor,
            policy=policy,
            preprocessor=preprocessor,
            postprocessor=postprocessor,
            task=cfg.task,
            duration_s=cfg.duration_s,
            display_data=cfg.display_data,
            display_compressed_images=display_compressed_images,
        )
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, stopping evaluation.")
    finally:
        log_say("Stop evaluation", cfg.play_sounds, blocking=True)
        if robot.is_connected:
            robot.disconnect()
        if not is_headless() and listener:
            listener.stop()
        log_say("Exiting", cfg.play_sounds)


def main():
    register_third_party_plugins()
    evaluate()


if __name__ == "__main__":
    main()
