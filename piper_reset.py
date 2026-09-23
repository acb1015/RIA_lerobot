#!/usr/bin/env python3
# -*-coding:utf8-*-

import re
import sys
import time

from piper_sdk import *
from piper_sdk.interface.piper_interface_v2 import C_PiperInterface_V2


def parse_can_name(default: str = "can0") -> str:
    """`--can1`, `--can=can1`, `--can can1` 형태로 CAN 인터페이스 이름을 읽습니다."""
    can_name = default
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        numbered = re.fullmatch(r"--can(\d+)", arg)
        if numbered:
            can_name = f"can{numbered.group(1)}"
        elif arg == "--can" and i + 1 < len(args):
            can_name = args[i + 1]
            i += 1
        elif arg.startswith("--can="):
            can_name = arg.split("=", 1)[1]
        else:
            raise SystemExit(f"알 수 없는 인자입니다: {arg}\n예: python piper_reset.py --can1")
        if not re.fullmatch(r"can\d+", can_name):
            raise SystemExit(f"CAN 이름은 can0, can1 형식이어야 합니다. 받은 값: {can_name}")
        i += 1
    return can_name

class Move_J:
    def __init__(self, piper: C_PiperInterface_V2):
        self.piper = piper  # piper 인터페이스 객체 초기화
        self.factor = 1000  # 0.001 도를 기준으로 int값을 넘겨주기 때문에 설정 (단위 변환용)
        self.position = [0, 0, 0, 0, 0, 0, 0]  # 초기 위치 (각 관절)
        self.gripper = 0  # 초기 위치 (그리퍼)
        self.count = 0  # 이동 횟수 카운트 초기화

    def enable(self):
        """
        로봇팔을 활성화하고, 모터가 준비될 때까지 대기하는 함수입니다.
        """
        enable_flag = False  # 팔이 활성화되었는지 확인하는 플래그
        elapsed_time_flag = False  # 시간 초과 여부를 체크하는 플래그
        timeout = 5  # 타임아웃 시간 (초)
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
            time.sleep(1)  # 1초 간격으로 체크

        if elapsed_time_flag:  # 시간 초과 발생 시
            print("프로그램을 종료합니다")
            exit(0)  # 프로그램 종료

    def convert(self):
        """
        현재 로봇팔의 각도(deg)와 그리퍼 값(mm)을 변환하여 반환합니다.
        """
        return [round(angle * self.factor) for angle in self.position] + [round(self.gripper * self.factor)]

    def move(self):
        """
        로봇팔이 설정된 위치로 순차적으로 이동하도록 하는 함수입니다.
        """

        print(self.piper.GetArmJointMsgs())  # 현재 로봇팔 조인트 각도 출력
        self.count += 1  # 카운트 증가
        print(self.count)  # 카운트 출력

        # 매번 조인트 별로 45도씩 돌아가는 예제 코드
        if self.count == 1:
            print("원점")
            self.position = [0, 0, 0, 0, 0, 0]
            self.gripper = 0

        
        
        # 변환된 값 적용
        converted_values = self.convert()
        joint_values = converted_values[:6]  # 첫 6개는 조인트 값
        gripper_value = converted_values[6]  # 마지막 값은 그리퍼
        
        # 로봇의 동작을 제어하는 명령
        self.piper.MotionCtrl_2(0x01, 0x01, 50, 0x00)  # 팔 모션 제어 (속도 및 제어 모드)
        self.piper.JointCtrl(*joint_values)  # 조인트 제어
        self.piper.GripperCtrl(abs(gripper_value), 1000, 0x01, 0)  # 그리퍼 제어
        time.sleep(0.005)  # 5ms 대기

# 메인 함수
def main():
    can_name = parse_can_name()
    print(f"원점 이동: {can_name}")
    piper = C_PiperInterface(can_name)  # piper 인터페이스 생성
    piper.ConnectPort()  # 포트 연결

    move_j = Move_J(piper)  # Move_J 객체 생성
    move_j.enable()  # 팔 활성화
    move_j.move()  # 팔 이동

if __name__ == "__main__":
    main()  # 메인 함수 실행