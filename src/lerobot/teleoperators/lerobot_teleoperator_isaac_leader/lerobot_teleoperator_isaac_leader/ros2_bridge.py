"""ROS 2 client used by the Isaac leader: joint_states only."""

from __future__ import annotations

import logging
import threading
from typing import Any

from .topics import JOINT_NAMES, JOINT_STATE_TIMEOUT_S, JOINT_STATE_TOPIC, NODE_NAME, RESET_TOPIC

logger = logging.getLogger(__name__)

_JOINT_COUNT = len(JOINT_NAMES)


def _require_rclpy() -> Any:
    try:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import JointState
    except ImportError as exc:
        raise ImportError(
            "ROS 2 Python packages (rclpy, sensor_msgs) are required. "
            "Source your ROS 2 workspace first, e.g. `source /opt/ros/humble/setup.bash`."
        ) from exc
    return (
        rclpy,
        SingleThreadedExecutor,
        QoSProfile,
        DurabilityPolicy,
        HistoryPolicy,
        ReliabilityPolicy,
        JointState,
    )


class _JointCache:
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


class IsaacLeaderRos2Bridge:
    """Subscribe to the Isaac leader JointState topic."""

    def __init__(self) -> None:
        self._node: Any = None
        self._executor: Any = None
        self._spin_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._joints_ready = threading.Event()
        self._joint_cache = _JointCache()
        self._latest_joints: dict[str, float] = dict.fromkeys(JOINT_NAMES, 0.0)
        self._connected = False
        self._reset_event = threading.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        (
            rclpy,
            SingleThreadedExecutor,
            QoSProfile,
            DurabilityPolicy,
            HistoryPolicy,
            ReliabilityPolicy,
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
        reset_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._node = rclpy.create_node(NODE_NAME)
        self._node.create_subscription(JointState, JOINT_STATE_TOPIC, self._on_joint_state, sensor_qos)
        self._node.create_subscription(Empty, RESET_TOPIC, self._on_reset, reset_qos)

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, name=NODE_NAME, daemon=True)
        self._spin_thread.start()
        self._connected = True

        if JOINT_STATE_TIMEOUT_S > 0 and not self._joints_ready.wait(timeout=JOINT_STATE_TIMEOUT_S):
            logger.warning(
                "No JointState received on %s within %.1fs. Actions will be zeros until a message arrives.",
                JOINT_STATE_TOPIC,
                JOINT_STATE_TIMEOUT_S,
            )
        logger.info("Isaac leader ROS 2 connected (joint_states=%s)", JOINT_STATE_TOPIC)

    def get_joint_positions(self) -> dict[str, float]:
        with self._lock:
            return dict(self._latest_joints)

    def consume_reset(self) -> bool:
        if not self._reset_event.is_set():
            return False
        self._reset_event.clear()
        return True

    def disconnect(self) -> None:
        self._connected = False
        executor, node, thread = self._executor, self._node, self._spin_thread
        self._executor = None
        self._node = None
        self._spin_thread = None
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
        logger.info("Isaac leader received environment reset on %s", RESET_TOPIC)
