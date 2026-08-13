#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
ACCESS_MODE="${MITIGATE_ACCESS_MODE:-local}"

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo/root" >&2
  exit 1
}

[[ -x "$ROOT/agent/bootstrap/bootstrap_mitigate_ai.sh" || -f "$ROOT/agent/bootstrap/bootstrap_mitigate_ai.sh" ]] || {
  echo "ERROR: bootstrap_mitigate_ai.sh not found under $ROOT" >&2
  exit 1
}

bash "$ROOT/agent/bootstrap/bootstrap_mitigate_ai.sh"

if [[ "$ACCESS_MODE" != "local" ]]; then
  [[ -x "$ROOT/agent/bootstrap/configure_remote_access.sh" || -f "$ROOT/agent/bootstrap/configure_remote_access.sh" ]] || {
    echo "ERROR: configure_remote_access.sh not found under $ROOT" >&2
    exit 1
  }

  MITIGATE_ROOT="$ROOT" \
    MITIGATE_ACCESS_MODE="$ACCESS_MODE" \
    MITIGATE_ACCESS_HOST="${MITIGATE_ACCESS_HOST:-}" \
    MITIGATE_ACCESS_USERNAME="${MITIGATE_ACCESS_USERNAME:-admin}" \
    MITIGATE_ACCESS_PASSWORD="${MITIGATE_ACCESS_PASSWORD:-}" \
    MITIGATE_CANVAS_UPSTREAM="${MITIGATE_CANVAS_UPSTREAM:-http://127.0.0.1:8000}" \
    MITIGATE_NGINX_EXISTING_SITE="${MITIGATE_NGINX_EXISTING_SITE:-/etc/nginx/sites-available/mitigate}" \
    bash "$ROOT/agent/bootstrap/configure_remote_access.sh"
fi

printf '\nMITIGATE AI INSTALLATION COMPLETE\n'
printf 'Access mode: %s\n' "$ACCESS_MODE"
