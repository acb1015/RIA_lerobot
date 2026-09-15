from dataclasses import dataclass,field

from lerobot.cameras import CameraConfig

from ...config import RobotConfig

@RobotConfig.register_subclass("piper_follower")
@dataclass
class PiperFollowerConfig(RobotConfig):
    port: str
    cameras: dict[str, CameraConfig] = field(default_factory=dict)