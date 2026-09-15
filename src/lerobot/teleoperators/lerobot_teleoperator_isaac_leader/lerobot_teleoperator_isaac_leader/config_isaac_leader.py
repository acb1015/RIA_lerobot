from dataclasses import dataclass

from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("isaac_leader")
@dataclass
class IsaacLeaderConfig(TeleoperatorConfig):
    """Isaac Sim leader arm. Topic paths live in `topics.py`."""
