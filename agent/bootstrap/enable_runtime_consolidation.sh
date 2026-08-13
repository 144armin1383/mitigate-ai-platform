#!/usr/bin/env bash

set -euo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
WORKER_DROPIN_DIR="/etc/systemd/system/mitigate-ai-worker.service.d"
WORKER_DROPIN="$WORKER_DROPIN_DIR/zzzz-runtime-consolidation.conf"
WORKER_LEGACY_DROPIN="$WORKER_DROPIN_DIR/runtime-consolidation.conf"
API_DROPIN_DIR="/etc/systemd/system/mitigate-ai-runtime-api.service.d"
API_DROPIN="$API_DROPIN_DIR/zzzz-isolated-request-runtime.conf"
BACKUP_DIR="/srv/mitigate/data/runtime/recovery/runtime-consolidation-$(date -u +%Y%m%dT%H%M%SZ)"

cd "$ROOT"

echo "=================================================="
echo "ENABLE MITIGATE RUNTIME CONSOLIDATION"
echo "=================================================="

if [ "$(git branch --show-current)" != "main" ]; then
  echo "ERROR: expected main"
  exit 10
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: repository is not clean"
  git status --short
  exit 11
fi

git fetch origin main
git pull --ff-only origin main

if [ "$(git rev-parse main)" != "$(git rev-parse origin/main)" ]; then
  echo "ERROR: main is not synchronized"
  exit 12
fi

if [ ! -x "$RUNTIME_ROOT/venv/bin/python" ]; then
  echo "ERROR: isolated OpenHands runtime missing"
  exit 20
fi

if [ ! -x "$RUNTIME_ROOT/npm/node_modules/.bin/openclaw" ]; then
  echo "ERROR: OpenClaw runtime missing"
  exit 21
fi

if [ ! -x "$RUNTIME_ROOT/npm/node_modules/.bin/ruflo" ]; then
  echo "ERROR: Ruflo runtime missing"
  exit 22
fi

export PYTHONPATH="$ROOT:$ROOT/agent${PYTHONPATH:+:$PYTHONPATH}"

"$ROOT/agent/.venv/bin/python" -m py_compile \
  agent/runtime/runtime_consolidation_controller.py \
  agent/runtime/runtime_consolidation_worker.py \
  agent/runtime/production_runtime_api_isolated.py \
  agent/runtime/isolated_request_queue_adapter.py \
  agent/runtime/autonomous_mission_queue.py \
  agent/runtime/autonomous_mission_diagnostics.py \
  agent/runtime/task_scope_workspace_controller.py \
  agent/runtime/managed_workspace_mission_controller.py \
  agent/execution/external_openhands_runner.py \
  agent/execution/managed_openhands_adapter.py \
  agent/execution/runtime_router.py \
  agent/execution/runtime_branch_publisher.py \
  agent/execution/openhands_subprocess_runner.py

"$ROOT/agent/.venv/bin/python" -m unittest \
  agent.tests.test_runtime_adapter \
  agent.tests.test_openhands_adapter \
  agent.tests.test_runtime_router \
  agent.tests.test_runtime_branch_publisher \
  agent.tests.test_runtime_consolidation_controller \
  agent.tests.test_external_runtime_adapters \
  agent.tests.test_upstream_manager \
  agent.tests.test_isolated_mission_runtime \
  agent.tests.test_autonomous_operator_runtime \
  -v

"$RUNTIME_ROOT/venv/bin/python" - <<'PY'
import importlib.metadata as m
import openhands.sdk
print("OPENHANDS_OK=" + m.version("openhands-sdk"))
PY

"$RUNTIME_ROOT/npm/node_modules/.bin/openclaw" --version
"$RUNTIME_ROOT/npm/node_modules/.bin/ruflo" --version

mkdir -p "$BACKUP_DIR"
systemctl cat mitigate-ai-worker.service > "$BACKUP_DIR/mitigate-ai-worker.service.before.txt"
systemctl cat mitigate-ai-runtime-api.service > "$BACKUP_DIR/mitigate-ai-runtime-api.service.before.txt"

sudo mkdir -p "$WORKER_DROPIN_DIR" "$API_DROPIN_DIR"
sudo rm -f "$WORKER_LEGACY_DROPIN"

sudo tee "$API_DROPIN" >/dev/null <<EOF
[Service]
Environment="MITIGATE_AI_MISSION_DEFINITION_ROOT=/srv/mitigate/data/runtime/mission-definitions"
Environment="MITIGATE_AI_AUTONOMOUS_MAX_RETRIES=2"
ExecStart=
ExecStart=$ROOT/agent/.venv/bin/python -m agent.runtime.production_runtime_api_isolated
EOF

sudo tee "$WORKER_DROPIN" >/dev/null <<EOF
[Service]
Environment="MITIGATE_EXTERNAL_RUNTIME_ROOT=$RUNTIME_ROOT"
Environment="MITIGATE_AI_MISSION_DEFINITION_ROOT=/srv/mitigate/data/runtime/mission-definitions"
Environment="MITIGATE_AI_AUTONOMOUS_MAX_RETRIES=2"
Environment="MITIGATE_OPENHANDS_PYTHON=$RUNTIME_ROOT/venv/bin/python"
Environment="PYTHONPATH=$ROOT:$ROOT/agent"
ExecStart=
ExecStart=$ROOT/agent/.venv/bin/python -m agent.runtime.runtime_consolidation_worker --queue-path /srv/mitigate/data/runtime/missions.json --worker-id production-worker --poll-interval 5 --controller-mode mission-runner --heartbeat-path /srv/mitigate/data/runtime/worker.heartbeat --execution-report-dir /srv/mitigate/data/runtime/execution-reports --checkpoint-dir /srv/mitigate/data/runtime/checkpoints --project-id mitigate-ai-platform --technology-registry-path /srv/mitigate/data/runtime/technology/registry.json --queue-reference missions
EOF

sudo systemctl daemon-reload
sudo systemctl restart mitigate-ai-runtime-api.service
sudo systemctl restart mitigate-ai-worker.service
sleep 3

rollback_runtime() {
  sudo rm -f "$WORKER_DROPIN" "$API_DROPIN" "$WORKER_LEGACY_DROPIN"
  sudo systemctl daemon-reload
  sudo systemctl restart mitigate-ai-runtime-api.service || true
  sudo systemctl restart mitigate-ai-worker.service || true
}

if [ "$(systemctl is-active mitigate-ai-worker.service)" != "active" ]; then
  echo "ERROR: consolidated worker failed; rolling back"
  rollback_runtime
  exit 30
fi

if [ "$(systemctl is-active mitigate-ai-runtime-api.service)" != "active" ]; then
  echo "ERROR: isolated runtime API failed; rolling back"
  rollback_runtime
  exit 31
fi

WORKER_EXECSTART="$(systemctl show mitigate-ai-worker.service -p ExecStart --value)"
API_EXECSTART="$(systemctl show mitigate-ai-runtime-api.service -p ExecStart --value)"

if ! printf '%s' "$WORKER_EXECSTART" | grep -q 'agent.runtime.runtime_consolidation_worker'; then
  echo "ERROR: consolidated worker entrypoint not active; rolling back"
  rollback_runtime
  exit 32
fi

if ! printf '%s' "$API_EXECSTART" | grep -q 'agent.runtime.production_runtime_api_isolated'; then
  echo "ERROR: isolated runtime API entrypoint not active; rolling back"
  rollback_runtime
  exit 33
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: canonical repository became dirty; rolling back"
  rollback_runtime
  exit 34
fi

echo
echo "=================================================="
echo "RESULT"
echo "=================================================="
echo "RUNTIME_CONSOLIDATION_ENABLED=yes"
echo "ISOLATED_REQUEST_RUNTIME_ENABLED=yes"
echo "AUTONOMOUS_RETRY_POLICY_ENABLED=yes"
echo "Worker=$(systemctl is-active mitigate-ai-worker.service)"
echo "RuntimeAPI=$(systemctl is-active mitigate-ai-runtime-api.service)"
echo "MAIN=$(git rev-parse main)"
echo "PRODUCTION_REPOSITORY_CLEAN=yes"
echo "ACTIVE_WORKER_DROPIN=$WORKER_DROPIN"
echo "ACTIVE_API_DROPIN=$API_DROPIN"
echo "ROLLBACK_BACKUP=$BACKUP_DIR"
