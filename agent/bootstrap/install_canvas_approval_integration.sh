#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
INSTALLER="$ROOT/agent/bootstrap/install_canvas_ui_integration.sh"

[[ -f "$INSTALLER" ]] || {
  echo "ERROR: unified Canvas integration installer missing" >&2
  exit 1
}

if [[ "$EUID" -eq 0 ]]; then
  exec bash "$INSTALLER"
fi

exec sudo bash "$INSTALLER"
