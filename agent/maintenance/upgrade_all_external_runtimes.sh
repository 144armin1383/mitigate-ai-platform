#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"

[[ "$EUID" -eq 0 ]] || {
    echo "ERROR: Run with sudo/root." >&2
    exit 1
}

exec python3 \
  "$ROOT/agent/maintenance/upgrade_managed_components.py"
