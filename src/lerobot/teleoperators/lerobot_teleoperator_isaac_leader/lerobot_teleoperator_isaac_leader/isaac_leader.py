from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

from lerobot.processor import RobotAction
from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .config_isaac_leader import IsaacLeaderConfig
from .ros2_bridge import IsaacLeaderRos2Bridge
from .topics import JOINT_NAMES

logger = logging.getLogger(__name__)


class IsaacLeader(Teleoperator):
    """Leader arm whose joint angles come from a ROS 2 JointState topic."""

    config_class = IsaacLeaderConfig
    name = "isaac_leader"

    def __init__(self, config: IsaacLeaderConfig):
        super().__init__(config)
        self.config = config
        self._bridge = IsaacLeaderRos2Bridge()

    @cached_property
    def action_features(self) -> dict[str, type]:
        return dict.fromkeys(JOINT_NAMES, float)

    @cached_property
    def feedback_features(self) -> dict[str, type]:
        return {}

    @property
    def is_connected(self) -> bool:
        return self._bridge.is_connected

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        self._bridge.connect()
        if not self.is_calibrated and calibrate:
            self.calibrate()
        self.configure()
        logger.info("%s connected.", self)

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        logger.info("Isaac leader: no manual calibration needed.")

    def configure(self) -> None:
        pass

    @check_if_not_connected
    def get_action(self) -> RobotAction:
        if self._bridge.consume_reset():
            logger.info("Isaac leader environment was reset.")
        return self._bridge.get_joint_positions()

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        pass

    @check_if_not_connected
    def disconnect(self) -> None:
        self._bridge.disconnect()
        logger.info("%s disconnected.", self)
