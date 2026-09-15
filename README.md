<p align="center">
  <img alt="LeRobot, Hugging Face Robotics Library" src="./media/readme/lerobot-logo-thumbnail.png" width="100%">
</p>

<div align="center">

# RIA LeRobot

**Piper 실기**와 **Isaac Sim (ROS 2)** 으로 텔레옵 · 수집 · 학습까지

`v0.4.4` &nbsp;·&nbsp; Python `≥ 3.10` &nbsp;·&nbsp; `can_number` / `camera_number` / `<USER>` 만 바꿔 쓰면 됩니다

</div>

<p align="center">
  <img src="./media/readme/robots_control_video.webp" width="720" alt="LeRobot robot control demo">
</p>

<p align="center">
  <img src="./media/readme/lerobot-workflow.png" width="820" alt="Teleoperate, Record, Train, Evaluate">
</p>

<p align="center">
  <a href="#설치">설치</a> ·
  <a href="#piper-실기">Piper</a> ·
  <a href="#isaac-sim-ros-2">Isaac</a> ·
  <a href="#데이터-시각화">시각화</a>
</p>

---

## 설치

```bash
conda activate lerobot
cd /path/to/RIA_lerobot
pip install -e .
pip install -e src/lerobot/robots/lerobot_robot_piper_follower
pip install -e src/lerobot/teleoperators/lerobot_teleoperator_piper_leader
pip install -e src/lerobot/robots/lerobot_robot_isaac_follower
pip install -e src/lerobot/teleoperators/lerobot_teleoperator_isaac_leader
```

`--display_data=true` 를 켜면 Rerun 창에서 카메라와 조인트를 실시간으로 볼 수 있습니다.

| 키 | 동작 |
| :---: | --- |
| `→` | 에피소드 종료 후 다음으로 |
| `←` | 방금 에피소드 다시 녹화 |
| `Esc` | 녹화 중단 |

---

## Piper (실기)

<p align="center">
  <img src="./media/readme/piper-teleop.png" width="720" alt="Piper leader and follower teleoperation">
</p>

CAN으로 리더/팔로워를 연결하고, OpenCV 카메라로 영상을 받습니다.  
`can_number` 예: `can0`, `can1`. 카메라 번호는 먼저 찾습니다.

```bash
lerobot-find-cameras
```

### 텔레옵

리더를 움직이면 팔로워가 따라 가고, Rerun에서 카메라/조인트를 확인합니다.

```bash
lerobot-teleoperate \
  --robot.type=piper_follower \
  --robot.port=can_number \
  --teleop.type=piper_leader \
  --teleop.port=can_number \
  --robot.cameras="{ front: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}, top: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}}" \
  --display_data=true
```

### 데이터 녹화

텔레옵으로 에피소드를 저장합니다. Hub에 올리지 않으려면 `--dataset.push_to_hub=false` 를 유지합니다.

```bash
lerobot-record \
  --robot.type=piper_follower \
  --robot.port=can_number \
  --teleop.type=piper_leader \
  --teleop.port=can_number \
  --robot.cameras="{ front: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}, top: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}}" \
  --display_data=true \
  --dataset.repo_id=<USER>/piper_dataset \
  --dataset.single_task="Pick the cube and place it in the box" \
  --dataset.num_episodes=50 \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=10 \
  --dataset.push_to_hub=false
```

<details>
<summary><b>이어서 찍을 때</b></summary>

```bash
lerobot-record \
  --robot.type=piper_follower \
  --robot.port=can_number \
  --teleop.type=piper_leader \
  --teleop.port=can_number \
  --robot.cameras="{ front: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}, top: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}}" \
  --display_data=true \
  --dataset.repo_id=<USER>/piper_dataset \
  --dataset.single_task="Pick the cube and place it in the box" \
  --dataset.num_episodes=10 \
  --resume=true \
  --dataset.push_to_hub=false
```

</details>

### 에피소드 리플레이

저장된 액션을 팔로워에 다시 보냅니다.

```bash
lerobot-replay \
  --robot.type=piper_follower \
  --robot.port=can_number \
  --dataset.repo_id=<USER>/piper_dataset \
  --dataset.episode=0
```

### 학습

```bash
lerobot-train \
  --dataset.repo_id=<USER>/piper_dataset \
  --policy.type=act \
  --output_dir=outputs/train/act_piper \
  --job_name=act_piper \
  --policy.device=cuda \
  --wandb.enable=false
```

### 정책으로 평가 녹화

학습된 체크포인트로 실기를 돌리면서 평가 에피소드를 저장합니다.

```bash
lerobot-record \
  --robot.type=piper_follower \
  --robot.port=can_number \
  --robot.cameras="{ front: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}, top: {type: opencv, index_or_path: camera_number, width: 640, height: 480, fps: 30}}" \
  --display_data=true \
  --dataset.repo_id=<USER>/eval_piper \
  --dataset.single_task="Pick the cube and place it in the box" \
  --dataset.num_episodes=10 \
  --dataset.push_to_hub=false \
  --policy.path=outputs/train/act_piper/checkpoints/last/pretrained_model
```

---

## Isaac Sim (ROS 2)

<p align="center">
  <img src="./media/readme/isaac-sim.png" width="720" alt="Isaac Sim follower and leader with ROS 2 cameras">
</p>

Isaac 쪽 카메라와 조인트는 OpenCV / `--robot.port` 가 아니라 **ROS 2 토픽**으로 들어옵니다.  
토픽 이름은 아래 파일 상단에서만 바꿉니다.

- `src/lerobot/robots/lerobot_robot_isaac_follower/lerobot_robot_isaac_follower/topics.py`
- `src/lerobot/teleoperators/lerobot_teleoperator_isaac_leader/lerobot_teleoperator_isaac_leader/topics.py`

실행 전에 ROS 2를 source 하고, Isaac Sim에서 아래 토픽이 나와야 합니다.

```bash
source /opt/ros/<distro>/setup.bash
```

| 역할 | 토픽 |
| --- | --- |
| follower 조인트 | `/isaac/follower/joint_states` |
| follower 명령 | `/isaac/follower/joint_command` |
| 카메라 `front` / `wrist` | `/isaac/follower/front/rgb`, `/isaac/follower/wrist/rgb` |
| leader 조인트 | `/isaac/leader/joint_states` |

### 텔레옵

Isaac 리더를 움직이면 팔로워가 따라 갑니다. 카메라는 토픽에서 자동으로 붙습니다.

```bash
lerobot-teleoperate \
  --robot.type=isaac_follower \
  --teleop.type=isaac_leader \
  --display_data=true
```

### 데이터 녹화

```bash
lerobot-record \
  --robot.type=isaac_follower \
  --teleop.type=isaac_leader \
  --display_data=true \
  --dataset.repo_id=<USER>/isaac_dataset \
  --dataset.single_task="Pick the cube and place it in the box" \
  --dataset.num_episodes=50 \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=10 \
  --dataset.push_to_hub=false
```

<details>
<summary><b>Isaac이 에피소드 종료/리셋을 토픽으로 알려 주는 수집 모드</b></summary>

```bash
ISAAC_COLLECT=1 lerobot-record \
  --robot.type=isaac_follower \
  --teleop.type=isaac_leader \
  --display_data=true \
  --dataset.repo_id=<USER>/isaac_dataset \
  --dataset.single_task="Pick the cube and place it in the box" \
  --dataset.num_episodes=50 \
  --dataset.push_to_hub=false
```

관련 토픽: `/isaac/env/reset`, `/isaac/env/reset_request`, `/isaac/env/episode_end`, `/isaac/env/episode_start`

</details>

### 에피소드 리플레이

```bash
lerobot-replay \
  --robot.type=isaac_follower \
  --dataset.repo_id=<USER>/isaac_dataset \
  --dataset.episode=0
```

### 학습

```bash
lerobot-train \
  --dataset.repo_id=<USER>/isaac_dataset \
  --policy.type=act \
  --output_dir=outputs/train/act_isaac \
  --job_name=act_isaac \
  --policy.device=cuda \
  --wandb.enable=false
```

### 정책으로 평가 녹화

Isaac에서 학습한 모델은 같은 `isaac_follower` 카메라 키(`front`, `wrist`)와 조인트 단위로 평가해야 합니다.  
실기 Piper 체크포인트를 Isaac에, 또는 그 반대로 그대로 넣으면 입력이 맞지 않습니다.

```bash
lerobot-record \
  --robot.type=isaac_follower \
  --display_data=true \
  --dataset.repo_id=<USER>/eval_isaac \
  --dataset.single_task="Pick the cube and place it in the box" \
  --dataset.num_episodes=10 \
  --dataset.push_to_hub=false \
  --policy.path=outputs/train/act_isaac/checkpoints/last/pretrained_model
```

---

## 데이터 시각화

로컬에 저장된 에피소드를 Rerun으로 재생합니다.

```bash
# Piper
lerobot-dataset-viz \
  --repo-id <USER>/piper_dataset \
  --episode-index 0

# Isaac
lerobot-dataset-viz \
  --repo-id <USER>/isaac_dataset \
  --episode-index 0
```
