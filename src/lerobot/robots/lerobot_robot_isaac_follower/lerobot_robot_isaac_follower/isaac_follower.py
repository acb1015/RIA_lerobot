import logging
from functools import cached_property

from lerobot.processor import RobotAction, RobotObservation
from lerobot.robots.robot import Robot
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .config_isaac_follower import IsaacFollowerConfig
from .ros2_bridge import IsaacFollowerRos2Bridge
from .topics import CAMERA_SHAPES, CAMERA_TOPICS, JOINT_NAMES

logger = logging.getLogger(__name__)

_DEFAULT_CAMERA_SHAPE = (480, 640, 3)


class IsaacFollower(Robot):
    """Follower arm whose cameras and joint angles come from ROS 2 topics."""

    config_class = IsaacFollowerConfig
    name = "isaac_follower"

    def __init__(self, config: IsaacFollowerConfig):
        super().__init__(config)
        self.config = config
        self._bridge = IsaacFollowerRos2Bridge()
        self._command = dict.fromkeys(JOINT_NAMES, 0.0)
        self._command_seeded = False
        self._collect_mode = "record"
        # LeRobot 0.4.4 record() calls len(robot.cameras) before connect().
        # Frames still come from ROS 2; this is only the camera name set.
        self.cameras = dict(CAMERA_TOPICS)

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        cameras = {cam: CAMERA_SHAPES.get(cam, _DEFAULT_CAMERA_SHAPE) for cam in CAMERA_TOPICS}
        return dict.fromkeys(JOINT_NAMES, float) | cameras

    @cached_property
    def action_features(self) -> dict[str, type]:
        return dict.fromkeys(JOINT_NAMES, float)

    @property
    def is_connected(self) -> bool:
        return self._bridge.is_connected

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        self._patch_record_keyboard()
        self._bridge.connect()
        if not self.is_calibrated and calibrate:
            self.calibrate()
        self.configure()
        logger.info("%s connected.", self)

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        logger.info("Isaac follower: no manual calibration needed.")

    def configure(self) -> None:
        pass

    def _patch_record_keyboard(self) -> None:
        try:
            import lerobot.scripts.lerobot_record as record_mod
        except ImportError:
            return
        orig = getattr(record_mod, "init_keyboard_listener", None)
        if orig is None or getattr(orig, "_isaac_patched", False):
            return
        bridge = self._bridge

        def wrapped(*args, **kwargs):
            listener, events = orig(*args, **kwargs)
            bridge.bind_record_events(events)
            return listener, events

        wrapped._isaac_patched = True
        record_mod.init_keyboard_listener = wrapped

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        if self._bridge.consume_episode_end():
            self._collect_mode = "reset"
        reset = self._bridge.consume_reset()
        if reset:
            self._command_seeded = False
            current = self._bridge.get_joint_positions()
            self._command = dict(current)
            self._collect_mode = "armed"
            logger.info("Isaac follower reseeded joint command after environment reset.")
            return self._bridge.get_observation()
        if self._collect_mode == "armed":
            self._bridge.publish_episode_start()
            self._collect_mode = "record"
        return self._bridge.get_observation()

    @check_if_not_connected
    def send_action(self, action: RobotAction) -> RobotAction:
        sent = self._command
        missing = False
        for name in JOINT_NAMES:
            value = action.get(name)
            if value is None:
                missing = True
            else:
                sent[name] = float(value)
        if missing and not self._command_seeded:
            current = self._bridge.get_joint_positions()
            for name in JOINT_NAMES:
                if name not in action:
                    sent[name] = current[name]
        self._command_seeded = True
        self._bridge.send_joint_positions(sent)
        return dict(sent)

    @check_if_not_connected
    def disconnect(self) -> None:
        self._bridge.disconnect()
        logger.info("%s disconnected.", self)
