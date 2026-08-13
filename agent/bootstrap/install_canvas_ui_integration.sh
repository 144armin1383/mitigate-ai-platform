#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
NGINX_SITE="${MITIGATE_NGINX_ACCESS_SITE:-/etc/nginx/sites-available/mitigate-ai-access}"
RUNTIME_ENV="${MITIGATE_RUNTIME_ENV:-/etc/mitigate-ai/runtime.env}"
CANVAS_UPSTREAM="${MITIGATE_CANVAS_UPSTREAM:-http://127.0.0.1:8000}"

SOURCE_JS="$ROOT/agent/integrations/agent-canvas/mitigate-runtime-overlay.js"
STATIC_DIR="/usr/local/share/mitigate-ai"
STATIC_JS="$STATIC_DIR/mitigate-runtime-overlay.js"

INTEGRATION_SNIPPET="/etc/nginx/snippets/mitigate-ai-canvas-integration.conf"
AUTH_SNIPPET="/etc/nginx/snippets/mitigate-ai-panel-auth.conf"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
[[ -f "$SOURCE_JS" ]] || die "Overlay source missing."
[[ -f "$NGINX_SITE" ]] || die "Nginx access site missing."
[[ -f "$RUNTIME_ENV" ]] || die "Runtime environment missing."

PANEL_USER="$(
  awk -F= '
    $1=="MITIGATE_AI_PANEL_USERNAME" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'' ]+|["'\'' ]+$/, "")
      print
      exit
    }
  ' "$RUNTIME_ENV"
)"

PANEL_PASS="$(
  awk -F= '
    $1=="MITIGATE_AI_PANEL_PASSWORD" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'' ]+|["'\'' ]+$/, "")
      print
      exit
    }
  ' "$RUNTIME_ENV"
)"

[[ -n "$PANEL_USER" ]] || die "Panel username missing."
[[ -n "$PANEL_PASS" ]] || die "Panel password missing."

install -d -m 0755 "$STATIC_DIR"
install -m 0644 "$SOURCE_JS" "$STATIC_JS"

AUTH_VALUE="$(
  printf '%s:%s' "$PANEL_USER" "$PANEL_PASS" |
    base64 -w0
)"

cat > "$AUTH_SNIPPET" <<EOF_AUTH
proxy_set_header Authorization "Basic ${AUTH_VALUE}";
EOF_AUTH

chmod 0600 "$AUTH_SNIPPET"

cat > "$INTEGRATION_SNIPPET" <<EOF_NGINX
# MITIGATE Canvas UI integration.
# This file never modifies upstream Agent Canvas files.

location = /mitigate-overlay.js {
    alias ${STATIC_JS};
    default_type application/javascript;
    add_header Cache-Control "no-store";
}

location = /mitigate-runtime/providers {
    include ${AUTH_SNIPPET};

    proxy_pass http://127.0.0.1:8766/api/providers\$is_args\$args;
    proxy_http_version 1.1;
    proxy_set_header Host 127.0.0.1;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_buffering off;
}

location ^~ /canvas {
    proxy_pass ${CANVAS_UPSTREAM};

    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";

    # HTML must be uncompressed only on Canvas page routes
    # so Nginx can inject the external overlay script.
    proxy_set_header Accept-Encoding "";

    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_buffering off;

    sub_filter_once on;
    sub_filter '</body>' '<script defer src="/mitigate-overlay.js"></script></body>';
}
EOF_NGINX

if ! grep -q 'mitigate-ai-canvas-integration.conf' "$NGINX_SITE"; then
    python3 - "$NGINX_SITE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

marker = "    location / {\n"

include = (
    "    # MITIGATE_CANVAS_UI_INTEGRATION\n"
    "    include /etc/nginx/snippets/"
    "mitigate-ai-canvas-integration.conf;\n\n"
)

if marker not in text:
    raise SystemExit(
        "ERROR: nginx location marker not found"
    )

path.write_text(
    text.replace(
        marker,
        include + marker,
        1,
    )
)
PY
fi

nginx -t
systemctl reload nginx

echo "CANVAS_UI_INTEGRATION_INSTALLED=yes"
echo "UPSTREAM_CANVAS_FILES_MODIFIED=no"
