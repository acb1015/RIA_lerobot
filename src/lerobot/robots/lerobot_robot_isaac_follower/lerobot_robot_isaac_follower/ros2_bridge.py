"""ROS 2 client used by the Isaac follower: joint_states, cameras, joint_command."""

from __future__ import annotations

import logging
import os
import threading
from functools import partial
from typing import Any

import numpy as np

from .topics import (
    CAMERA_SHAPES,
    CAMERA_TOPICS,
    EPISODE_END_TOPIC,
    EPISODE_START_TOPIC,
    JOINT_COMMAND_TOPIC,
    JOINT_NAMES,
    JOINT_STATE_TIMEOUT_S,
    JOINT_STATE_TOPIC,
    NODE_NAME,
    RESET_ACK_TOPIC,
    RESET_REQUEST_TOPIC,
    RESET_TOPIC,
)

logger = logging.getLogger(__name__)

_JOINT_COUNT = len(JOINT_NAMES)
_CHANNELS = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4, "mono8": 1}
_CVT_COLOR = None  # lazy-filled with cv2 COLOR_* codes


def _require_rclpy() -> Any:
    try:
        import rclpy
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import Image, JointState
    except ImportError as exc:
        raise ImportError(
            "ROS 2 Python packages (rclpy, sensor_msgs) are required. "
            "Source your ROS 2 workspace first, e.g. `source /opt/ros/humble/setup.bash`."
        ) from exc
    return (
        rclpy,
        MultiThreadedExecutor,
        QoSProfile,
        DurabilityPolicy,
        HistoryPolicy,
        ReliabilityPolicy,
        Image,
        JointState,
    )


def _cvt_codes() -> dict[str, int]:
    global _CVT_COLOR
    if _CVT_COLOR is None:
        import cv2

        _CVT_COLOR = {
            "bgr8": cv2.COLOR_BGR2RGB,
            "rgba8": cv2.COLOR_RGBA2RGB,
            "bgra8": cv2.COLOR_BGRA2RGB,
            "mono8": cv2.COLOR_GRAY2RGB,
        }
    return _CVT_COLOR


def _image_view(msg: Any, channels: int) -> np.ndarray:
    """Zero-copy view over the ROS Image buffer. Caller must copy before the callback returns."""
    height, width, step = msg.height, msg.width, msg.step
    if step == width * channels:
        return np.frombuffer(msg.data, dtype=np.uint8, count=height * step).reshape(height, width, channels)
    return np.ndarray(
        (height, width, channels),
        dtype=np.uint8,
        buffer=msg.data,
        strides=(step, channels, 1),
    )


def image_msg_to_hwc_rgb(msg: Any, target_hw: tuple[int, int] | None = None) -> np.ndarray:
    """Decode sensor_msgs/Image into a newly owned HxWx3 uint8 RGB array (one copy)."""
    encoding = msg.encoding
    channels = _CHANNELS.get(encoding)
    if channels is None:
        encoding = encoding.lower()
        channels = _CHANNELS.get(encoding)
        if channels is None:
            raise ValueError(f"Unsupported image encoding '{msg.encoding}' on ROS 2 camera topic.")

    src = _image_view(msg, channels)
    if encoding == "rgb8":
        rgb = src.copy()
    else:
        import cv2

        rgb = cv2.cvtColor(src, _cvt_codes()[encoding])

    if target_hw is not None and (rgb.shape[0], rgb.shape[1]) != target_hw:
        import cv2

        rgb = cv2.resize(rgb, (target_hw[1], target_hw[0]), interpolation=cv2.INTER_AREA)
    return rgb


class _JointCache:
    """Map JointState messages onto JOINT_NAMES with a cached name→index table."""

    __slots__ = ("_index", "_names_key")

    def __init__(self) -> None:
        self._index: list[int] | None = None
        self._names_key: tuple[str, ...] | None = None

    def update(self, msg: Any) -> list[float]:
        names = msg.name
        positions = msg.position
        n = len(positions)
        if not names:
            return [float(positions[i]) if i < n else 0.0 for i in range(_JOINT_COUNT)]

        names_key = tuple(names)
        if names_key != self._names_key:
            lookup = {name: i for i, name in enumerate(names)}
            self._index = [lookup.get(name, -1) for name in JOINT_NAMES]
            self._names_key = names_key

        return [float(positions[j]) if 0 <= j < n else 0.0 for j in self._index]  # type: ignore[union-attr]


class IsaacFollowerRos2Bridge:
    """Subscribe to Isaac joint/camera topics and publish joint commands."""

    def __init__(self) -> None:
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._joints_ready = threading.Event()
        self._joint_cache = _JointCache()
        self._latest_joints: dict[str, float] = dict.fromkeys(JOINT_NAMES, 0.0)
        self._latest_images: dict[str, np.ndarray] = {
            cam: np.zeros(CAMERA_SHAPES.get(cam, (480, 640, 3)), dtype=np.uint8) for cam in CAMERA_TOPICS
        }
        self._target_hw = {
            cam: (shape[0], shape[1]) for cam, shape in CAMERA_SHAPES.items() if cam in CAMERA_TOPICS
        }
        self._image_errors: set[str] = set()
        self._joint_pub: Any = None
        self._cmd_msg: Any = None
        self._cmd_position = [0.0] * _JOINT_COUNT
        self._clock: Any = None
        self._connected = False
        self._reset_event = threading.Event()
        self._episode_end_event = threading.Event()
        self._reset_ack_pub: Any = None
        self._reset_req_pub: Any = None
        self._episode_start_pub: Any = None
        self._record_events: dict[str, bool] | None = None
        self._collect = os.environ.get("ISAAC_COLLECT") == "1"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        (
            rclpy,
            MultiThreadedExecutor,
            QoSProfile,
            DurabilityPolicy,
            HistoryPolicy,
            ReliabilityPolicy,
            Image,
            JointState,
        ) = _require_rclpy()
        from std_msgs.msg import Empty

        if not rclpy.ok():
            rclpy.init()

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.VOLATILE,
        )
        command_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._node = rclpy.create_node(NODE_NAME)
        self._clock = self._node.get_clock()
        self._node.create_subscription(JointState, JOINT_STATE_TOPIC, self._on_joint_state, sensor_qos)
        for cam_key, topic in CAMERA_TOPICS.items():
            self._node.create_subscription(
                Image, topic, partial(self._on_image, cam_key), sensor_qos
            )

        self._cmd_msg = JointState()
        self._cmd_msg.name = list(JOINT_NAMES)
        self._joint_pub = self._node.create_publisher(JointState, JOINT_COMMAND_TOPIC, command_qos)
        self._reset_ack_pub = self._node.create_publisher(Empty, RESET_ACK_TOPIC, command_qos)
        self._reset_req_pub = self._node.create_publisher(Empty, RESET_REQUEST_TOPIC, command_qos)
        self._node.create_subscription(Empty, RESET_TOPIC, self._on_reset, command_qos)
        if self._collect:
            self._episode_start_pub = self._node.create_publisher(Empty, EPISODE_START_TOPIC, command_qos)
            self._node.create_subscription(Empty, EPISODE_END_TOPIC, self._on_episode_end, command_qos)

        n_threads = max(2, 1 + len(CAMERA_TOPICS))
        self._executor = MultiThreadedExecutor(num_threads=n_threads)
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, name=NODE_NAME, daemon=True)
        self._spin_thread.start()
        self._connected = True

        if JOINT_STATE_TIMEOUT_S > 0 and not self._joints_ready.wait(timeout=JOINT_STATE_TIMEOUT_S):
            logger.warning(
                "No JointState received on %s within %.1fs. Observation joints will be zeros until a message arrives.",
                JOINT_STATE_TOPIC,
                JOINT_STATE_TIMEOUT_S,
            )
        logger.info(
            "Isaac follower ROS 2 connected (joint_states=%s, joint_command=%s, cameras=%s)",
            JOINT_STATE_TOPIC,
            JOINT_COMMAND_TOPIC,
            list(CAMERA_TOPICS.values()),
        )

    def get_observation(self) -> dict[str, Any]:
        """Snapshot joints + latest camera frames. Frames are already owned copies from the callback."""
        with self._lock:
            obs: dict[str, Any] = dict(self._latest_joints)
            obs.update(self._latest_images)
            return obs

    def get_joint_positions(self) -> dict[str, float]:
        with self._lock:
            return dict(self._latest_joints)

    def send_joint_positions(self, action: dict[str, float]) -> None:
        pub, msg, clock = self._joint_pub, self._cmd_msg, self._clock
        if pub is None or msg is None or clock is None:
            return
        pos = self._cmd_position
        for i, name in enumerate(JOINT_NAMES):
            pos[i] = action[name]
        msg.header.stamp = clock.now().to_msg()
        msg.position = pos
        pub.publish(msg)

    def bind_record_events(self, events: dict[str, bool]) -> None:
        self._record_events = events

    def signal_exit_early(self) -> None:
        events = self._record_events
        if events is not None:
            events["exit_early"] = True

    def consume_episode_end(self) -> bool:
        if not self._episode_end_event.is_set():
            return False
        self._episode_end_event.clear()
        return True

    def consume_reset(self) -> bool:
        if not self._reset_event.is_set():
            return False
        self._reset_event.clear()
        return True

    def publish_episode_start(self) -> None:
        pub = self._episode_start_pub
        if pub is None:
            return
        from std_msgs.msg import Empty

        pub.publish(Empty())
        logger.info("Isaac follower started the next episode on %s", EPISODE_START_TOPIC)

    def request_environment_reset(self) -> None:
        pub = self._reset_req_pub
        if pub is None:
            return
        from std_msgs.msg import Empty

        pub.publish(Empty())

    def disconnect(self) -> None:
        self._connected = False
        executor, node, thread = self._executor, self._node, self._spin_thread
        self._executor = None
        self._node = None
        self._spin_thread = None
        self._joint_pub = None
        self._cmd_msg = None
        self._clock = None
        self._reset_ack_pub = None
        self._reset_req_pub = None
        self._episode_start_pub = None
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _on_joint_state(self, msg: Any) -> None:
        values = self._joint_cache.update(msg)
        joints = dict(zip(JOINT_NAMES, values, strict=True))
        with self._lock:
            self._latest_joints = joints
        self._joints_ready.set()

    def _on_reset(self, _msg: Any) -> None:
        self._reset_event.set()
        self.signal_exit_early()
        ack = self._reset_ack_pub
        if ack is not None:
            from std_msgs.msg import Empty

            ack.publish(Empty())
        logger.info("Isaac follower received environment reset on %s", RESET_TOPIC)

    def _on_episode_end(self, _msg: Any) -> None:
        self._episode_end_event.set()
        self.signal_exit_early()
        logger.info("Isaac follower received episode end on %s", EPISODE_END_TOPIC)

    def _on_image(self, cam_key: str, msg: Any) -> None:
        try:
            image = image_msg_to_hwc_rgb(msg, self._target_hw.get(cam_key))
        except ValueError:
            if cam_key not in self._image_errors:
                self._image_errors.add(cam_key)
                logger.exception("Failed to convert camera '%s' image", cam_key)
            return
        with self._lock:
            self._latest_images[cam_key] = image
