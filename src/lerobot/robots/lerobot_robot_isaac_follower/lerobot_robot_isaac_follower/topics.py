"""Isaac follower ROS 2 topic paths.

Isaac Sim 그래프에서 퍼블리시/서브스크라이브하는 토픽 이름을 이 파일 상단에서만 바꾸면 됩니다.
"""

# ---------------------------------------------------------------------------
# ROS 2 노드 / 토픽 경로
# ---------------------------------------------------------------------------
NODE_NAME = "lerobot_isaac_follower"

# sensor_msgs/JointState — 현재 조인트 각도 (Isaac → LeRobot)
JOINT_STATE_TOPIC = "/isaac/follower/joint_states"

# sensor_msgs/JointState — 목표 조인트 각도 (LeRobot → Isaac)
JOINT_COMMAND_TOPIC = "/isaac/follower/joint_command"

# JointState.name 과 LeRobot observation/action 키를 1:1로 맞춥니다.
JOINT_NAMES = [
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "gripper",
]

# sensor_msgs/Image — 카메라 이미지 (Isaac → LeRobot)
# key: LeRobot observation 키, value: ROS 2 토픽
CAMERA_TOPICS = {
    "front": "/isaac/follower/front/rgb",
    "wrist": "/isaac/follower/wrist/rgb",
}

# observation_features 및 빈 프레임 placeholder 용 (height, width, channels)
CAMERA_SHAPES = {
    "front": (720, 1280, 3),
    "wrist": (720, 1280, 3),
}

# connect() 시 첫 joint_states 를 기다릴 시간 (초). 0 이면 대기하지 않습니다.
JOINT_STATE_TIMEOUT_S = 5.0

# ---------------------------------------------------------------------------
# 환경 초기화 신호 (Isaac Sim → LeRobot, 그 반대)
# ---------------------------------------------------------------------------
# std_msgs/Empty — Isaac가 환경/로봇을 리셋할 때 퍼블리시
RESET_TOPIC = "/isaac/env/reset"
# std_msgs/Empty — LeRobot가 Isaac에 리셋을 요청할 때 퍼블리시
RESET_REQUEST_TOPIC = "/isaac/env/reset_request"
# std_msgs/Empty — LeRobot가 리셋 신호를 받았음을 알림
RESET_ACK_TOPIC = "/isaac/env/reset_ack"
# std_msgs/Empty — cuRobo 태스크가 끝났을 때 (DONE/FAILED). LeRobot은 현재 에피소드 녹화를 멈춥니다.
EPISODE_END_TOPIC = "/isaac/env/episode_end"
# std_msgs/Empty — LeRobot가 다음 에피소드 녹화를 시작할 때
EPISODE_START_TOPIC = "/isaac/env/episode_start"
# std_msgs/String — Isaac 브릿지 상태 (waiting_for_lerobot, running, resetting, ...)
STATUS_TOPIC = "/isaac/env/status"
