# LeRobot Integration Setup — xArm + XR Teleoperator

This guide covers installing the two LeRobot plugin packages, verifying they
are correctly detected, and running `lerobot-record` to teleoperate the xArm
with an XR headset while recording a dataset.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python ≥ 3.10 | Tested with the `lerobot` conda env |
| [LeRobot](https://github.com/huggingface/lerobot) | Installed (editable or pip) in the same environment |
| xArm Python SDK | `pip install xarm-python-sdk` |
| `televuer` / `teleimager` | Already installed from the xr_teleoperate project |
| Network access | xArm controller + image server reachable |

## 1. Install the Plugin Packages

Activate your environment first:

```bash
conda activate lerobot
```

Install both packages in **editable** mode (no extra deps are pulled since
LeRobot and the xArm SDK should already be present):

```bash
# Robot plugin
cd /home/mht/code/lerobot_robot_xarm
pip install -e .

# Teleoperator plugin
cd /home/mht/code/lerobot_teleoperator_xr
pip install -e .
```

## 2. Verify Plugin Detection

### 2.1 Check that the packages are installed

```bash
pip show lerobot_robot_xarm lerobot_teleoperator_xr
```

Expected: both packages listed with version `0.1.0`.

### 2.2 Check that LeRobot discovers the plugins

```bash
python -c "
from lerobot.utils.import_utils import register_third_party_plugins
register_third_party_plugins()

from lerobot.robots.config import RobotConfig
from lerobot.teleoperators.config import TeleoperatorConfig

robot_choices = RobotConfig.get_known_choices()
teleop_choices = TeleoperatorConfig.get_known_choices()

assert 'xarm_robot' in robot_choices, 'xarm_robot not found!'
assert 'xr_teleoperator' in teleop_choices, 'xr_teleoperator not found!'

print('✅ xarm_robot registered:', robot_choices['xarm_robot'])
print('✅ xr_teleoperator registered:', teleop_choices['xr_teleoperator'])
"
```

Expected output:

```
✅ xarm_robot registered: <class 'lerobot_robot_xarm.config_xarm_robot.XArmRobotConfig'>
✅ xr_teleoperator registered: <class 'lerobot_teleoperator_xr.config_xr_teleoperator.XRTeleoperatorConfig'>
```

### 2.3 Check that `lerobot-record` sees both types

```bash
lerobot-record --help 2>&1 | grep -E "robot\.type|teleop\.type"
```

You should see `xarm_robot` in the `--robot.type` choices and
`xr_teleoperator` in the `--teleop.type` choices.

## 3. Configuration Reference

### Robot (`--robot.*`)

| Flag | Type | Default | Description |
|---|---|---|---|
| `--robot.type` | choice | — | Must be `xarm_robot` |
| `--robot.xarm_ip` | str | `192.168.1.230` | xArm controller IP |
| `--robot.img_server_ip` | str \| None | `None` | Image server IP (set to enable cameras) |
| `--robot.head_camera` | bool | `false` | Enable head camera |
| `--robot.left_wrist_camera` | bool | `false` | Enable left wrist camera |
| `--robot.right_wrist_camera` | bool | `true` | Enable right wrist camera |
| `--robot.img_height` | int | `480` | Camera image height |
| `--robot.img_width` | int | `640` | Camera image width |
| `--robot.gripper_open` | int | `850` | Gripper fully-open position |
| `--robot.gripper_closed` | int | `0` | Gripper fully-closed position |

### Teleoperator (`--teleop.*`)

| Flag | Type | Default | Description |
|---|---|---|---|
| `--teleop.type` | choice | — | Must be `xr_teleoperator` |
| `--teleop.xarm_ip` | str | `192.168.1.230` | Read-only xArm connection (pose queries) |
| `--teleop.img_server_ip` | str | `192.168.123.232` | Image server IP for VR streaming |
| `--teleop.input_mode` | str | `controller` | `controller` or `hand` |
| `--teleop.display_mode` | str | `immersive` | `immersive`, `ego`, `pass-through`, `immersive-wrist` |
| `--teleop.opposite` | bool | `false` | Invert x/y for face-to-face operation |
| `--teleop.translation_scale` | float | `1000.0` | VR meters → xArm mm scale factor |
| `--teleop.orientation_slerp_alpha` | float | `0.015` | Orientation lock blending speed |

## 4. Sample Run Scripts


### only teleoperate

```bash
lerobot-teleoperate \
    --robot.type=xarm_robot \
    --robot.xarm_ip=192.168.1.230 \
    --robot.img_server_ip=192.168.1.232 \
    --robot.right_wrist_camera=true \
    --teleop.type=xr_teleoperator \
    --teleop.xarm_ip=192.168.1.230 \
    --teleop.img_server_ip=192.168.1.232 \
    --teleop.input_mode=controller \
    --teleop.display_mode=immersive \
    --teleop.opposite=true
```

teleoperate with data visualization
```bash
lerobot-teleoperate     --robot.type=xarm_robot     --robot.xarm_ip=192.168.1.230     --robot.cameras='{ right_wrist_camera: {type: imageclient, host: "192.168.1.232", camera_name: right_wrist_camera, width: 640, height: 480, fps: 30} }'     --teleop.type=xr_teleoperator     --teleop.xarm_ip=192.168.1.230     --teleop.img_server_ip=192.168.1.232     --teleop.input_mode=controller     --teleop.display_mode=immersive     --teleop.opposite=true     --display_data=true
```

### 4.1 Basic recording (right wrist camera, operator behind robot)

```bash
lerobot-record \
    --robot.type=xarm_robot \
    --robot.xarm_ip=192.168.1.230 \
    --robot.img_server_ip=192.168.1.232 \
    --robot.right_wrist_camera=true \
    --teleop.type=xr_teleoperator \
    --teleop.xarm_ip=192.168.1.230 \
    --teleop.img_server_ip=192.168.1.232 \
    --teleop.input_mode=controller \
    --teleop.display_mode=immersive \
    --dataset.repo_id=my_user/xarm_xr_dataset_test \
    --dataset.single_task="Pick and place the object" \
    --dataset.fps=30 \
    --dataset.num_episodes=50
```

```bash
lerobot-record \
  --robot.type=xarm_robot \
  --robot.xarm_ip=192.168.1.230 \
  --robot.cameras='{ right_wrist_camera: {type: imageclient, host: "192.168.1.2", request_port: 60000, camera_name: right_wrist_camera, width: 640, height: 480, fps: 30} }' \
  --teleop.type=xr_teleoperator \
  --teleop.xarm_ip=192.168.1.230 \
  --teleop.img_server_ip=192.168.1.2 \
  --teleop.input_mode=controller \
  --teleop.display_mode=immersive \
  --dataset.root=/home/mht/code/xr_teleoperate/dataset/test_$(date +%Y%m%d_%H%M%S) \
  --dataset.repo_id=my_user/xarm_xr_dataset_run \
  --dataset.single_task="Pick and place the object" \
  --dataset.fps=30 \
  --dataset.num_episodes=50
```

### 4.2 Opposite mode (operator facing the robot)

```bash
lerobot-record \
    --robot.type=xarm_robot \
    --robot.xarm_ip=192.168.1.230 \
    --robot.img_server_ip=192.168.1.232 \
    --robot.right_wrist_camera=true \
    --teleop.type=xr_teleoperator \
    --teleop.xarm_ip=192.168.1.230 \
    --teleop.img_server_ip=192.168.1.232 \
    --teleop.opposite=true \
    --teleop.display_mode=immersive \
    --dataset.repo_id=my_user/xarm_xr_opposite \
    --dataset.single_task="Pick and place the object" \
    --dataset.fps=30 \
    --dataset.num_episodes=50
```

```bash
lerobot-record \
    --robot.type=xarm_robot \
    --robot.xarm_ip=192.168.1.230 \
    --robot.cameras='{ right_wrist_camera: {type: imageclient, host: "192.168.1.2", request_port: 60000, camera_name: right_wrist_camera, width: 640, height: 480, fps: 30} }' \
    --teleop.type=xr_teleoperator \
    --teleop.xarm_ip=192.168.1.230 \
    --teleop.img_server_ip=192.168.1.2 \
    --teleop.input_mode=controller \
    --teleop.display_mode=immersive \
    --teleop.opposite=true \
    --dataset.root=/home/mht/code/xr_teleoperate/dataset/test_$(date +%Y%m%d_%H%M%S) \
    --dataset.repo_id=my_user/xarm_xr_dataset_run \
    --dataset.single_task="Pick and place the object" \
    --dataset.fps=30 \
    --dataset.num_episodes=50
```

### 4.3 Multi-camera recording (head + right wrist)

```bash
lerobot-record \
    --robot.type=xarm_robot \
    --robot.xarm_ip=192.168.1.230 \
    --robot.img_server_ip=192.168.1.232 \
    --robot.head_camera=true \
    --robot.right_wrist_camera=true \
    --teleop.type=xr_teleoperator \
    --teleop.xarm_ip=192.168.1.230 \
    --teleop.img_server_ip=192.168.1.232 \
    --teleop.display_mode=immersive \
    --dataset.repo_id=my_user/xarm_xr_multicam \
    --dataset.single_task="Pick and place the object" \
    --dataset.fps=30 \
    --dataset.num_episodes=50
```

### 4.4 Hand tracking mode with pass-through display

```bash
lerobot-record \
    --robot.type=xarm_robot \
    --robot.xarm_ip=192.168.1.230 \
    --robot.img_server_ip=192.168.1.232 \
    --robot.right_wrist_camera=true \
    --teleop.type=xr_teleoperator \
    --teleop.xarm_ip=192.168.1.230 \
    --teleop.img_server_ip=192.168.1.232 \
    --teleop.input_mode=hand \
    --teleop.display_mode=pass-through \
    --dataset.repo_id=my_user/xarm_xr_hand \
    --dataset.single_task="Pick and place the object" \
    --dataset.fps=30 \
    --dataset.num_episodes=50
```

## 5. Teleoperation Controls (during recording)

These controls are active inside the VR headset during a recording session:

| Control | Action |
|---|---|
| **A button** (right) | Start teleoperation — captures VR/robot origins |
| **B button** (right) | Stop teleoperation — arm holds position |
| **Squeeze** (right) | Gripper: released = open, squeezed = closed |
| **Trigger** (either) | Sprint mode: doubles translation speed |
| **Thumbstick ↑** | Lock end-effector to wall orientation |
| **Thumbstick ↓** | Lock end-effector to floor orientation |
| **Thumbstick click** | Unlock orientation (free mode) |

Episode boundaries are managed by `lerobot-record` itself (typically via
keyboard on the host machine — see `lerobot-record --help` for episode
control keys).

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `xarm_robot` not in `--robot.type` choices | Re-run `pip install -e .` in `lerobot_robot_xarm/` and check `pip show lerobot_robot_xarm` |
| `Failed to read initial xArm pose` | Check that the xArm is powered on and reachable at the specified IP |
| `ImageClient` connection errors | Verify the image server is running and the IP/port are correct |
| `TeleVuerWrapper` fails to initialize | Ensure the XR headset is connected and the WebXR server is running |
| Camera images are black | Check that the camera streams are active on the image server |
| Actions seem inverted | Try toggling `--teleop.opposite` |
