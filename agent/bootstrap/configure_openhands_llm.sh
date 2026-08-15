#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ENV="${MITIGATE_RUNTIME_ENV:-/etc/mitigate-ai/runtime.env}"
CANVAS_ENV="${MITIGATE_CANVAS_ENV:-/etc/mitigate-ai/agent-canvas.env}"
LLM_MODEL="${MITIGATE_OPENHANDS_LLM_MODEL:-gpt-5.5}"
LLM_AUTH_TYPE="${MITIGATE_OPENHANDS_LLM_AUTH_TYPE:-api_key}"
LLM_PROFILE="${MITIGATE_OPENHANDS_LLM_PROFILE:-default}"
LLM_BASE_URL="${MITIGATE_OPENHANDS_LLM_BASE_URL:-}"
LLM_API_KEY_OVERRIDE="${MITIGATE_OPENHANDS_LLM_API_KEY:-}"
COMPOSE_DIR="${MITIGATE_AGENT_CANVAS_COMPOSE_DIR:-$ROOT/agent/deploy/agent-canvas}"

log() { printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "Run with sudo/root."
[[ -f "$RUNTIME_ENV" ]] || die "Runtime env not found: $RUNTIME_ENV"
[[ -f "$CANVAS_ENV" ]] || die "Canvas env not found: $CANVAS_ENV"
[[ -d "$COMPOSE_DIR" ]] || die "Canvas compose directory not found: $COMPOSE_DIR"
[[ "$LLM_PROFILE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || die "Invalid OpenHands LLM profile name: $LLM_PROFILE"
if [[ -n "$LLM_BASE_URL" ]]; then
    [[ "$LLM_BASE_URL" == https://* || "$LLM_BASE_URL" == http://127.0.0.1/* || "$LLM_BASE_URL" == http://localhost/* ]] \
        || die "LLM base URL must use HTTPS (or loopback HTTP)."
fi

get_env_value() {
  local file="$1" key="$2"
  awk -F= -v key="$key" '$1==key {sub(/^[^=]*=/, ""); gsub(/^["'\'' ]+|["'\'' ]+$/, ""); print; exit}' "$file"
}

LLM_KEY="$LLM_API_KEY_OVERRIDE"
if [[ -z "$LLM_KEY" ]]; then
    LLM_KEY="$(get_env_value "$RUNTIME_ENV" OPENAI_API_KEY)"
fi
[[ -n "$LLM_KEY" ]] || die "No LLM API key supplied. Set MITIGATE_OPENHANDS_LLM_API_KEY or OPENAI_API_KEY in $RUNTIME_ENV"

cd "$COMPOSE_DIR"

log "Waiting for Agent Canvas readiness"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" == 1 ]] || die "Agent Canvas did not become ready"

CONTAINER_ID="$(docker compose --env-file "$CANVAS_ENV" ps -q agent-canvas)"
[[ -n "$CONTAINER_ID" ]] || die "Agent Canvas container not found"

log "Persisting and activating OpenHands LLM profile through the Agent Server API"
docker exec -i \
  -e MITIGATE_LLM_KEY="$LLM_KEY" \
  -e MITIGATE_LLM_MODEL="$LLM_MODEL" \
  -e MITIGATE_LLM_AUTH_TYPE="$LLM_AUTH_TYPE" \
  -e MITIGATE_LLM_PROFILE="$LLM_PROFILE" \
  -e MITIGATE_LLM_BASE_URL="$LLM_BASE_URL" \
  "$CONTAINER_ID" \
  python3 - <<'PY_INNER'
import json
import os
import urllib.request

base = "http://127.0.0.1:18000"

profile = os.environ["MITIGATE_LLM_PROFILE"]
model = os.environ["MITIGATE_LLM_MODEL"]
auth_type = os.environ["MITIGATE_LLM_AUTH_TYPE"]
api_key = os.environ["MITIGATE_LLM_KEY"]
base_url = os.environ.get("MITIGATE_LLM_BASE_URL", "").strip() or None

llm = {
    "model": model,
    "api_key": api_key,
    "auth_type": auth_type,
}
if base_url:
    llm["base_url"] = base_url

save_payload = {
    "llm": llm,
    "include_secrets": True,
}

save_req = urllib.request.Request(
    f"{base}/api/profiles/{profile}",
    data=json.dumps(save_payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(save_req, timeout=30) as response:
    if response.status != 201:
        raise SystemExit(
            f"POST /api/profiles/{profile} returned HTTP {response.status}"
        )

activate_req = urllib.request.Request(
    f"{base}/api/profiles/{profile}/activate",
    data=b"",
    method="POST",
)

with urllib.request.urlopen(activate_req, timeout=30) as response:
    if response.status != 200:
        raise SystemExit(
            f"POST /api/profiles/{profile}/activate returned HTTP {response.status}"
        )

with urllib.request.urlopen(
    f"{base}/api/profiles",
    timeout=10,
) as response:
    profiles_data = json.load(response)

with urllib.request.urlopen(
    f"{base}/api/settings",
    timeout=10,
) as response:
    settings_data = json.load(response)

profiles = profiles_data.get("profiles") or []
matched = next(
    (item for item in profiles if item.get("name") == profile),
    None,
)

if not matched:
    raise SystemExit("Persisted LLM profile is missing")

if matched.get("model") != model:
    raise SystemExit(
        "Persisted LLM profile model does not match requested model"
    )

if matched.get("api_key_set") is not True:
    raise SystemExit("Persisted LLM profile API key is not set")

if profiles_data.get("active_profile") != profile:
    raise SystemExit("Persisted LLM profile is not active")

active_llm = (settings_data.get("agent_settings") or {}).get("llm") or {}

if settings_data.get("active_profile") != profile:
    raise SystemExit(
        "OpenHands settings active_profile does not match requested profile"
    )

if settings_data.get("llm_api_key_is_set") is not True:
    raise SystemExit(
        "OpenHands settings do not report an LLM API key"
    )

if active_llm.get("model") != model:
    raise SystemExit("Active LLM model does not match requested model")

if active_llm.get("auth_type") != auth_type:
    raise SystemExit(
        "Active LLM auth type does not match requested auth type"
    )

if base_url and str(active_llm.get("base_url") or "").rstrip("/") != base_url.rstrip("/"):
    raise SystemExit("Active LLM base URL does not match requested base URL")

print("OPENHANDS_LLM_CONFIGURATION=OK")
print("LLM_PROFILE=" + profile)
print("LLM_MODEL=" + model)
print("LLM_AUTH_TYPE=" + auth_type)
print("LLM_BASE_URL=" + (base_url or "<DEFAULT>"))
print("LLM_API_KEY=<CONFIGURED_REDACTED>")
PY_INNER

unset LLM_KEY LLM_API_KEY_OVERRIDE

log "OpenHands LLM profile configuration complete"
