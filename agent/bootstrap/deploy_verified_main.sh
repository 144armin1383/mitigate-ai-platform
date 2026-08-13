#!/usr/bin/env bash

set -euo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
PYTHON="$ROOT/agent/.venv/bin/python"
BACKUP_REF="origin/backup/rolling-main"

cd "$ROOT"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[ "$(git branch --show-current)" = "main" ] || fail "expected main branch"
[ -z "$(git status --porcelain)" ] || fail "repository is not clean"
[ -x "$PYTHON" ] || fail "production python missing"

BEFORE="$(git rev-parse HEAD)"

git fetch origin main backup/rolling-main

REMOTE_MAIN="$(git rev-parse origin/main)"
VERIFIED_MAIN="$(git rev-parse "$BACKUP_REF")"

[ "$REMOTE_MAIN" = "$VERIFIED_MAIN" ] || {
  echo "DEPLOY_BLOCKED=github_main_not_yet_verified"
  echo "ORIGIN_MAIN=$REMOTE_MAIN"
  echo "VERIFIED_BACKUP=$VERIFIED_MAIN"
  exit 20
}

if [ "$BEFORE" = "$REMOTE_MAIN" ]; then
  echo "ALREADY_CURRENT=yes"
else
  git pull --ff-only origin main
fi

rollback() {
  local reason="$1"
  echo "ROLLBACK_REASON=$reason"
  git reset --hard "$BEFORE"
  sudo systemctl daemon-reload
  sudo systemctl restart mitigate-ai-worker.service || true
  echo "ROLLED_BACK_TO=$BEFORE"
  exit 30
}

export PYTHONPATH="$ROOT:$ROOT/agent${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON" -m py_compile \
  agent/execution/runtime_adapter.py \
  agent/execution/openhands_adapter.py \
  agent/execution/openclaw_adapter.py \
  agent/execution/ruflo_adapter.py \
  agent/execution/runtime_router.py \
  agent/execution/runtime_branch_publisher.py \
  agent/execution/workspace_manager.py \
  agent/execution/upstream_manager.py \
  agent/operations/runtime_doctor.py \
  agent/runtime/runtime_consolidation_controller.py \
  agent/runtime/runtime_consolidation_worker.py \
  || rollback "compile_failed"

"$PYTHON" -m unittest \
  agent.tests.test_runtime_adapter \
  agent.tests.test_openhands_adapter \
  agent.tests.test_runtime_router \
  agent.tests.test_runtime_branch_publisher \
  agent.tests.test_runtime_consolidation_controller \
  agent.tests.test_external_runtime_adapters \
  agent.tests.test_upstream_manager \
  agent.tests.test_runtime_doctor \
  -v \
  || rollback "runtime_tests_failed"

sudo systemctl daemon-reload
sudo systemctl restart mitigate-ai-worker.service || rollback "worker_restart_failed"
sleep 4

[ "$(systemctl is-active mitigate-ai-worker.service)" = "active" ] \
  || rollback "worker_not_active"
[ "$(systemctl is-active mitigate-ai-runtime-api.service)" = "active" ] \
  || rollback "runtime_api_not_active"

"$PYTHON" -m agent.operations.runtime_doctor --pretty \
  || rollback "runtime_doctor_failed"

[ -z "$(git status --porcelain)" ] || rollback "repository_became_dirty"
[ "$(git rev-parse HEAD)" = "$REMOTE_MAIN" ] || rollback "unexpected_head"

printf '%s\n' \
  "DEPLOY_VERIFIED_MAIN=yes" \
  "BEFORE=$BEFORE" \
  "AFTER=$(git rev-parse HEAD)" \
  "GITHUB_VERIFICATION_REF=$VERIFIED_MAIN" \
  "Worker=active" \
  "RuntimeAPI=active" \
  "REPOSITORY_CLEAN=yes"
