import time
import argparse
import threading
import numpy as np
from scipy.spatial.transform import Rotation

import os 
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from televuer import TeleVuerWrapper
from teleimager.image_client import ImageClient
from xarm.wrapper import XArmAPI
from sshkeyboard import listen_keyboard, stop_listening

DEFAULT_XARM_IP = os.environ.get("XARM_IP", "192.168.1.230")
TRANSLATION_SCALE = 1000.0   # VR meters -> xArm mm
GRIPPER_OPEN = 850
GRIPPER_CLOSED = 0
# Fixed end-effector orientation when "wall lock" is active (RPY in degrees).
FIXED_WALL_RPY = [134.2, -88.5, -130.8]
# Fixed orientation when "floor lock" is active.
FIXED_FLOOR_RPY = [180, 0, 180]

# How fast to blend toward the fixed orientation (0→no change, 1→instant snap).
# At 50 Hz with alpha=0.015, convergence takes roughly 1.3 seconds.
ORIENTATION_SLERP_ALPHA = 0.015

STOP = False


def on_press(key):
    global STOP
    if key == 'q':
        STOP = True


def setup_arm(ip: str) -> XArmAPI:
    arm = XArmAPI(ip, is_radian=False)
    arm.clean_warn()
    arm.clean_error()
    arm.motion_enable(enable=True)
    arm.set_mode(0)
    arm.set_state(0)
    return arm


def build_display(teleop_active, target_pose, robot_origin, loop_hz, gripper_closed, scale, fix_orientation):
    """Build a compact status display."""
    lines = []
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append("║       🤖  XR → xArm Teleoperation   (press [q] to quit)    ║")
    lines.append(f"║       Loop rate: {loop_hz:6.1f} Hz                                  ║")
    lines.append("╠══════════════════════════════════════════════════════════════╣")
    status = "🟢 ACTIVE" if teleop_active else "🔴 INACTIVE"
    
    if fix_orientation == 'wall':
        orient = "🧱 WALL LOCK"
    elif fix_orientation == 'floor':
        orient = "⏬ FLOOR LOCK"
    else:
        orient = "🔓 FREE"
        
    lines.append(f"║  Status: {status}   Orientation: {orient}")
    lines.append(f"║  Gripper: {'CLOSED' if gripper_closed else 'OPEN'}   Scale: {scale:.0f}")
    lines.append("╠══════════════════════════════════════════════════════════════╣")
    if robot_origin is not None:
        lines.append(f"║  [Robot Origin]  x={robot_origin[0]:+8.2f}  y={robot_origin[1]:+8.2f}  z={robot_origin[2]:+8.2f}")
        lines.append(f"║                  r={robot_origin[3]:+8.2f}  p={robot_origin[4]:+8.2f}  w={robot_origin[5]:+8.2f}")
    if target_pose is not None:
        lines.append(f"║  [Target Pose]   x={target_pose[0]:+8.2f}  y={target_pose[1]:+8.2f}  z={target_pose[2]:+8.2f}")
        lines.append(f"║                  r={target_pose[3]:+8.2f}  p={target_pose[4]:+8.2f}  w={target_pose[5]:+8.2f}")
    else:
        lines.append("║  [Target Pose]   — waiting for activation (press A) —")
    lines.append("╠══════════════════════════════════════════════════════════════╣")
    lines.append("║  [A] Start  [B] Stop  [Squeeze] Gripper  [Stick ↑↓/Click] Lock ║")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


def refresh_screen(content):
    """Clear terminal and print content at top."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write(content + "\n")
    sys.stdout.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='XR teleoperation for xArm — use VR controller to control xArm in real-time.')
    parser.add_argument('--frequency', type=float, default=50.0, help='Loop frequency (Hz)')
    parser.add_argument('--input-mode', type=str, choices=['hand', 'controller'], default='controller', help='XR device input tracking source')
    parser.add_argument('--display-mode', type=str, choices=['immersive', 'ego', 'pass-through', 'immersive-wrist'], default='immersive', help='XR device display mode')
    parser.add_argument('--img-server-ip', type=str, default='192.168.123.232', help='IP address of image server')
    parser.add_argument('--xarm-ip', type=str, default=DEFAULT_XARM_IP, help='xArm IP address')
    parser.add_argument('--opposite', action='store_true', help='Operator stands opposite (facing) the robot: inverts x/y axes')
    args = parser.parse_args()
    print(f"[INFO] args: {args}")

    try:
        # keyboard listener
        listen_keyboard_thread = threading.Thread(
            target=listen_keyboard,
            kwargs={"on_press": on_press, "until": None, "sequential": False},
            daemon=True,
        )
        listen_keyboard_thread.start()

        # image client
        img_client = ImageClient(host=args.img_server_ip)
        camera_config = img_client.get_cam_config()

        # Pick a display camera: prefer head_camera, fall back to right_wrist_camera if head has no stream
        head_cfg = camera_config['head_camera']
        if head_cfg.get('enable_webrtc') or head_cfg.get('enable_zmq'):
            display_cfg = head_cfg
        else:
            display_cfg = camera_config['right_wrist_camera']

        xr_need_local_img = not (args.display_mode == 'pass-through' or display_cfg['enable_webrtc'])

        # wrist overlay URLs (used in immersive-wrist mode)
        left_wrist_cfg = camera_config.get('left_wrist_camera', {})
        right_wrist_cfg = camera_config.get('right_wrist_camera', {})
        left_wrist_webrtc_url = (
            f"https://{args.img_server_ip}:{left_wrist_cfg['webrtc_port']}/offer"
            if left_wrist_cfg.get('enable_webrtc') else None
        )
        right_wrist_webrtc_url = (
            f"https://{args.img_server_ip}:{right_wrist_cfg['webrtc_port']}/offer"
            if right_wrist_cfg.get('enable_webrtc') else None
        )

        # televuer wrapper
        tv_wrapper = TeleVuerWrapper(
            use_hand_tracking=args.input_mode == "hand",
            binocular=display_cfg.get('binocular', False),
            img_shape=display_cfg['image_shape'],
            display_mode=args.display_mode,
            zmq=display_cfg['enable_zmq'],
            webrtc=display_cfg['enable_webrtc'],
            webrtc_url=f"https://{args.img_server_ip}:{display_cfg['webrtc_port']}/offer",
            left_wrist_webrtc_url=left_wrist_webrtc_url,
            right_wrist_webrtc_url=right_wrist_webrtc_url,
        )

        # xArm setup
        print(f"[INFO] Connecting to xArm at {args.xarm_ip}")
        arm = setup_arm(args.xarm_ip)
        code, init_pose = arm.get_position(is_radian=False)
        if code != 0 or init_pose is None:
            raise RuntimeError(f"Failed to read initial xArm pose, code={code}")
        print(f"[INFO] xArm initial pose: {[f'{v:.2f}' for v in init_pose]}")

        # teleoperation state
        teleop_active = False
        vr_origin = None          # (4,4) VR wrist SE(3) at activation
        head_origin_pos = None    # (3,) head position at activation (world frame)
        robot_origin = None       # [x,y,z,r,p,y] xArm pose at activation (mm, deg)
        gripper_closed = False
        prev_a = False
        prev_b = False
        prev_sprint = False
        prev_thumbstick_push_up = False
        prev_thumbstick_push_down = False
        prev_thumbstick_click = False
        fix_orientation = 'free'  # 'free', 'wall', or 'floor'
        target_pose = None
        loop_hz = 0.0

        print("[INFO] Ready. Press A on right controller to start teleoperation.")

        while not STOP:
            start_time = time.time()

            # stream image to XR if needed
            if display_cfg['enable_zmq'] and xr_need_local_img:
                if display_cfg is camera_config['right_wrist_camera']:
                    head_img, _ = img_client.get_right_wrist_frame()
                else:
                    head_img, _ = img_client.get_head_frame()
                tv_wrapper.render_to_xr(head_img)

            # get tele data
            tele_data = tv_wrapper.get_tele_data()

            # --- A button: start teleop (rising edge) ---
            a_now = tele_data.right_ctrl_aButton
            if a_now and not prev_a and not teleop_active:
                vr_origin = tele_data.right_wrist_pose.copy()
                head_origin_pos = tele_data.head_pose[:3, 3].copy()
                code, cur = arm.get_position(is_radian=False)
                if code == 0 and cur is not None:
                    robot_origin = list(cur)
                    # switch to servo mode
                    arm.set_mode(1)
                    arm.set_state(0)
                    teleop_active = True
                    target_pose = list(robot_origin)
                    print("[INFO] ✅ Teleoperation STARTED")
                else:
                    print(f"[WARN] Cannot read robot pose (code={code}), start aborted")
            prev_a = a_now

            # --- B button: stop teleop (rising edge) ---
            b_now = tele_data.right_ctrl_bButton
            if b_now and not prev_b and teleop_active:
                teleop_active = False
                fix_orientation = 'free'
                # switch to position mode (arm holds position)
                arm.set_mode(0)
                arm.set_state(0)
                print("[INFO] 🛑 Teleoperation STOPPED")
            prev_b = b_now

            # --- Thumbstick push up (y < -0.7): LOCK orientation to WALL (rising edge) ---
            left_y = tele_data.left_ctrl_thumbstickValue[1] if hasattr(tele_data, 'left_ctrl_thumbstickValue') else 0.0
            right_y = tele_data.right_ctrl_thumbstickValue[1] if hasattr(tele_data, 'right_ctrl_thumbstickValue') else 0.0
            
            thumbstick_push_up_now = (left_y < -0.7) or (right_y < -0.7)
            if thumbstick_push_up_now and not prev_thumbstick_push_up and fix_orientation != 'wall':
                fix_orientation = 'wall'
                print("[INFO] 🧱 Orientation LOCKED (wall)")
            prev_thumbstick_push_up = thumbstick_push_up_now

            # --- Thumbstick push down (y > 0.7): LOCK orientation to FLOOR (rising edge) ---
            thumbstick_push_down_now = (left_y > 0.7) or (right_y > 0.7)
            if thumbstick_push_down_now and not prev_thumbstick_push_down and fix_orientation != 'floor':
                fix_orientation = 'floor'
                print("[INFO] ⏬ Orientation LOCKED (floor)")
            prev_thumbstick_push_down = thumbstick_push_down_now

            # --- Thumbstick click: UNLOCK orientation (rising edge) ---
            thumbstick_click_now = tele_data.right_ctrl_thumbstick or tele_data.left_ctrl_thumbstick
            if thumbstick_click_now and not prev_thumbstick_click and fix_orientation != 'free':
                fix_orientation = 'free'
                # Re-anchor on unlock so VR tracking resumes from the fixed orientation
                if teleop_active and target_pose is not None:
                    vr_origin = tele_data.right_wrist_pose.copy()
                    head_origin_pos = tele_data.head_pose[:3, 3].copy()
                    robot_origin = list(target_pose)
                print("[INFO] 🔓 Orientation UNLOCKED (free)")
            prev_thumbstick_click = thumbstick_click_now

            # --- Gripper: proportional from squeeze value ---
            # squeezeValue: 0.0 (released) -> 1.0 (fully squeezed)
            squeeze_val = tele_data.right_ctrl_squeezeValue
            gripper_pos = int(GRIPPER_OPEN * (1.0 - squeeze_val))
            arm.set_gripper_position(gripper_pos, wait=False, speed=5000, auto_enable=True)
            gripper_closed = squeeze_val > 0.5

            # --- Teleop control ---
            if teleop_active and vr_origin is not None and robot_origin is not None:
                current_vr = tele_data.right_wrist_pose

                # Cancel out headset translation: the wrist pose is stored relative to the
                # head, so any head movement shifts it.  Adding back (current_head - head_origin)
                # keeps the delta purely from controller movement in world space.
                head_compensation = tele_data.head_pose[:3, 3] - head_origin_pos

                # position delta: VR meters -> xArm mm (double scale when either index trigger is pressed)
                sprint = tele_data.right_ctrl_trigger or tele_data.left_ctrl_trigger
                if sprint != prev_sprint:
                    # Reset reference to current pose so scale change doesn't cause a jump
                    vr_origin = current_vr.copy()
                    head_origin_pos = tele_data.head_pose[:3, 3].copy()
                    robot_origin = list(target_pose)
                    prev_sprint = sprint
                scale = TRANSLATION_SCALE * (2.0 if sprint else 1.0)
                delta_pos = (current_vr[:3, 3] + head_compensation - vr_origin[:3, 3]) * scale

                # rotation delta via proper matrix composition
                delta_rot = current_vr[:3, :3] @ vr_origin[:3, :3].T

                # opposite mode: operator faces the robot, invert x and y
                if args.opposite:
                    delta_pos[0] = -delta_pos[0]
                    delta_pos[1] = -delta_pos[1]
                    _Rz = np.diag([-1.0, -1.0, 1.0])
                    delta_rot = _Rz @ delta_rot @ _Rz

                target_pos = np.array(robot_origin[:3]) + delta_pos
                robot_origin_rot = Rotation.from_euler('xyz', robot_origin[3:], degrees=True).as_matrix()
                target_rot = delta_rot @ robot_origin_rot
                target_rpy = Rotation.from_matrix(target_rot).as_euler('xyz', degrees=True)

                # Smoothly blend orientation toward active lock target
                if fix_orientation != 'free' and target_pose is not None:
                    cur = Rotation.from_euler('xyz', target_pose[3:], degrees=True)
                    target_euler = FIXED_WALL_RPY if fix_orientation == 'wall' else FIXED_FLOOR_RPY
                    goal = Rotation.from_euler('xyz', target_euler, degrees=True)
                    step = Rotation.from_rotvec((goal * cur.inv()).as_rotvec() * ORIENTATION_SLERP_ALPHA)
                    target_rpy = (step * cur).as_euler('xyz', degrees=True)

                target_pose = list(target_pos) + list(target_rpy)
                code = arm.set_servo_cartesian(target_pose, is_radian=False)
                if code != 0:
                    print(f"[WARN] set_servo_cartesian failed: code={code}")

            # display
            display = build_display(teleop_active, target_pose, robot_origin, loop_hz, gripper_closed, scale if teleop_active else TRANSLATION_SCALE, fix_orientation)
            refresh_screen(display)

            elapsed = time.time() - start_time
            loop_hz = 1.0 / elapsed if elapsed > 0 else 0.0
            sleep_time = max(0, (1 / args.frequency) - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n⛔ KeyboardInterrupt, exiting program...")
    except Exception:
        import traceback
        print(traceback.format_exc())
    finally:
        print()
        try:
            stop_listening()
            listen_keyboard_thread.join()
        except Exception as e:
            print(f"Failed to stop keyboard listener: {e}")
        try:
            img_client.close()
        except Exception as e:
            print(f"Failed to close image client: {e}")
        try:
            tv_wrapper.close()
        except Exception as e:
            print(f"Failed to close televuer wrapper: {e}")
        try:
            arm.set_mode(0)
            arm.set_state(0)
            arm.disconnect()
        except Exception as e:
            print(f"Failed to disconnect xArm: {e}")
        print("✅ Exiting program.")
        exit(0)
