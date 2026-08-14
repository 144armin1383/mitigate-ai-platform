#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
API_UNIT="/etc/systemd/system/mitigate-ai-runtime-api.service"
WORKER_UNIT="/etc/systemd/system/mitigate-ai-worker.service"
OPENHANDS_STATE_ROOT="${MITIGATE_OPENHANDS_HOME:-/srv/mitigate/data/openhands-runtime}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/etc/mitigate-ai/systemd-backups/$STAMP"

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo/root" >&2
  exit 1
}

cd "$ROOT"

# The production OpenHands worker runs as ubuntu while Agent Canvas runs in its
# container as UID/GID 10001. Keep their persistent state roots separate so
# fixing or provisioning one runtime can never change ownership underneath the
# other. ProtectHome=true remains enabled for the worker.
install -d -o ubuntu -g ubuntu -m 0700 "$OPENHANDS_STATE_ROOT"
for relative in .config .cache .local .local/share .openhands; do
  install -d -o ubuntu -g ubuntu -m 0700 "$OPENHANDS_STATE_ROOT/$relative"
done
chown -R ubuntu:ubuntu "$OPENHANDS_STATE_ROOT"

python3 -m py_compile \
  agent/runtime/isolated_request_queue_adapter.py \
  agent/runtime/production_runtime_api_isolated.py \
  agent/runtime/workspace_production_mission_controller.py \
  agent/runtime/managed_workspace_mission_controller.py \
  agent/runtime/autonomous_mission_queue.py \
  agent/runtime/autonomous_mission_diagnostics.py \
  agent/runtime/host_recovery_supervisor.py \
  agent/runtime/mission_diagnostics.py \
  agent/runtime/workspace_worker_entrypoint.py \
  agent/execution/external_openhands_runner.py \
  agent/execution/managed_openhands_adapter.py \
  agent/execution/openhands_subprocess_runner.py \
  agent/execution/openclaw_adapter.py \
  agent/execution/runtime_router.py \
  agent/runtime/runtime_mcp_server_extended.py \
  agent/tests/test_isolated_mission_runtime.py \
  agent/tests/test_autonomous_operator_runtime.py \
  agent/tests/test_host_recovery_supervisor.py \
  agent/tests/test_mission_diagnostics_git_warnings.py \
  agent/tests/test_runtime_execution_observability.py \
  agent/tests/test_runtime_router_failover.py \
  agent/tests/test_openhands_managed_home.py

"$ROOT/agent/.venv/bin/python" -m unittest \
  agent.tests.test_isolated_mission_runtime \
  agent.tests.test_autonomous_operator_runtime \
  agent.tests.test_host_recovery_supervisor \
  agent.tests.test_mission_diagnostics_git_warnings \
  agent.tests.test_runtime_execution_observability \
  agent.tests.test_runtime_router_failover \
  agent.tests.test_openhands_managed_home -v

OPENHANDS_PYTHON="${MITIGATE_OPENHANDS_PYTHON:-/srv/mitigate/external-runtimes/venv/bin/python}"
OPENHANDS_OK=0
if [[ -x "$OPENHANDS_PYTHON" ]]; then
  if HOME="$OPENHANDS_STATE_ROOT" XDG_CONFIG_HOME="$OPENHANDS_STATE_ROOT/.config" XDG_CACHE_HOME="$OPENHANDS_STATE_ROOT/.cache" XDG_DATA_HOME="$OPENHANDS_STATE_ROOT/.local/share" OPENHANDS_HOME="$OPENHANDS_STATE_ROOT/.openhands" "$OPENHANDS_PYTHON" - <<'PY'
from openhands.sdk import Agent, Conversation, LLM, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
PY
  then
    OPENHANDS_OK=1
    echo "MANAGED_OPENHANDS_API_IMPORTS=OK"
    echo "MANAGED_OPENHANDS_TOOL_IMPORTS=OK"
    echo "MANAGED_OPENHANDS_STATE=OK"
  else
    echo "MANAGED_OPENHANDS_IMPORTS=UNAVAILABLE"
  fi
else
  echo "MANAGED_OPENHANDS_PYTHON=UNAVAILABLE"
fi

OPENCLAW_BINARY="${MITIGATE_OPENCLAW_BINARY:-/srv/mitigate/external-runtimes/npm/node_modules/.bin/openclaw}"
OPENCLAW_OK=0
if [[ -x "$OPENCLAW_BINARY" ]] && NODE_OPTIONS=--jitless "$OPENCLAW_BINARY" agent exec --help >/dev/null 2>&1; then
  OPENCLAW_OK=1
  echo "MANAGED_OPENCLAW_AGENT_EXEC=OK"
  echo "MANAGED_OPENCLAW_JITLESS=OK"
else
  echo "MANAGED_OPENCLAW_AGENT_EXEC=UNAVAILABLE"
fi

if [[ "$OPENHANDS_OK" -ne 1 && "$OPENCLAW_OK" -ne 1 ]]; then
  echo "ERROR: no healthy governed coding runtime is available" >&2
  exit 1
fi

echo "MITIGATE_CODING_RUNTIME_PREFLIGHT=PASS"

install -d -m 0700 "$BACKUP_DIR"
cp -a "$API_UNIT" "$BACKUP_DIR/" 2>/dev/null || true
cp -a "$WORKER_UNIT" "$BACKUP_DIR/" 2>/dev/null || true

systemctl stop mitigate-ai-worker.service

cat >"$API_UNIT" <<'EOF'
[Unit]
Description=MITIGATE AI Production Runtime Private API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/srv/mitigate/mitigate-ai-platform
EnvironmentFile=/etc/mitigate-ai/runtime.env
Environment="OPENCLAW_HOME=/srv/mitigate/data/openclaw"
Environment="OPENCLAW_STATE_DIR=/srv/mitigate/data/openclaw"
Environment="MITIGATE_AI_MISSION_DEFINITION_ROOT=/srv/mitigate/data/runtime/mission-definitions"
Environment="MITIGATE_AI_AUTONOMOUS_MAX_RETRIES=2"
Environment="MITIGATE_AI_RECOVERY_CHAIN_LIMIT=2"
ExecStart=/srv/mitigate/mitigate-ai-platform/agent/.venv/bin/python -m agent.runtime.production_runtime_api_isolated
Restart=on-failure
RestartSec=5s
KillSignal=SIGTERM
TimeoutStopSec=30s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictRealtime=true
RestrictNamespaces=true
SystemCallArchitectures=native
UMask=0077
ReadWritePaths=/srv/mitigate/mitigate-ai-platform /srv/mitigate/data /srv/mitigate/ai-logs /var/log/mitigate-ai
RuntimeDirectory=mitigate-ai-runtime-api
RuntimeDirectoryMode=0750

[Install]
WantedBy=multi-user.target
EOF

cat >"$WORKER_UNIT" <<EOF
[Unit]
Description=MITIGATE AI Autonomous Background Worker
After=network-online.target mitigate-ai-runtime-api.service
Wants=network-online.target
Requires=mitigate-ai-runtime-api.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/srv/mitigate/mitigate-ai-platform
EnvironmentFile=/etc/mitigate-ai/runtime.env
Environment="OPENCLAW_HOME=/srv/mitigate/data/openclaw"
Environment="OPENCLAW_STATE_DIR=/srv/mitigate/data/openclaw"
Environment="NODE_OPTIONS=--jitless"
Environment="GIT_SSH_COMMAND=ssh -F /etc/mitigate-ai/ssh/config"
Environment="MITIGATE_AI_MISSION_DEFINITION_ROOT=/srv/mitigate/data/runtime/mission-definitions"
Environment="MITIGATE_AI_AUTONOMOUS_MAX_RETRIES=2"
Environment="MITIGATE_AI_RECOVERY_CHAIN_LIMIT=2"
Environment="MITIGATE_OPENHANDS_PYTHON=/srv/mitigate/external-runtimes/venv/bin/python"
Environment="MITIGATE_OPENHANDS_HOME=$OPENHANDS_STATE_ROOT"
Environment="MITIGATE_OPENCLAW_BINARY=/srv/mitigate/external-runtimes/npm/node_modules/.bin/openclaw"
ExecStart=/srv/mitigate/mitigate-ai-platform/agent/.venv/bin/python -m agent.runtime.workspace_worker_entrypoint --queue-path /srv/mitigate/data/runtime/missions.json --worker-id production-worker --poll-interval 5 --heartbeat-path /srv/mitigate/data/runtime/worker.heartbeat
Restart=on-failure
RestartSec=5s
KillSignal=SIGTERM
TimeoutStopSec=30s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictRealtime=true
RestrictNamespaces=true
SystemCallArchitectures=native
UMask=0077
ReadWritePaths=/srv/mitigate/mitigate-ai-platform /srv/mitigate/data /srv/mitigate/ai-logs /var/log/mitigate-ai
RuntimeDirectory=mitigate-ai-worker
RuntimeDirectoryMode=0750

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl restart mitigate-ai-runtime-api.service

for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:8765/health/live >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:8765/health/live >/dev/null

systemctl restart mitigate-ai-worker.service
sleep 2

bash "$ROOT/agent/bootstrap/configure_openhands_mcp.sh"
systemctl restart mitigate-ai-runtime-mcp.service
systemctl restart mitigate-ai-panel.service
sleep 2

for service in \
  mitigate-ai-runtime-api.service \
  mitigate-ai-worker.service \
  mitigate-ai-runtime-gateway.service \
  mitigate-ai-runtime-mcp.service \
  mitigate-ai-panel.service
do
  test "$(systemctl is-active "$service")" = "active"
done

curl -fsS --max-time 5 http://127.0.0.1:8000/ready >/dev/null

echo "ISOLATED_MISSION_RUNTIME_ACTIVATED=yes"
echo "MITIGATE_AUTONOMOUS_OPERATOR=ACTIVE"
echo "MITIGATE_HOST_RECOVERY_SUPERVISOR=ACTIVE"
echo "MITIGATE_RECOVERY_CHAIN_LIMIT=2"
echo "MITIGATE_GIT_DIAGNOSTICS_WARNING_ISOLATION=ACTIVE"
echo "MITIGATE_OPENHANDS_DISPOSABLE_CWD=ACTIVE"
echo "MITIGATE_OPENHANDS_MANAGED_HOME=ACTIVE"
echo "MITIGATE_OPENHANDS_STATE_ISOLATION=ACTIVE"
echo "MITIGATE_PROVIDER_FAILOVER_ROUTER=ACTIVE"
echo "MITIGATE_FAILURE_EVIDENCE=ACTIVE"
echo "MITIGATE_INTENT_CLASSIFIER_V2=ACTIVE"
echo "SYSTEMD_BACKUP_DIR=$BACKUP_DIR"
echo "GIT_STATUS_BEGIN"
git status --short
echo "GIT_STATUS_END"
