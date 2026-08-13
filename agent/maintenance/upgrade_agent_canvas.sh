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
CURRENT_VERSION="${CURRENT_VERSION:-1.13.0}"

resolve_latest_version() {
    python3 - <<'PY_RESOLVE'
import json
import platform
import urllib.parse
import urllib.request

repo = "openhands/agent-canvas"
registry = "https://ghcr.io"

token_url = (
    registry
    + "/token?service=ghcr.io&scope="
    + urllib.parse.quote(
        f"repository:{repo}:pull",
        safe=":",
    )
)

with urllib.request.urlopen(token_url, timeout=20) as response:
    token = json.load(response)["token"]

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": ",".join([
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]),
}

def get_json(url, extra_headers=None):
    request_headers = dict(headers)
    if extra_headers:
        request_headers.update(extra_headers)

    request = urllib.request.Request(
        url,
        headers=request_headers,
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

manifest = get_json(
    f"{registry}/v2/{repo}/manifests/latest"
)

media_type = manifest.get("mediaType", "")

if "index" in media_type or "manifest.list" in media_type:
    machine = platform.machine().lower()

    arch_map = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }

    architecture = arch_map.get(machine, machine)

    selected = None

    for item in manifest.get("manifests", []):
        target = item.get("platform") or {}

        if (
            target.get("os") == "linux"
            and target.get("architecture") == architecture
        ):
            selected = item
            break

    if selected is None:
        raise SystemExit(
            f"No linux/{architecture} Canvas manifest found"
        )

    digest = selected["digest"]

    manifest = get_json(
        f"{registry}/v2/{repo}/manifests/{digest}"
    )

config_digest = manifest["config"]["digest"]

config = get_json(
    f"{registry}/v2/{repo}/blobs/{config_digest}"
)

labels = (
    config
    .get("config", {})
    .get("Labels", {})
    or {}
)

version = labels.get(
    "org.opencontainers.image.version"
)

if not version:
    raise SystemExit(
        "Agent Canvas latest image has no OCI version label"
    )

print(version.lstrip("v"))
PY_RESOLVE
}

if [[ "$REQUESTED_TARGET" == "latest" ]]; then
    log "Resolving latest Agent Canvas stable image metadata"

    TARGET_VERSION="$(resolve_latest_version)"

    echo "Current version: $CURRENT_VERSION"
    echo "Latest version:  $TARGET_VERSION"

    if [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
        echo "AGENT_CANVAS_ALREADY_CURRENT=yes"
        echo "AGENT_CANVAS_VERSION=$CURRENT_VERSION"
        exit 0
    fi
fi

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

if [[ -n "$LABEL_VERSION" && "$LABEL_VERSION" != "<no value>" ]]; then
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
