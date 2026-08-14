#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
API_UNIT="/etc/systemd/system/mitigate-ai-runtime-api.service"
WORKER_UNIT="/etc/systemd/system/mitigate-ai-worker.service"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/etc/mitigate-ai/systemd-backups/$STAMP"

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo/root" >&2
  exit 1
}

cd "$ROOT"

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
  agent/runtime/runtime_mcp_server_extended.py \
  agent/tests/test_isolated_mission_runtime.py \
  agent/tests/test_autonomous_operator_runtime.py \
  agent/tests/test_host_recovery_supervisor.py

"$ROOT/agent/.venv/bin/python" -m unittest \
  agent.tests.test_isolated_mission_runtime \
  agent.tests.test_autonomous_operator_runtime \
  agent.tests.test_host_recovery_supervisor -v

OPENHANDS_PYTHON="${MITIGATE_OPENHANDS_PYTHON:-/srv/mitigate/external-runtimes/venv/bin/python}"
test -x "$OPENHANDS_PYTHON"
"$OPENHANDS_PYTHON" -c 'import openhands.sdk; print("MANAGED_OPENHANDS_IMPORT=OK")'

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

cat >"$WORKER_UNIT" <<'EOF'
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
Environment="GIT_SSH_COMMAND=ssh -F /etc/mitigate-ai/ssh/config"
Environment="MITIGATE_AI_MISSION_DEFINITION_ROOT=/srv/mitigate/data/runtime/mission-definitions"
Environment="MITIGATE_AI_AUTONOMOUS_MAX_RETRIES=2"
Environment="MITIGATE_AI_RECOVERY_CHAIN_LIMIT=2"
Environment="MITIGATE_OPENHANDS_PYTHON=/srv/mitigate/external-runtimes/venv/bin/python"
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
echo "SYSTEMD_BACKUP_DIR=$BACKUP_DIR"
echo "GIT_STATUS_BEGIN"
git status --short
echo "GIT_STATUS_END"
