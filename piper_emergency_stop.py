#!/usr/bin/env python3
# -*-coding:utf8-*-

"""
급하게 PiPER를 멈추고 싶을 경우, 해당 파일을 꼭 실행해야 합니다!
"""

import re
import sys
import time

from piper_sdk import *


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
            raise SystemExit(f"알 수 없는 인자입니다: {arg}\n예: python piper_emergency_stop.py --can1")
        if not re.fullmatch(r"can\d+", can_name):
            raise SystemExit(f"CAN 이름은 can0, can1 형식이어야 합니다. 받은 값: {can_name}")
        i += 1
    return can_name


if __name__ == "__main__":
    can_name = parse_can_name()
    print(f"긴급 정지: {can_name}")
    piper = C_PiperInterface(can_name)
    piper.ConnectPort()
    
    time.sleep(2)
    piper.MotionCtrl_1(0x01,0,0x00) # 긴급 정지버튼 (E-stop)
    piper.GripperCtrl(gripper_angle=0, gripper_effort=0, gripper_code=0x00, set_zero=0) 

    print("정상 중지되었습니다.")
    pass
