#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
WRAPPER_SRC="$ROOT/agent/execution/openclaw_compat_wrapper.sh"
WRAPPER_DST="/usr/local/libexec/mitigate-openclaw-compat"
DROPIN_DIR="/etc/systemd/system/mitigate-ai-worker.service.d"
DROPIN_FILE="$DROPIN_DIR/20-openclaw-node-compat.conf"

[[ ${EUID} -eq 0 ]] || {
  echo "ERROR: run with sudo/root" >&2
  exit 1
}

install -d -m 0755 /usr/local/libexec
install -m 0755 "$WRAPPER_SRC" "$WRAPPER_DST"
install -d -m 0755 "$DROPIN_DIR"

cat >"$DROPIN_FILE" <<EOF
[Service]
MemoryDenyWriteExecute=false
Environment="NODE_OPTIONS="
Environment="MITIGATE_OPENCLAW_BINARY=$WRAPPER_DST"
Environment="MITIGATE_OPENCLAW_REAL_BINARY=/srv/mitigate/external-runtimes/npm/node_modules/.bin/openclaw"
Environment="MITIGATE_WORKSPACE_ROOT=/srv/mitigate/data/runtime/workspaces"
EOF

systemctl daemon-reload
systemctl restart mitigate-ai-worker.service
sleep 2

test "$(systemctl is-active mitigate-ai-worker.service)" = "active"

echo "OPENCLAW_WORKER_COMPAT=ACTIVE"
echo "OPENCLAW_WRAPPER=$WRAPPER_DST"
echo "WORKER_MEMORY_DENY_WRITE_EXECUTE=$(systemctl show mitigate-ai-worker.service -p MemoryDenyWriteExecute --value)"
echo "WORKER_OPENCLAW_BINARY=$(systemctl show mitigate-ai-worker.service -p Environment --value | tr ' ' '\n' | grep '^MITIGATE_OPENCLAW_BINARY=' | tail -1)"
