#!/usr/bin/env bash
# Starts the DialoStack GUI: rosbridge + web/API server.
#   ./gui.sh          production mode (static build + server.py)
#   ./gui.sh --dev    development mode (Vite with hot reload + separate API)
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUI_DIR="$SCRIPT_DIR/dialostack_gui"
BRIDGE_PORT=9090
WEB_PORT=5173
API_PORT=5175   # Dev only; in production /api shares WEB_PORT
BRIDGE_LOG=/tmp/dialostack/logs/rosbridge.log

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}"
echo "  ██████╗ ██╗ █████╗ ██╗      ██████╗ ███████╗████████╗ █████╗  ██████╗██╗  ██╗"
echo "  ██╔══██╗██║██╔══██╗██║     ██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██╔════╝██║ ██╔╝"
echo "  ██║  ██║██║███████║██║     ██║   ██║███████╗   ██║   ███████║██║     █████╔╝ "
echo "  ██║  ██║██║██╔══██║██║     ██║   ██║╚════██║   ██║   ██╔══██║██║     ██╔═██╗ "
echo "  ██████╔╝██║██║  ██║███████╗╚██████╔╝███████║   ██║   ██║  ██║╚██████╗██║  ██╗"
echo "  ╚═════╝ ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝"
echo -e "${NC}  GUI v1.0"
echo ""

# ─── Local secrets (.env, kept out of git) ──────────────────────────────────
# Lets you define GEMINI_API_KEY and similar without exporting them by hand:
#   echo 'GEMINI_API_KEY=...' > .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a; source "$SCRIPT_DIR/.env"; set +a
  echo -e "  Secrets:   ${GREEN}.env loaded${NC}"
fi

# ─── Source ROS 2 ───────────────────────────────────────────────────────────
if   [ -f /opt/ros/lyrical/setup.bash ]; then source /opt/ros/lyrical/setup.bash
elif [ -f /opt/ros/jazzy/setup.bash ];  then source /opt/ros/jazzy/setup.bash
elif [ -f /opt/ros/humble/setup.bash ]; then source /opt/ros/humble/setup.bash
else
  echo -e "${RED}ERROR: ROS 2 installation not found${NC}" >&2
  exit 1
fi

# ─── Workspace overlay (detected once, reused below) ────────────────────────
WS_SETUP=""
for _candidate in \
  "$SCRIPT_DIR/install/setup.bash" \
  "$(realpath "$SCRIPT_DIR/../dialostack_ws/install/setup.bash" 2>/dev/null || true)"
do
  [ -n "$_candidate" ] && [ -f "$_candidate" ] && { WS_SETUP="$_candidate"; break; }
done

if [ -n "$WS_SETUP" ]; then
  source "$WS_SETUP"
  echo -e "  Workspace: ${GREEN}${WS_SETUP}${NC}"
else
  echo -e "  ${YELLOW}WARNING: No compiled workspace found — ros2 launch may fail.${NC}"
  echo -e "  Run 'colcon build --symlink-install' from your workspace root, then source install/setup.bash"
  echo ""
fi

# ─── Cleanup on exit ────────────────────────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}Stopping DialoStack GUI...${NC}"
  kill $(jobs -p) 2>/dev/null || true
  wait 2>/dev/null || true
  echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT INT TERM

# ─── Dev vs production mode ─────────────────────────────────────────────────
DEV_MODE=false
[ "${1:-}" = "--dev" ] && DEV_MODE=true

if [ "$DEV_MODE" = true ]; then
  echo -e "  Mode: ${YELLOW}development${NC} (hot reload)"
else
  echo -e "  Mode: ${GREEN}production${NC}"
fi
echo ""

# ─── Node dependencies / build ──────────────────────────────────────────────
need_npm() {
  if ! command -v npm &>/dev/null; then
    echo -e "${RED}ERROR: npm not found. Install with: sudo apt install nodejs npm${NC}" >&2
    exit 1
  fi
}

# node_modules is only needed to develop or to build: with a prebuilt dist/
# (e.g. the Docker image) production mode does not need npm.
if [ ! -d "$GUI_DIR/node_modules" ] && { [ "$DEV_MODE" = true ] || [ ! -d "$GUI_DIR/dist" ]; }; then
  need_npm
  echo -e "${YELLOW}[DEPS]${NC} Installing npm dependencies..."
  (cd "$GUI_DIR" && npm install --silent)
fi

if [ "$DEV_MODE" = false ] && [ ! -d "$GUI_DIR/dist" ]; then
  need_npm
  echo -e "${YELLOW}[BUILD]${NC} First run — building GUI..."
  (cd "$GUI_DIR" && npm run build --silent)
  echo -e "${GREEN}[BUILD]${NC} Done."
  echo ""
fi

# ─── 1. rosbridge ───────────────────────────────────────────────────────────
# rosbridge needs the system Python: drop the venv from PATH so it does not
# interfere, but keep the workspace overlay so it can import the project's own
# message types (ros2_dialog_interfaces).
echo -e "${BLUE}[1/2]${NC} rosbridge_websocket  →  ws://localhost:${BRIDGE_PORT}  (log: ${BRIDGE_LOG})"
mkdir -p "$(dirname "$BRIDGE_LOG")"
SYSTEM_PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "dialostack_venv" | tr '\n' ':' | sed 's/:$//')

BRIDGE_WS_SOURCE=""
[ -n "$WS_SETUP" ] && BRIDGE_WS_SOURCE="source $WS_SETUP &&"

env -i HOME="$HOME" PATH="$SYSTEM_PATH" ROS_DISTRO="${ROS_DISTRO:-jazzy}" \
  bash -c "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && \
    $BRIDGE_WS_SOURCE \
    ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=$BRIDGE_PORT" \
  >"$BRIDGE_LOG" 2>&1 &

sleep 1

# ─── 2. Web / API server ────────────────────────────────────────────────────
if [ "$DEV_MODE" = true ]; then
  # Vite serves the frontend; server.py handles /api on another port
  # (vite.config.js proxies /api to localhost:$API_PORT).
  echo -e "${BLUE}[2/3]${NC} API server (engine)  →  http://localhost:${API_PORT}"
  python3 "$GUI_DIR/server.py" --api-only $API_PORT &
  sleep 0.5
  echo -e "${BLUE}[3/3]${NC} Web server (Vite)    →  http://localhost:${WEB_PORT}"
  (cd "$GUI_DIR" && npm run dev -- --port $WEB_PORT --host) &
else
  # Production: a single server for static files and /api.
  echo -e "${BLUE}[2/2]${NC} Web server           →  http://localhost:${WEB_PORT}"
  python3 "$GUI_DIR/server.py" $WEB_PORT "$GUI_DIR/dist" &
fi

sleep 1

# ─── Open browser ───────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}Ready!${NC} → http://localhost:${WEB_PORT}"
echo -e "       Press ${YELLOW}Ctrl+C${NC} to stop.\n"
xdg-open "http://localhost:${WEB_PORT}" 2>/dev/null || true

wait
