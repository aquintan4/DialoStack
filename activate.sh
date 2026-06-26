# DialoStack environment — SOURCE this file (do not execute it):
#
#     source src/DialoStack/activate.sh
#
# Edit the two variables below once for your machine. Nothing is auto-detected
# or searched for on your system.

# ── edit these ───────────────────────────────────────────────────────────────

# ROS 2 distro installed under /opt/ros/<distro>.
: "${ROS_DISTRO:=jazzy}"

# Absolute path to the Python venv where you ran the `pip install -r ...` steps.
# Leave EMPTY ("") if you installed the deps into the same Python that ROS uses.
DIALOSTACK_VENV=""

# ─────────────────────────────────────────────────────────────────────────────

# 1) ROS 2.
if [ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]; then
  source "/opt/ros/${ROS_DISTRO}/setup.bash"
else
  echo "DialoStack: /opt/ros/${ROS_DISTRO}/setup.bash not found — set ROS_DISTRO at the top of activate.sh" >&2
fi

# 2) Workspace overlay. This file lives at <workspace>/src/DialoStack/, so the
#    workspace root is two levels up. Sourced only if it has been built.
_dialostack_ws="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
if [ -f "${_dialostack_ws}/install/setup.bash" ]; then
  source "${_dialostack_ws}/install/setup.bash"
fi

# 3) venv. Sourcing the overlay reorders PYTHONPATH, so the venv's packages must
#    go back in front or the ROS nodes fail with ModuleNotFoundError
#    (sounddevice, torch, faster-whisper...). Only touched if you set the path.
if [ -n "${DIALOSTACK_VENV}" ]; then
  [ -f "${DIALOSTACK_VENV}/bin/activate" ] && source "${DIALOSTACK_VENV}/bin/activate"
  for _sp in "${DIALOSTACK_VENV}"/lib/python*/site-packages; do
    [ -d "${_sp}" ] && export PYTHONPATH="${_sp}:${PYTHONPATH:-}"
  done
fi

# 4) Where the TTS node looks for Piper voices (scripts/download_models.sh fills it).
export DIALOSTACK_MODELS_DIR="${DIALOSTACK_MODELS_DIR:-$HOME/.local/share/dialostack/models}"

echo "DialoStack env ready — ROS ${ROS_DISTRO}, models ${DIALOSTACK_MODELS_DIR}"
