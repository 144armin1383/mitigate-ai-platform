#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
DATA_ROOT="${MITIGATE_AI_DATA_ROOT:-/srv/mitigate/data}"
NGINX_SITE="${MITIGATE_NGINX_ACCESS_SITE:-/etc/nginx/sites-available/mitigate-ai-access}"
RUNTIME_ENV="${MITIGATE_RUNTIME_ENV:-/etc/mitigate-ai/runtime.env}"
CANVAS_UPSTREAM="${MITIGATE_CANVAS_UPSTREAM:-http://127.0.0.1:8000}"

RUNTIME_SOURCE_JS="$ROOT/agent/integrations/agent-canvas/mitigate-runtime-overlay.js"
APPROVAL_SOURCE_JS="$ROOT/agent/web/canvas_approval_overlay.js"
LLM_SOURCE_JS="$ROOT/agent/web/canvas_llm_provider_overlay.js"
APPROVAL_SOURCE_SNIPPET="$ROOT/agent/deploy/nginx/mitigate-ai-canvas-approval.conf"
STATIC_DIR="/usr/local/share/mitigate-ai"
RUNTIME_STATIC_JS="$STATIC_DIR/mitigate-runtime-overlay.js"
APPROVAL_STATIC_JS="$STATIC_DIR/mitigate-approval-overlay.js"
LLM_STATIC_JS="$STATIC_DIR/mitigate-llm-provider-overlay.js"
APPROVAL_STATE_DIR="$DATA_ROOT/runtime/approvals"
PROVIDER_SECRET_DIR="$DATA_ROOT/runtime/provider-secrets"

INTEGRATION_SNIPPET="/etc/nginx/snippets/mitigate-ai-canvas-integration.conf"
APPROVAL_SNIPPET="/etc/nginx/snippets/mitigate-ai-canvas-approval.conf"
AUTH_SNIPPET="/etc/nginx/snippets/mitigate-ai-panel-auth.conf"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/etc/mitigate-ai/nginx-backups/$STAMP"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
[[ -f "$RUNTIME_SOURCE_JS" ]] || die "Runtime overlay source missing."
[[ -f "$APPROVAL_SOURCE_JS" ]] || die "Approval overlay source missing."
[[ -f "$LLM_SOURCE_JS" ]] || die "LLM provider overlay source missing."
[[ -f "$APPROVAL_SOURCE_SNIPPET" ]] || die "Approval Nginx source missing."
[[ -f "$NGINX_SITE" ]] || die "Nginx access site missing."
[[ -f "$RUNTIME_ENV" ]] || die "Runtime environment missing."
[[ -d "$DATA_ROOT/runtime" ]] || die "Runtime state directory missing."

PANEL_USER="$(awk -F= '$1=="MITIGATE_AI_PANEL_USERNAME" {sub(/^[^=]*=/, ""); gsub(/^["'\'' ]+|["'\'' ]+$/, ""); print; exit}' "$RUNTIME_ENV")"
PANEL_PASS="$(awk -F= '$1=="MITIGATE_AI_PANEL_PASSWORD" {sub(/^[^=]*=/, ""); gsub(/^["'\'' ]+|["'\'' ]+$/, ""); print; exit}' "$RUNTIME_ENV")"

[[ -n "$PANEL_USER" ]] || die "Panel username missing."
[[ -n "$PANEL_PASS" ]] || die "Panel password missing."

install -d -m 0755 "$STATIC_DIR" "$BACKUP_DIR"

RUNTIME_UID="$(stat -c '%u' "$DATA_ROOT/runtime")"
RUNTIME_GID="$(stat -c '%g' "$DATA_ROOT/runtime")"
install -d -o "$RUNTIME_UID" -g "$RUNTIME_GID" -m 0700 "$APPROVAL_STATE_DIR" "$PROVIDER_SECRET_DIR"

for path in "$INTEGRATION_SNIPPET" "$APPROVAL_SNIPPET" "$RUNTIME_STATIC_JS" "$APPROVAL_STATIC_JS" "$LLM_STATIC_JS"; do
    if [[ -f "$path" ]]; then
        cp -a "$path" "$BACKUP_DIR/$(basename "$path").before"
    fi
done

install -m 0644 "$RUNTIME_SOURCE_JS" "$RUNTIME_STATIC_JS"
install -m 0644 "$APPROVAL_SOURCE_JS" "$APPROVAL_STATIC_JS"
install -m 0644 "$LLM_SOURCE_JS" "$LLM_STATIC_JS"
install -m 0644 "$APPROVAL_SOURCE_SNIPPET" "$APPROVAL_SNIPPET"

AUTH_VALUE="$(printf '%s:%s' "$PANEL_USER" "$PANEL_PASS" | base64 -w0)"
cat > "$AUTH_SNIPPET" <<EOF_AUTH
proxy_set_header Authorization "Basic ${AUTH_VALUE}";
EOF_AUTH
chmod 0600 "$AUTH_SNIPPET"

cat > "$INTEGRATION_SNIPPET" <<EOF_NGINX
# MITIGATE Canvas UI integration.
# Repository-managed external layer; upstream Agent Canvas files are never modified.
# This file intentionally contains no standalone /mitigate-panel route.

location = /mitigate-overlay.js {
    alias ${RUNTIME_STATIC_JS};
    default_type application/javascript;
    add_header Cache-Control "no-store";
}

location = /mitigate-llm-provider-overlay.js {
    alias ${LLM_STATIC_JS};
    default_type application/javascript;
    add_header Cache-Control "no-store";
}

# Fixed-destination OpenCode Zen connectivity probe. The browser sends the
# candidate Zen key only in a custom header; Nginx converts it to the upstream
# Bearer credential. No arbitrary destination or raw proxy URL is accepted.
location ^~ /mitigate-llm/opencode/ {
    proxy_pass https://opencode.ai/zen/v1/;
    proxy_http_version 1.1;
    proxy_ssl_server_name on;
    proxy_ssl_name opencode.ai;
    proxy_set_header Host opencode.ai;
    proxy_set_header Authorization "Bearer \$http_x_mitigate_llm_key";
    proxy_set_header X-Mitigate-LLM-Key "";
    proxy_set_header Accept-Encoding "";
    proxy_buffering off;
    proxy_read_timeout 30s;
    proxy_send_timeout 30s;
    add_header Cache-Control "no-store" always;
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

# Authenticated same-origin handoff from the Canvas provider card to MITIGATE's
# private runtime provider store. The key never enters Git, Nginx config, query
# strings or browser storage.
location = /mitigate-runtime/provider/opencode {
    include ${AUTH_SNIPPET};

    proxy_pass http://127.0.0.1:8766/api/providers/opencode;
    proxy_http_version 1.1;
    proxy_set_header Host 127.0.0.1;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_buffering off;
    client_max_body_size 16k;
}

include ${APPROVAL_SNIPPET};

location ^~ /canvas {
    proxy_pass ${CANVAS_UPSTREAM};

    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Accept-Encoding "";

    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_buffering off;

    sub_filter_once on;
    sub_filter '</body>' '<script defer src="/mitigate-overlay.js"></script><script defer src="/mitigate-approval-overlay.js"></script><script defer src="/mitigate-llm-provider-overlay.js"></script></body>';
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
    "    include /etc/nginx/snippets/mitigate-ai-canvas-integration.conf;\n\n"
)
if marker not in text:
    raise SystemExit("ERROR: nginx location marker not found")
path.write_text(text.replace(marker, include + marker, 1))
PY
fi

nginx -t
systemctl reload nginx

[[ "$(systemctl is-active nginx)" == "active" ]] || die "Nginx not active after reload."
curl -fsS --max-time 5 http://127.0.0.1:8766/healthz >/dev/null || die "Canvas API health failed."
grep -q 'mitigate-runtime-overlay.js' "$INTEGRATION_SNIPPET" || die "Runtime overlay injection missing."
grep -q 'mitigate-approval-overlay.js' "$INTEGRATION_SNIPPET" || die "Approval overlay injection missing."
grep -q 'mitigate-llm-provider-overlay.js' "$INTEGRATION_SNIPPET" || die "LLM provider overlay injection missing."
grep -q 'opencode.ai/zen/v1' "$INTEGRATION_SNIPPET" || die "OpenCode Zen probe route missing."
grep -q '/mitigate-runtime/provider/opencode' "$INTEGRATION_SNIPPET" || die "OpenCode runtime sync route missing."
if grep -q 'location .*mitigate-panel' "$INTEGRATION_SNIPPET"; then
    die "Legacy standalone mitigate-panel route still present."
fi

echo "CANVAS_UI_INTEGRATION_INSTALLED=yes"
echo "MITIGATE_RUNTIME_OVERLAY=ACTIVE"
echo "MITIGATE_APPROVAL_OVERLAY=ACTIVE"
echo "MITIGATE_LLM_PROVIDER_OVERLAY=ACTIVE"
echo "MITIGATE_OPENCODE_ZEN_PROBE=ACTIVE"
echo "MITIGATE_OPENCODE_RUNTIME_SYNC=ACTIVE"
echo "MITIGATE_APPROVAL_AUDIT_STORAGE=ACTIVE"
echo "MITIGATE_STANDALONE_PANEL=REMOVED"
echo "UPSTREAM_CANVAS_FILES_MODIFIED=no"
echo "CANVAS_UPDATE_SURVIVAL=repository_managed_nginx_overlay"
echo "BACKUP_DIR=$BACKUP_DIR"
