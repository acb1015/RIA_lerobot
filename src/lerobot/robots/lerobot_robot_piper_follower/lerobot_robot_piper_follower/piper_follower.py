import logging
import time
from functools import cached_property

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.processor import RobotAction, RobotObservation
from lerobot.robots.robot import Robot
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .config_piper_follower import PiperFollowerConfig

from piper_sdk import *
from piper_sdk.interface.piper_interface_v2 import C_PiperInterface_V2

logger = logging.getLogger(__name__)

class PiperFollower(Robot):
    config_class = PiperFollowerConfig
    name = "piper_follower"

    def __init__(self, config: PiperFollowerConfig):
        super().__init__(config)
        self.config = config
        self.piper = C_PiperInterface_V2(config.port)
        self.enable()
        self.factor = 1
        self.cameras = make_cameras_from_configs(config.cameras)
        self._is_connected = False

    
    def enable(self):
        """
        로봇팔을 활성화하고, 모터가 준비될 때까지 대기하는 함수입니다.
        """
        enable_flag = False  # 팔이 활성화되었는지 확인하는 플래그
        elapsed_time_flag = False  # 시간 초과 여부를 체크하는 플래그
        timeout = 5
        start_time = time.time()  # 시작 시간 기록
        
        while not enable_flag:  # 팔이 활성화 될 때까지 반복
            elapsed_time = time.time() - start_time  # 경과 시간 계산
            enable_flag = all(  # 모든 모터가 활성화되었는지 확인
                getattr(self.piper.GetArmLowSpdInfoMsgs(), f"motor_{i}").foc_status.driver_enable_status 
                for i in range(1, 7)
            )
            self.piper.EnableArm(7)  # 로봇 팔 활성화
            self.piper.GripperCtrl(0, 1000, 0x01, 0)  # 그리퍼 활성화 (초기 상태)

            if elapsed_time > timeout:  # 타임아웃 시간 초과 시
                print("시간초과")
                elapsed_time_flag = True  # 시간 초과 플래그 설정
                enable_flag = True  # 루프 종료
                break
            time.sleep(1)

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }

    @cached_property
    def observation_features(self) -> dict[str,type]:
        return {
            "joint_1": float,
            "joint_2": float,
            "joint_3": float,
            "joint_4": float,
            "joint_5": float,
            "joint_6": float,
            "gripper": float,
            **self._cameras_ft
        }
    
    @cached_property
    def action_features(self) -> dict[str, type]:
        return {
            "joint_1": float,
            "joint_2": float,
            "joint_3": float,
            "joint_4": float,
            "joint_5": float,
            "joint_6": float,
            "gripper": float,
        }
    
    def connect(self, calibrate: bool = True) -> None:
        self.piper.ConnectPort()
        time.sleep(0.025)
        self._is_connected = True # 연결 확인 시 true로 변경
        
        for cam_key, cam in self.cameras.items():
            cam.connect()
            logger.info("Connected camera %s (%s)", cam_key, cam)
            time.sleep(0.2)

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        joint_msg = self.piper.GetArmJointMsgs()
        gripper_msg = self.piper.GetArmGripperMsgs()
        
        obs_dict = {
            "joint_1": float(joint_msg.joint_state.joint_1),
            "joint_2": float(joint_msg.joint_state.joint_2),
            "joint_3": float(joint_msg.joint_state.joint_3),
            "joint_4": float(joint_msg.joint_state.joint_4),
            "joint_5": float(joint_msg.joint_state.joint_5),
            "joint_6": float(joint_msg.joint_state.joint_6),
            "gripper": float(gripper_msg.gripper_state.grippers_angle),
        }
        
        for cam_key, cam in self.cameras.items():
            obs_dict[cam_key] = cam.read_latest(max_age_ms=1000)
        
        return obs_dict

    
    def convert(self):
        """
        현재 로봇팔의 위치(mm, deg)와 그리퍼 값(mm)을 변환하여 반환합니다.
        """
        return [round(pose * self.factor) for pose in self.position[:6]] + [round(self.position[6] * self.factor)]
    
    @check_if_not_connected
    def send_action(self, action: RobotAction) -> RobotAction:
        self.position = [
            action["joint_1"],
            action["joint_2"],
            action["joint_3"],
            action["joint_4"],
            action["joint_5"],
            action["joint_6"],
            action["gripper"]
        ]
        
        # 변환
        converted_values = self.convert()
        joint_values = converted_values[:6]
        gripper_value = converted_values[6]
                
        # SDK 명령
        self.piper.MotionCtrl_2(0x01, 0x01, 50, 0x00)
        self.piper.JointCtrl(*joint_values)
        self.piper.GripperCtrl(abs(gripper_value), 1000, 0x01, 0)
        
        return action

    @check_if_not_connected
    def disconnect(self) -> None:
        self.piper.DisconnectPort()
        self._is_connected = False # 연결 해제 시 False로 변경
        
        # 카메라 연결 해제
        for cam in self.cameras.values():
            cam.disconnect()

    def configure(self):
        """
        로봇과의 통신을 설정합니다.
        LeRobot 시스템이 시작될 때 호출됩니다.
        """
        print("Configuring Piper Follower...")
        pass

    @property
    def is_connected(self) -> bool:
        """
        로봇이 현재 연결되어 있는지 확인합니다.
        """
        return self._is_connected

    def calibrate(self):
        """
        캘리브레이션을 수행합니다.
        Piper는 자체 엔코더를 사용하므로 패스합니다.
        """
        print("Piper Follower: No manual calibration needed.")

    @property
    def is_calibrated(self) -> bool:
        """
        캘리브레이션 완료 여부를 반환합니다.
        """
        return True


    

