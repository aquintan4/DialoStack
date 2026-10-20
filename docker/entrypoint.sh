#!/usr/bin/env bash
# Source ROS and the DialoStack workspace, then run the given command
# (the GUI by default, or e.g. `ros2 launch ros2_dialog_manager main.launch.py`).
set -e
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source /opt/dialostack/install/setup.bash
exec "$@"
