#!/usr/bin/env python3
"""
Quick diagnostic & viewer for the teleimager camera streams.
Uses ImageClient directly (same as the original teleop) — works for ZMQ streams.
"""

import argparse
import time
import cv2
from teleimager.image_client import ImageClient

parser = argparse.ArgumentParser()
parser.add_argument("--host", type=str, default="192.168.1.232")
parser.add_argument("--request-port", type=int, default=60000)
args = parser.parse_args()

# ── connect & dump config ──────────────────────────────────
client = ImageClient(host=args.host, request_port=args.request_port)
cam_config = client.get_cam_config()

print("\n══════ Camera Config from Server ══════")
for name in ("head_camera", "left_wrist_camera", "right_wrist_camera"):
    cfg = cam_config.get(name, {})
    zmq = cfg.get("enable_zmq", False)
    webrtc = cfg.get("enable_webrtc", False)
    shape = cfg.get("image_shape", "?")
    zmq_port = cfg.get("zmq_port", "?")
    webrtc_port = cfg.get("webrtc_port", "?")
    print(f"  {name:25s}  zmq={zmq} (port {zmq_port})  webrtc={webrtc} (port {webrtc_port})  shape={shape}")

# ── build list of cameras we can actually read (ZMQ only) ──
CAMERAS = {
    "head_camera": client.get_head_frame,
    "left_wrist_camera": client.get_left_wrist_frame,
    "right_wrist_camera": client.get_right_wrist_frame,
}

readable = {}
for name, getter in CAMERAS.items():
    cfg = cam_config.get(name, {})
    if cfg.get("enable_zmq", False):
        readable[name] = getter
    else:
        note = "webrtc-only (cannot read locally)" if cfg.get("enable_webrtc") else "disabled"
        print(f"  ⚠  {name}: {note} — skipping")

if not readable:
    print("\n❌ No cameras have ZMQ enabled — nothing to display.")
    print("   If cameras use WebRTC only, the stream goes directly to the headset")
    print("   and cannot be captured by Python. Enable ZMQ on the image server to")
    print("   read frames locally.")
    client.close()
    exit(1)

print(f"\nShowing {len(readable)} camera(s). Press 'q' to quit.\n")

try:
    while True:
        for name, getter in readable.items():
            img, fps = getter()
            if img is not None:
                stats = f"shape={img.shape} dtype={img.dtype} min={img.min()} max={img.max()} fps={fps:.1f}"
                cv2.putText(img, stats, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                cv2.imshow(name, img)
            else:
                print(f"  {name}: frame is None")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        time.sleep(0.002)
except KeyboardInterrupt:
    pass
finally:
    client.close()
    cv2.destroyAllWindows()
    print("Done.")
