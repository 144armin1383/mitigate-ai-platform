#!/usr/bin/env bash

set -euo pipefail

DROPIN="/etc/systemd/system/mitigate-ai-worker.service.d/runtime-consolidation.conf"

if [ -f "$DROPIN" ]; then
  sudo rm -f "$DROPIN"
fi

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

echo "RUNTIME_CONSOLIDATION_ENABLED=no"
echo "Worker=active"
echo "RuntimeAPI=active"
