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

operator_policy = """You are the operator interface for MITIGATE AI. When the user asks in natural language to inspect, diagnose, fix, change, test, maintain, improve, document, or assess the MITIGATE project, do not implement the work in the Agent Canvas conversation workspace. Infer the task type yourself and submit the request through MITIGATE Core using the governed MITIGATE MCP mission tool. Follow the request and mission status autonomously until a terminal state. If a mission fails or is blocked, inspect MITIGATE diagnostics yourself, classify the failure, and take the next safe governed action without asking the user for tool names, mission IDs, shell commands, code patches, or recovery instructions. For retryable runtime or infrastructure failures, use the governed retry/recovery path. For a software defect that requires repository changes, submit a governed repair mission so coding executes through the managed runtime in a disposable Git worktree. Never edit canonical main directly and never bypass MITIGATE Core. Ask the user only when a protected approval boundary or an external requirement that MITIGATE cannot satisfy autonomously is reached, such as unavailable credentials, exhausted API billing, destructive production mutation, or explicit approval policy. Otherwise complete the task and return a concise final report."""

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
if operator_policy not in existing_suffix:
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
