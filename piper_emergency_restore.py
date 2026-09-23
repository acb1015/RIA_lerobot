#!/usr/bin/env python3
# -*-coding:utf8-*-

"""
해당 파일은 0-2. piper_emergency_stop.py 파일을 실행시켰을 경우에만 적용됩니다.
해당 파일은 PiPER 모드를 리셋하기 위해 자동으로 Disable을 적용시키기 때문에 PiPER를 안전한 위치에 놓고 실행시켜주세요.
티칭 모드 적용 시, 현재는 리셋이 불가능합니다. 전원선을 뽑았다가 다시 재인가해주세요.
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
            raise SystemExit(f"알 수 없는 인자입니다: {arg}\n예: python piper_emergency_restore.py --can1")
        if not re.fullmatch(r"can\d+", can_name):
            raise SystemExit(f"CAN 이름은 can0, can1 형식이어야 합니다. 받은 값: {can_name}")
        i += 1
    return can_name


if __name__ == "__main__":
    can_name = parse_can_name()
    print(f"긴급 정지 복구: {can_name}")
    piper = C_PiperInterface_V2(can_name)
    piper.ConnectPort()

    piper.MotionCtrl_1(0x02, 0, 0x00)
    piper.MotionCtrl_1(0x00, 0, 0x00)

    piper.MotionCtrl_2(0x01, 0, 0, 0x00)  # 한 번만 실행 시 StandBy 모드
    #piper.GripperCtrl(0, 0, 0x01, 0)
    #piper.GripperCtrl(gripper_angle=0, gripper_effort=0, gripper_code=0x00, set_zero=0) 
    time.sleep(1)

    piper.MotionCtrl_2(0x01, 0, 0, 0x00)  # 최종적으로 한번 더 실행해야 CAN 모드로 변경
    #piper.GripperCtrl(0, 0, 0x03, 0)
    time.sleep(1)

    if piper.GetArmStatus().arm_status.ctrl_mode == 0x01:
        print("정상 리셋되었습니다. PiPER를 작동시킬 수 있습니다.")
    else:
        print("리셋에 실패했습니다. PiPER를 작동시키지 말아주세요!")
        pass
