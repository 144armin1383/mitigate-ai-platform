#!/usr/bin/env bash
set -euo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
DEPLOY_DIR="$ROOT/agent/deploy/agent-canvas"
ENV_FILE="${MITIGATE_AGENT_CANVAS_ENV:-/etc/mitigate-ai/agent-canvas.env}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required. Install Docker Engine before running this helper."
  exit 20
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose v2 plugin is required."
  exit 21
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: missing $ENV_FILE"
  echo "Copy $DEPLOY_DIR/agent-canvas.env.example and replace CHANGE_ME first."
  exit 22
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -z "${LOCAL_BACKEND_API_KEY:-}" ] || [ "$LOCAL_BACKEND_API_KEY" = "CHANGE_ME" ]; then
  echo "ERROR: LOCAL_BACKEND_API_KEY must be configured."
  exit 23
fi

mkdir -p "${MITIGATE_OPENHANDS_STATE_PATH:-/srv/mitigate/data/openhands}"

cd "$DEPLOY_DIR"
docker compose --env-file "$ENV_FILE" pull
docker compose --env-file "$ENV_FILE" up -d

echo "Agent Canvas started on http://127.0.0.1:${MITIGATE_AGENT_CANVAS_PORT:-8000}"
