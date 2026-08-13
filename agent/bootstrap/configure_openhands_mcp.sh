#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
CONTAINER="${MITIGATE_AGENT_CANVAS_CONTAINER:-agent-canvas-agent-canvas-1}"
MCP_URL="${MITIGATE_RUNTIME_MCP_URL:-http://172.18.0.1:8771/mcp}"

sudo docker exec -i \
  "$CONTAINER" \
  env MITIGATE_RUNTIME_MCP_URL="$MCP_URL" \
  python3 - <<'PY'
import json
import os
import urllib.request

base = "http://127.0.0.1:18000"
url = os.environ["MITIGATE_RUNTIME_MCP_URL"]

with urllib.request.urlopen(
    base + "/api/settings",
    timeout=10,
) as response:
    current = json.load(response)

agent = current.get("agent_settings", {})
mcp_config = dict(
    agent.get("mcp_config") or {}
)

mcp_config["mitigate-runtime"] = {
    "transport": "streamable-http",
    "url": url,
}

payload = {
    "agent_settings_diff": {
        "mcp_config": mcp_config
    }
}

request = urllib.request.Request(
    base + "/api/settings",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json"
    },
    method="PATCH",
)

with urllib.request.urlopen(
    request,
    timeout=10,
) as response:
    if response.status != 200:
        raise SystemExit(
            f"MCP settings update failed: "
            f"{response.status}"
        )

print("OPENHANDS_MCP_CONFIGURATION=OK")
print("MCP_SERVER=mitigate-runtime")
print("MCP_URL=" + url)
PY
