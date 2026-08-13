#!/usr/bin/env bash

set -euo pipefail

DROPIN_DIR="/etc/systemd/system/mitigate-ai-worker.service.d"
DROPIN="$DROPIN_DIR/zzzz-runtime-consolidation.conf"
LEGACY_DROPIN="$DROPIN_DIR/runtime-consolidation.conf"

sudo rm -f "$DROPIN" "$LEGACY_DROPIN"

sudo systemctl daemon-reload
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

EXECSTART="$(systemctl show mitigate-ai-worker.service -p ExecStart --value)"
if printf '%s' "$EXECSTART" | grep -q 'agent.runtime.runtime_consolidation_worker'; then
  echo "ERROR: consolidated worker entrypoint is still active"
  exit 12
fi

echo "RUNTIME_CONSOLIDATION_ENABLED=no"
echo "Worker=active"
echo "RuntimeAPI=active"
