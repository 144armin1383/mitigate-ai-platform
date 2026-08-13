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

operator_policy = """You are the operator interface for MITIGATE AI. The user should be able to describe a MITIGATE problem or desired change in one natural-language sentence. For MITIGATE source, bug, maintenance, testing, architecture, documentation, infrastructure, or improvement requests, do not implement work in the Agent Canvas conversation workspace and do not ask the user to name tools, task types, mission IDs, commands, code patches, or recovery steps. Use mitigate_autonomous_task for the natural-language request; MITIGATE Core owns task classification, planning, mission state, runtime choice, disposable workspace creation, validation, Git governance and reporting. Follow the returned request and mission autonomously until terminal state. If execution fails or is blocked, use mitigate_mission_diagnostics and then mitigate_autonomous_recovery yourself. Continue following any governed repair mission without requiring a new user prompt. Never edit canonical main directly and never bypass MITIGATE Core. Ask the user only when MITIGATE reaches a real protected approval boundary or an external requirement it cannot satisfy autonomously, such as unavailable credentials, exhausted API billing, or a destructive production action requiring explicit approval. Otherwise finish the work and return only a concise result report."""

with urllib.request.urlopen(
    base + "/api/settings",
    timeout=10,
) as response:
    current = json.load(response)

agent = current.get("agent_settings", {})
mcp_config = dict(agent.get("mcp_config") or {})
mcp_config["mitigate-runtime"] = {
    "transport": "streamable-http",
    "url": url,
    "enabled": True,
}

agent_context = dict(agent.get("agent_context") or {})
existing_suffix = str(agent_context.get("system_message_suffix") or "").strip()
marker = "You are the operator interface for MITIGATE AI."
if marker in existing_suffix:
    existing_suffix = existing_suffix.split(marker, 1)[0].rstrip()
agent_context["system_message_suffix"] = (
    (existing_suffix + "\n\n") if existing_suffix else ""
) + operator_policy

payload = {
    "agent_settings_diff": {
        "mcp_config": mcp_config,
        "agent_context": agent_context,
    }
}

request = urllib.request.Request(
    base + "/api/settings",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)

with urllib.request.urlopen(request, timeout=10) as response:
    if response.status != 200:
        raise SystemExit(
            f"MCP settings update failed: {response.status}"
        )

print("OPENHANDS_MCP_CONFIGURATION=OK")
print("MCP_SERVER=mitigate-runtime")
print("MCP_URL=" + url)
print("MITIGATE_AUTONOMOUS_OPERATOR_POLICY=OK")
PY
