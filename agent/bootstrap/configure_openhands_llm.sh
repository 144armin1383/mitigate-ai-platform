#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ENV="${MITIGATE_RUNTIME_ENV:-/etc/mitigate-ai/runtime.env}"
CANVAS_ENV="${MITIGATE_CANVAS_ENV:-/etc/mitigate-ai/agent-canvas.env}"
LLM_MODEL="${MITIGATE_OPENHANDS_LLM_MODEL:-gpt-5.5}"
LLM_AUTH_TYPE="${MITIGATE_OPENHANDS_LLM_AUTH_TYPE:-api_key}"
COMPOSE_DIR="${MITIGATE_AGENT_CANVAS_COMPOSE_DIR:-$ROOT/agent/deploy/agent-canvas}"

log() { printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "Run with sudo/root."
[[ -f "$RUNTIME_ENV" ]] || die "Runtime env not found: $RUNTIME_ENV"
[[ -f "$CANVAS_ENV" ]] || die "Canvas env not found: $CANVAS_ENV"
[[ -d "$COMPOSE_DIR" ]] || die "Canvas compose directory not found: $COMPOSE_DIR"

get_env_value() {
  local file="$1" key="$2"
  awk -F= -v key="$key" '$1==key {sub(/^[^=]*=/, ""); gsub(/^["'\'' ]+|["'\'' ]+$/, ""); print; exit}' "$file"
}

OPENAI_KEY="$(get_env_value "$RUNTIME_ENV" OPENAI_API_KEY)"
[[ -n "$OPENAI_KEY" ]] || die "OPENAI_API_KEY is missing from $RUNTIME_ENV"

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

log "Persisting OpenHands LLM settings through the Agent Server API"
docker exec -i \
  -e MITIGATE_LLM_KEY="$OPENAI_KEY" \
  -e MITIGATE_LLM_MODEL="$LLM_MODEL" \
  -e MITIGATE_LLM_AUTH_TYPE="$LLM_AUTH_TYPE" \
  "$CONTAINER_ID" \
  python3 - <<'PY'
import json
import os
import urllib.request

payload = {
    "agent_settings_diff": {
        "llm": {
            "model": os.environ["MITIGATE_LLM_MODEL"],
            "api_key": os.environ["MITIGATE_LLM_KEY"],
            "auth_type": os.environ["MITIGATE_LLM_AUTH_TYPE"],
        }
    }
}

req = urllib.request.Request(
    "http://127.0.0.1:18000/api/settings",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
with urllib.request.urlopen(req, timeout=30) as response:
    if response.status != 200:
        raise SystemExit(f"PATCH /api/settings returned HTTP {response.status}")

with urllib.request.urlopen("http://127.0.0.1:18000/api/settings", timeout=10) as response:
    data = json.load(response)

llm = (data.get("agent_settings") or {}).get("llm") or {}
if llm.get("model") != os.environ["MITIGATE_LLM_MODEL"]:
    raise SystemExit("Persisted LLM model does not match requested model")
if llm.get("auth_type") != os.environ["MITIGATE_LLM_AUTH_TYPE"]:
    raise SystemExit("Persisted LLM auth type does not match requested auth type")
if not llm.get("api_key"):
    raise SystemExit("Persisted LLM API key is missing")

print("OPENHANDS_LLM_CONFIGURATION=OK")
print("LLM_MODEL=" + llm["model"])
print("LLM_AUTH_TYPE=" + llm["auth_type"])
print("LLM_API_KEY=<CONFIGURED_REDACTED>")
PY

unset OPENAI_KEY

log "OpenHands LLM configuration complete"
