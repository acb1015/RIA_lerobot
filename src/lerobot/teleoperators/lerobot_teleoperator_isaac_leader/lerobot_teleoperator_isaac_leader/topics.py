"""Isaac leader ROS 2 topic paths.

Isaac Sim 그래프에서 퍼블리시하는 토픽 이름을 이 파일 상단에서만 바꾸면 됩니다.
"""

# ---------------------------------------------------------------------------
# ROS 2 노드 / 토픽 경로
# ---------------------------------------------------------------------------
NODE_NAME = "lerobot_isaac_leader"

# sensor_msgs/JointState — 리더 암 조인트 각도 (Isaac → LeRobot)
JOINT_STATE_TOPIC = "/isaac/leader/joint_states"

# JointState.name 과 LeRobot action 키를 1:1로 맞춥니다.
# follower 의 JOINT_NAMES 와 같아야 teleoperate 가 그대로 연결됩니다.
JOINT_NAMES = [
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "gripper",
]

# connect() 시 첫 joint_states 를 기다릴 시간 (초). 0 이면 대기하지 않습니다.
JOINT_STATE_TIMEOUT_S = 5.0

# std_msgs/Empty — Isaac가 환경/리더 암을 리셋할 때 퍼블리시
RESET_TOPIC = "/isaac/env/reset"
