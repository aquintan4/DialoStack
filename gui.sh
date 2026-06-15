#!/usr/bin/env bash
# Arranca la GUI de DialoStack: rosbridge + servidor web/API.
#   ./gui.sh          modo producción (build estático + server.py)
#   ./gui.sh --dev    modo desarrollo (Vite con hot reload + API aparte)
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUI_DIR="$SCRIPT_DIR/dialostack_gui"
BRIDGE_PORT=9090
WEB_PORT=5173
API_PORT=5175   # Solo en dev; en producción /api comparte WEB_PORT
BRIDGE_LOG=/tmp/dialostack_bridge.log

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

# ─── Secretos locales (.env, fuera de git) ──────────────────────────────────
# Permite definir GEMINI_API_KEY y similares sin exportarlas a mano:
#   echo 'GEMINI_API_KEY=...' > .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a; source "$SCRIPT_DIR/.env"; set +a
  echo -e "  Secretos:  ${GREEN}.env cargado${NC}"
fi

# ─── Source ROS 2 ───────────────────────────────────────────────────────────
if   [ -f /opt/ros/jazzy/setup.bash ];  then source /opt/ros/jazzy/setup.bash
elif [ -f /opt/ros/humble/setup.bash ]; then source /opt/ros/humble/setup.bash
else
  echo -e "${RED}ERROR: ROS 2 installation not found${NC}" >&2
  exit 1
fi

# ─── Workspace overlay (única detección, reutilizada después) ───────────────
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
  echo -e "  Run: cd ~/Desktop/dialostack_ws && colcon build --symlink-install"
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

if [ ! -d "$GUI_DIR/node_modules" ]; then
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
# rosbridge necesita el Python del sistema: quitamos el venv del PATH para que
# no interfiera, pero mantenemos el overlay del workspace para que pueda
# importar los tipos de mensaje propios (ros2_dialog_interfaces).
echo -e "${BLUE}[1/2]${NC} rosbridge_websocket  →  ws://localhost:${BRIDGE_PORT}  (log: ${BRIDGE_LOG})"
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
  # Vite sirve el frontend; server.py atiende /api en otro puerto
  # (vite.config.js proxya /api → localhost:$API_PORT).
  echo -e "${BLUE}[2/3]${NC} API server (engine)  →  http://localhost:${API_PORT}"
  python3 "$GUI_DIR/server.py" --api-only $API_PORT &
  sleep 0.5
  echo -e "${BLUE}[3/3]${NC} Web server (Vite)    →  http://localhost:${WEB_PORT}"
  (cd "$GUI_DIR" && npm run dev -- --port $WEB_PORT --host) &
else
  # Producción: un único servidor para estáticos y /api.
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
