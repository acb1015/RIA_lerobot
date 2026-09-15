from dataclasses import dataclass

from lerobot.robots.config import RobotConfig


@RobotConfig.register_subclass("isaac_follower")
@dataclass
class IsaacFollowerConfig(RobotConfig):
    """Isaac Sim follower arm. Topic paths live in `topics.py`."""
