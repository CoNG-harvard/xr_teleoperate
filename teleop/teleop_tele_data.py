import time
import argparse
import threading
import numpy as np

import os 
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from televuer import TeleVuerWrapper
from teleimager.image_client import ImageClient
from sshkeyboard import listen_keyboard, stop_listening

STOP = False

def on_press(key):
    global STOP
    if key == 'q':
        STOP = True

def fmt_arr(arr, indent=2):
    """Format a numpy array with fixed-width floats, indented."""
    prefix = " " * indent
    if arr.ndim == 1:
        return prefix + "  ".join(f"{v:+10.4f}" for v in arr)
    return "\n".join(
        prefix + "  ".join(f"{v:+10.4f}" for v in row) for row in arr
    )

def build_display(tele_data, input_mode, hz):
    """Build the full screen content as a single string."""
    lines = []
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append("║         🟢  XR TeleData Live View   (press [q] to quit)    ║")
    lines.append(f"║         Loop rate: {hz:6.1f} Hz                                 ║")
    lines.append("╠══════════════════════════════════════════════════════════════╣")

    lines.append("║  [Head Pose]")
    lines.append(fmt_arr(tele_data.head_pose))
    lines.append("║  [Left Wrist Pose]")
    lines.append(fmt_arr(tele_data.left_wrist_pose))
    lines.append("║  [Right Wrist Pose]")
    lines.append(fmt_arr(tele_data.right_wrist_pose))

    lines.append("╠══════════════════════════════════════════════════════════════╣")

    if input_mode == "hand":
        if tele_data.left_hand_pos is not None:
            lines.append(f"║  [Left Hand Positions]  shape {tele_data.left_hand_pos.shape}")
            lines.append(fmt_arr(tele_data.left_hand_pos))
        if tele_data.right_hand_pos is not None:
            lines.append(f"║  [Right Hand Positions] shape {tele_data.right_hand_pos.shape}")
            lines.append(fmt_arr(tele_data.right_hand_pos))
        if tele_data.left_hand_rot is not None:
            lines.append(f"║  [Left Hand Rotations]  shape {tele_data.left_hand_rot.shape}")
            lines.append(fmt_arr(tele_data.left_hand_rot))
        if tele_data.right_hand_rot is not None:
            lines.append(f"║  [Right Hand Rotations] shape {tele_data.right_hand_rot.shape}")
            lines.append(fmt_arr(tele_data.right_hand_rot))
        lines.append(f"║  [Left  Pinch]   {str(tele_data.left_hand_pinch):>5s}  Value: {tele_data.left_hand_pinchValue:.2f}")
        lines.append(f"║  [Left  Squeeze] {str(tele_data.left_hand_squeeze):>5s}  Value: {tele_data.left_hand_squeezeValue:.2f}")
        lines.append(f"║  [Right Pinch]   {str(tele_data.right_hand_pinch):>5s}  Value: {tele_data.right_hand_pinchValue:.2f}")
        lines.append(f"║  [Right Squeeze] {str(tele_data.right_hand_squeeze):>5s}  Value: {tele_data.right_hand_squeezeValue:.2f}")
    else:
        lines.append(f"║  [Left  Trigger]    {str(tele_data.left_ctrl_trigger):>5s}  Value: {tele_data.left_ctrl_triggerValue:.2f}")
        lines.append(f"║  [Left  Squeeze]    {str(tele_data.left_ctrl_squeeze):>5s}  Value: {tele_data.left_ctrl_squeezeValue:.2f}")
        lines.append(f"║  [Left  Thumbstick] {str(tele_data.left_ctrl_thumbstick):>5s}  Value: {tele_data.left_ctrl_thumbstickValue}")
        lines.append(f"║  [Left  A/B]        A={tele_data.left_ctrl_aButton}  B={tele_data.left_ctrl_bButton}")
        lines.append(f"║  [Right Trigger]    {str(tele_data.right_ctrl_trigger):>5s}  Value: {tele_data.right_ctrl_triggerValue:.2f}")
        lines.append(f"║  [Right Squeeze]    {str(tele_data.right_ctrl_squeeze):>5s}  Value: {tele_data.right_ctrl_squeezeValue:.2f}")
        lines.append(f"║  [Right Thumbstick] {str(tele_data.right_ctrl_thumbstick):>5s}  Value: {tele_data.right_ctrl_thumbstickValue}")
        lines.append(f"║  [Right A/B]        A={tele_data.right_ctrl_aButton}  B={tele_data.right_ctrl_bButton}")

    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)

def refresh_screen(content):
    """Clear terminal and print content at top."""
    sys.stdout.write("\033[2J\033[H")  # clear screen + move cursor to top-left
    sys.stdout.write(content)
    sys.stdout.flush()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simple teleoperation data viewer — outputs XR tele data without robot control.')
    parser.add_argument('--frequency', type=float, default=50.0, help='Loop frequency (Hz)')
    parser.add_argument('--input-mode', type=str, choices=['hand', 'controller'], default='hand', help='XR device input tracking source')
    parser.add_argument('--display-mode', type=str, choices=['immersive', 'ego', 'pass-through'], default='immersive', help='XR device display mode')
    parser.add_argument('--img-server-ip', type=str, default='192.168.123.232', help='IP address of image server')
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
        xr_need_local_img = not (args.display_mode == 'pass-through' or camera_config['head_camera']['enable_webrtc'])

        # televuer wrapper
        tv_wrapper = TeleVuerWrapper(
            use_hand_tracking=args.input_mode == "hand",
            binocular=camera_config['head_camera']['binocular'],
            img_shape=camera_config['head_camera']['image_shape'],
            display_mode=args.display_mode,
            zmq=camera_config['head_camera']['enable_zmq'],
            webrtc=camera_config['head_camera']['enable_webrtc'],
            webrtc_url=f"https://{args.img_server_ip}:{camera_config['head_camera']['webrtc_port']}/offer",
        )

        frame_count = 0
        loop_hz = 0.0

        while not STOP:
            start_time = time.time()

            # stream image to XR if needed
            if camera_config['head_camera']['enable_zmq'] and xr_need_local_img:
                head_img, _ = img_client.get_head_frame()
                tv_wrapper.render_to_xr(head_img)

            # get tele data
            tele_data = tv_wrapper.get_tele_data()

            # build and refresh display
            frame_count += 1
            display = build_display(tele_data, args.input_mode, loop_hz)
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
        print("✅ Exiting program.")
        exit(0)
