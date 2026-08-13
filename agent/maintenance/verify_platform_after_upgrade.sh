#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
EXTERNAL_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"

[[ "$(systemctl is-active mitigate-ai-worker.service)" == "active" ]]
[[ "$(systemctl is-active mitigate-ai-runtime-api.service)" == "active" ]]

curl -fsS --max-time 10 \
  http://127.0.0.1:8000/ready >/dev/null

"$EXTERNAL_ROOT/venv/bin/python" - <<'PY'
import importlib.metadata as metadata

for package in (
    "openhands-sdk",
    "openhands-tools",
):
    version = metadata.version(package)
    if not version:
        raise SystemExit(f"{package} version missing")

print("OPENHANDS=OK")
PY

"$EXTERNAL_ROOT/npm/node_modules/.bin/openclaw" \
  --version >/dev/null

"$EXTERNAL_ROOT/npm/node_modules/.bin/ruflo" \
  --version >/dev/null

echo "PLATFORM_POST_UPGRADE_VERIFY=OK"
