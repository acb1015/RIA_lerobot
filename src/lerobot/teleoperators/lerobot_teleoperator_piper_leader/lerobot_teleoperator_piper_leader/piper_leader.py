import logging
import time

from ...teleoperator import Teleoperator
from piper_sdk import *
from piper_sdk.interface.piper_interface_v2 import C_PiperInterface_V2
from .config_piper_leader import PiperLeaderConfig
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected


logger = logging.getLogger(__name__)

class PiperLeader(Teleoperator):
    config_class = PiperLeaderConfig
    name = 'piper_leader'

    def __init__(self, config:PiperLeaderConfig):
        super().__init__(config)
        self.piper = C_PiperInterface_V2(config.port)
        self.factor = 1000
        self.position = [0, 0, 0, 0, 0, 0, 0]
        self.gripper = 0
        self._is_connected = False
        

    @property
    def action_features(self) -> dict[str,type]:
        return {
            "joint_1": float,
            "joint_2": float,
            "joint_3": float,
            "joint_4": float,
            "joint_5": float,
            "joint_6": float,
            "gripper": float,
        }
        
    @property
    def feedback_features(self) -> dict[str,type]:
        return {}
    
    @check_if_not_connected
    def get_action(self) -> dict[str,float]:
        self.joint = self.piper.GetArmJointMsgs()
        self.gripper = self.piper.GetArmGripperMsgs()
        self.joint_state = self.joint.joint_state
        self.gripper_state = self.gripper.gripper_state

        # leader arm의 joint state를 전송
        action = {
        "joint_1": float(self.joint_state.joint_1),
        "joint_2": float(self.joint_state.joint_2),
        "joint_3": float(self.joint_state.joint_3),
        "joint_4": float(self.joint_state.joint_4),
        "joint_5": float(self.joint_state.joint_5),
        "joint_6": float(self.joint_state.joint_6),
        "gripper": float(self.gripper_state.grippers_angle),
        }
        return action
    
    def send_feedback(self) -> None:
        pass  

    @check_if_already_connected  
    def connect(self) -> None:
        self.piper.ConnectPort()
        time.sleep(0.025)
        self._is_connected = True 

    @check_if_not_connected
    def disconnect(self) -> None:
        self.piper.DisconnectPort()
        self._is_connected = False
    
    def configure(self):
        print("Configuring Piper Leader...")
        pass

    @property
    def is_connected(self) -> bool:
        return self._is_connected 

    def calibrate(self):
        """
        캘리브레이션을 수행합니다.
        Piper는 자체 엔코더를 사용하므로 별도 캘리브레이션 과정이 필요 없다면 pass 합니다.
        """
        print("Piper Leader: No manual calibration needed.")
        pass

    def is_calibrated(self) -> bool:
        """
        캘리브레이션 완료 여부를 반환합니다.
        """
        return True


