LOG_FILE="run_teleop_$(date +%Y%m%d_%H%M%S).log"
echo "Logging stderr to $LOG_FILE"
python teleop/teleop_tele_xarm.py --input-mode controller --display-mode immersive --img-server-ip 192.168.1.232 --opposite 2> >(tee -a "$LOG_FILE" >&2)

# pass-through, immersive-wrist, immersive