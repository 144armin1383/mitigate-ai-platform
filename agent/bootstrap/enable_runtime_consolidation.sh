#!/usr/bin/env bash

set -euo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
DROPIN_DIR="/etc/systemd/system/mitigate-ai-worker.service.d"
DROPIN="$DROPIN_DIR/zzzz-runtime-consolidation.conf"
LEGACY_DROPIN="$DROPIN_DIR/runtime-consolidation.conf"
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

sudo mkdir -p "$DROPIN_DIR"

# Remove the older lower-precedence filename if a previous activation created it.
sudo rm -f "$LEGACY_DROPIN"

# This file is intentionally named with a zzzz- prefix so it sorts after
# existing execution-reporting, technology-lifecycle and zz-durable-checkpointing
# drop-ins. systemd applies drop-ins lexicographically; the final ExecStart reset
# must therefore belong to the consolidation layer while it is enabled.
sudo tee "$DROPIN" >/dev/null <<EOF
[Service]
Environment="MITIGATE_EXTERNAL_RUNTIME_ROOT=$RUNTIME_ROOT"
Environment="PYTHONPATH=$ROOT:$ROOT/agent"
ExecStart=
ExecStart=$ROOT/agent/.venv/bin/python -m agent.runtime.runtime_consolidation_worker --queue-path /srv/mitigate/data/runtime/missions.json --worker-id production-worker --poll-interval 5 --controller-mode mission-runner --heartbeat-path /srv/mitigate/data/runtime/worker.heartbeat --execution-report-dir /srv/mitigate/data/runtime/execution-reports --checkpoint-dir /srv/mitigate/data/runtime/checkpoints --project-id mitigate-ai-platform --technology-registry-path /srv/mitigate/data/runtime/technology/registry.json --queue-reference missions
EOF

sudo systemctl daemon-reload
sudo systemctl restart mitigate-ai-worker.service
sleep 3

rollback_worker() {
  sudo rm -f "$DROPIN" "$LEGACY_DROPIN"
  sudo systemctl daemon-reload
  sudo systemctl restart mitigate-ai-worker.service
}

if [ "$(systemctl is-active mitigate-ai-worker.service)" != "active" ]; then
  echo "ERROR: consolidated worker failed; rolling back"
  rollback_worker
  exit 30
fi

if [ "$(systemctl is-active mitigate-ai-runtime-api.service)" != "active" ]; then
  echo "ERROR: runtime API is not active; rolling back worker"
  rollback_worker
  exit 31
fi

EXECSTART="$(systemctl show mitigate-ai-worker.service -p ExecStart --value)"
if ! printf '%s' "$EXECSTART" | grep -q 'agent.runtime.runtime_consolidation_worker'; then
  echo "ERROR: consolidated worker entrypoint not active; rolling back"
  rollback_worker
  exit 32
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: canonical repository became dirty; rolling back worker"
  rollback_worker
  exit 33
fi

echo
echo "=================================================="
echo "RESULT"
echo "=================================================="
echo "RUNTIME_CONSOLIDATION_ENABLED=yes"
echo "Worker=$(systemctl is-active mitigate-ai-worker.service)"
echo "RuntimeAPI=$(systemctl is-active mitigate-ai-runtime-api.service)"
echo "MAIN=$(git rev-parse main)"
echo "PRODUCTION_REPOSITORY_CLEAN=yes"
echo "ACTIVE_DROPIN=$DROPIN"
echo "ROLLBACK_BACKUP=$BACKUP_DIR"
