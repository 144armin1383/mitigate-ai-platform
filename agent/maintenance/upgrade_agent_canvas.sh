#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
ENV_FILE="${MITIGATE_CANVAS_ENV:-/etc/mitigate-ai/agent-canvas.env}"
COMPOSE_DIR="${MITIGATE_AGENT_CANVAS_COMPOSE_DIR:-$ROOT/agent/deploy/agent-canvas}"
REQUESTED_TARGET="${1:-${MITIGATE_AGENT_CANVAS_TARGET_VERSION:-latest}}"
TARGET_VERSION="$REQUESTED_TARGET"
MIN_FREE_GB="${MITIGATE_CANVAS_UPGRADE_MIN_FREE_GB:-12}"
READY_URL="${MITIGATE_AGENT_CANVAS_READY_URL:-http://127.0.0.1:8000/ready}"

log() {
    printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
[[ -f "$ENV_FILE" ]] || die "Missing Canvas environment file: $ENV_FILE"
[[ -d "$COMPOSE_DIR" ]] || die "Missing Canvas compose directory: $COMPOSE_DIR"

get_env() {
    local key="$1"

    awk -F= -v key="$key" '
        $1 == key {
            sub(/^[^=]*=/, "")
            gsub(/^["'\'' ]+|["'\'' ]+$/, "")
            print
            exit
        }
    ' "$ENV_FILE"
}

set_env() {
    local key="$1"
    local value="$2"

    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

CURRENT_VERSION="$(get_env MITIGATE_AGENT_CANVAS_VERSION)"
CURRENT_VERSION="${CURRENT_VERSION:-1.6.1}"

FREE_KB="$(df -Pk / | awk 'NR==2 {print $4}')"
REQUIRED_KB=$((MIN_FREE_GB * 1024 * 1024))

log "Preflight"
echo "Current version: $CURRENT_VERSION"
echo "Target version:  $TARGET_VERSION"
echo "Minimum free:    ${MIN_FREE_GB}GB"
echo "Available:       $((FREE_KB / 1024 / 1024))GB"

if (( FREE_KB < REQUIRED_KB )); then
    die "Insufficient disk space. Upgrade not started."
fi

BACKUP="$(mktemp /tmp/mitigate-agent-canvas-env.XXXXXX)"
cp -a "$ENV_FILE" "$BACKUP"

rollback() {
    local exit_code=$?

    if [[ "$exit_code" -eq 0 ]]; then
        rm -f "$BACKUP"
        return
    fi

    trap - EXIT

    echo
    echo "UPGRADE_FAILED=yes"
    echo "ROLLBACK_VERSION=$CURRENT_VERSION"

    cp -a "$BACKUP" "$ENV_FILE"

    cd "$COMPOSE_DIR"

    MITIGATE_AGENT_CANVAS_VERSION="$CURRENT_VERSION" \
      docker compose \
        --env-file "$ENV_FILE" \
        up -d --force-recreate agent-canvas || true

    rm -f "$BACKUP"

    exit "$exit_code"
}

trap rollback EXIT

cd "$COMPOSE_DIR"

log "Pulling Agent Canvas $TARGET_VERSION"

MITIGATE_AGENT_CANVAS_VERSION="$TARGET_VERSION" \
docker compose \
  --env-file "$ENV_FILE" \
  pull agent-canvas

CURRENT_CONTAINER_ID="$(
    docker compose \
      --env-file "$ENV_FILE" \
      ps -q agent-canvas 2>/dev/null || true
)"

CURRENT_IMAGE_ID=""

if [[ -n "$CURRENT_CONTAINER_ID" ]]; then
    CURRENT_IMAGE_ID="$(
        docker inspect \
          --format '{{.Image}}' \
          "$CURRENT_CONTAINER_ID"
    )"
fi

TARGET_IMAGE_ID="$(
    docker image inspect \
      "ghcr.io/openhands/agent-canvas:$TARGET_VERSION" \
      --format '{{.Id}}'
)"

if [[ -n "$CURRENT_IMAGE_ID" && "$CURRENT_IMAGE_ID" == "$TARGET_IMAGE_ID" ]]; then
    log "Agent Canvas already uses the latest target image"

    trap - EXIT
    rm -f "$BACKUP"

    echo "AGENT_CANVAS_ALREADY_CURRENT=yes"
    exit 0
fi

log "Starting target version"

MITIGATE_AGENT_CANVAS_VERSION="$TARGET_VERSION" \
docker compose \
  --env-file "$ENV_FILE" \
  up -d --force-recreate agent-canvas

log "Waiting for Canvas readiness"

READY=0

for _ in $(seq 1 90); do
    if curl -fsS --max-time 5 "$READY_URL" >/dev/null 2>&1; then
        READY=1
        break
    fi

    sleep 2
done

[[ "$READY" -eq 1 ]] || die "Canvas readiness check failed."

log "Re-applying persistent OpenHands LLM profile"

MITIGATE_ROOT="$ROOT" \
bash "$ROOT/agent/bootstrap/configure_openhands_llm.sh"

log "Performing functional configuration verification"

CONTAINER_ID="$(
    MITIGATE_AGENT_CANVAS_VERSION="$TARGET_VERSION" \
    docker compose \
      --env-file "$ENV_FILE" \
      ps -q agent-canvas
)"

[[ -n "$CONTAINER_ID" ]] || die "Canvas container not found."

docker exec -i "$CONTAINER_ID" python3 - <<'PY'
import json
import urllib.request

base = "http://127.0.0.1:18000"

with urllib.request.urlopen(base + "/api/settings", timeout=10) as r:
    settings = json.load(r)

with urllib.request.urlopen(base + "/api/profiles", timeout=10) as r:
    profiles = json.load(r)

if settings.get("llm_api_key_is_set") is not True:
    raise SystemExit("LLM API key verification failed")

active = settings.get("active_profile")

if not active:
    raise SystemExit("No active LLM profile")

profile = next(
    (
        item
        for item in profiles.get("profiles", [])
        if item.get("name") == active
    ),
    None,
)

if profile is None:
    raise SystemExit("Active profile missing")

if profile.get("api_key_set") is not True:
    raise SystemExit("Active profile API key missing")

print("CANVAS_API=OK")
print("ACTIVE_PROFILE=" + active)
print("LLM_API_KEY=OK")
PY

IMAGE="$(
    docker inspect \
      --format '{{.Config.Image}}' \
      "$CONTAINER_ID"
)"

IMAGE_ID="$(
    docker inspect \
      --format '{{.Image}}' \
      "$CONTAINER_ID"
)"

LABEL_VERSION="$(
    docker image inspect \
      "$IMAGE_ID" \
      --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' \
      2>/dev/null || true
)"

LABEL_VERSION="${LABEL_VERSION#v}"

RESOLVED_VERSION="$TARGET_VERSION"

if [[ "$REQUESTED_TARGET" == "latest" ]]; then
    if [[ -z "$LABEL_VERSION" || "$LABEL_VERSION" == "<no value>" ]]; then
        die "Latest Canvas image does not expose a stable version label."
    fi

    RESOLVED_VERSION="$LABEL_VERSION"
fi

log "Upgrade passed all checks"

set_env MITIGATE_AGENT_CANVAS_VERSION "$RESOLVED_VERSION"

trap - EXIT
rm -f "$BACKUP"

echo
echo "=================================================="
echo "AGENT CANVAS UPGRADE SUCCESSFUL"
echo "=================================================="
echo "Previous: $CURRENT_VERSION"
echo "Target:   $REQUESTED_TARGET"
echo "Resolved: $RESOLVED_VERSION"
echo "Image:    $IMAGE"
echo "Ready:    yes"
echo "LLM:      verified"
