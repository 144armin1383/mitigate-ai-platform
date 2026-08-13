#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
CANVAS_URL="${MITIGATE_AGENT_CANVAS_HTML_URL:-http://127.0.0.1:8000/canvas}"
PANEL_URL="${MITIGATE_PANEL_HEALTH_URL:-http://127.0.0.1:8766/healthz}"

if [[ ! -f /etc/nginx/snippets/mitigate-ai-canvas-integration.conf ]]; then
    echo "CANVAS_UI_INTEGRATION=NOT_INSTALLED"
    exit 0
fi

HTML="$(
    curl -fsS \
      --max-time 15 \
      "$CANVAS_URL"
)"

if ! grep -qi '</body>' <<<"$HTML"; then
    echo "CANVAS_UI_INTEGRATION=DEGRADED"
    echo "REASON=upstream_html_marker_missing"
    exit 1
fi

curl -fsS \
  --max-time 10 \
  "$PANEL_URL" >/dev/null

test -f \
  /usr/local/share/mitigate-ai/mitigate-runtime-overlay.js

sudo nginx -t >/dev/null

echo "CANVAS_UI_INTEGRATION=COMPATIBLE"
echo "UPSTREAM_CANVAS_FILES_MODIFIED=no"
