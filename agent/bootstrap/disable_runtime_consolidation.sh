#!/usr/bin/env bash

set -euo pipefail

WORKER_DROPIN_DIR="/etc/systemd/system/mitigate-ai-worker.service.d"
WORKER_DROPIN="$WORKER_DROPIN_DIR/zzzz-runtime-consolidation.conf"
WORKER_LEGACY_DROPIN="$WORKER_DROPIN_DIR/runtime-consolidation.conf"
API_DROPIN="/etc/systemd/system/mitigate-ai-runtime-api.service.d/zzzz-isolated-request-runtime.conf"

sudo rm -f \
  "$WORKER_DROPIN" \
  "$WORKER_LEGACY_DROPIN" \
  "$API_DROPIN"

sudo systemctl daemon-reload
sudo systemctl restart mitigate-ai-runtime-api.service
sudo systemctl restart mitigate-ai-worker.service
sleep 2

if [ "$(systemctl is-active mitigate-ai-worker.service)" != "active" ]; then
  echo "ERROR: legacy worker failed to restart"
  exit 10
fi

if [ "$(systemctl is-active mitigate-ai-runtime-api.service)" != "active" ]; then
  echo "ERROR: runtime API is not active"
  exit 11
fi

WORKER_EXECSTART="$(systemctl show mitigate-ai-worker.service -p ExecStart --value)"
API_EXECSTART="$(systemctl show mitigate-ai-runtime-api.service -p ExecStart --value)"

if printf '%s' "$WORKER_EXECSTART" | grep -q 'agent.runtime.runtime_consolidation_worker'; then
  echo "ERROR: consolidated worker entrypoint is still active"
  exit 12
fi

if printf '%s' "$API_EXECSTART" | grep -q 'agent.runtime.production_runtime_api_isolated'; then
  echo "ERROR: isolated request API entrypoint is still active"
  exit 13
fi

echo "RUNTIME_CONSOLIDATION_ENABLED=no"
echo "ISOLATED_REQUEST_RUNTIME_ENABLED=no"
echo "Worker=active"
echo "RuntimeAPI=active"
