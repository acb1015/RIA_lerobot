from dataclasses import dataclass

from lerobot.teleoperators.config import TeleoperatorConfig

@TeleoperatorConfig.register_subclass("piper_leader")
@dataclass
class PiperLeaderConfig(TeleoperatorConfig):
    port: str # learder arm can 번호