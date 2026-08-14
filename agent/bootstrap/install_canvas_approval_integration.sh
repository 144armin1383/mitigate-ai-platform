#!/usr/bin/env bash

set -euo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
CANVAS_SNIPPET="${MITIGATE_CANVAS_NGINX_SNIPPET:-/etc/nginx/snippets/mitigate-ai-canvas-integration.conf}"
APPROVAL_SNIPPET="/etc/nginx/snippets/mitigate-ai-canvas-approval.conf"
ASSET_DIR="/usr/local/share/mitigate-ai"
ASSET="$ASSET_DIR/mitigate-approval-overlay.js"
SOURCE_ASSET="$ROOT/agent/web/canvas_approval_overlay.js"
SOURCE_SNIPPET="$ROOT/agent/deploy/nginx/mitigate-ai-canvas-approval.conf"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/etc/mitigate-ai/nginx-backups/$STAMP"

cd "$ROOT"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[ "$(git branch --show-current)" = "main" ] || fail "expected main branch"
[ -z "$(git status --porcelain)" ] || fail "canonical repository is not clean"
[ -f "$SOURCE_ASSET" ] || fail "approval overlay source missing"
[ -f "$SOURCE_SNIPPET" ] || fail "approval nginx fragment missing"
[ -f "$CANVAS_SNIPPET" ] || fail "existing Canvas integration snippet missing"
[ "$(systemctl is-active nginx)" = "active" ] || fail "nginx is not active"
[ "$(systemctl is-active mitigate-ai-panel.service)" = "active" ] || fail "MITIGATE panel is not active"

sudo mkdir -p "$BACKUP_DIR" "$ASSET_DIR"
sudo cp -a "$CANVAS_SNIPPET" "$BACKUP_DIR/mitigate-ai-canvas-integration.conf.before"
if [ -f "$APPROVAL_SNIPPET" ]; then
  sudo cp -a "$APPROVAL_SNIPPET" "$BACKUP_DIR/mitigate-ai-canvas-approval.conf.before"
fi
if [ -f "$ASSET" ]; then
  sudo cp -a "$ASSET" "$BACKUP_DIR/mitigate-approval-overlay.js.before"
fi

rollback() {
  local reason="$1"
  echo "ROLLBACK_REASON=$reason"
  sudo cp -a "$BACKUP_DIR/mitigate-ai-canvas-integration.conf.before" "$CANVAS_SNIPPET"
  if [ -f "$BACKUP_DIR/mitigate-ai-canvas-approval.conf.before" ]; then
    sudo cp -a "$BACKUP_DIR/mitigate-ai-canvas-approval.conf.before" "$APPROVAL_SNIPPET"
  else
    sudo rm -f "$APPROVAL_SNIPPET"
  fi
  if [ -f "$BACKUP_DIR/mitigate-approval-overlay.js.before" ]; then
    sudo cp -a "$BACKUP_DIR/mitigate-approval-overlay.js.before" "$ASSET"
  else
    sudo rm -f "$ASSET"
  fi
  sudo nginx -t >/dev/null 2>&1 && sudo systemctl reload nginx || true
  exit 30
}

sudo install -m 0644 "$SOURCE_ASSET" "$ASSET"
sudo install -m 0644 "$SOURCE_SNIPPET" "$APPROVAL_SNIPPET"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
sudo cat "$CANVAS_SNIPPET" > "$TMP"

python3 - "$TMP" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

include_line = "include /etc/nginx/snippets/mitigate-ai-canvas-approval.conf;"
if include_line not in text:
    text = text.rstrip() + "\n\n# MITIGATE_CANVAS_APPROVAL_INCLUDE\n" + include_line + "\n"

script = '<script defer src="/mitigate-approval-overlay.js"></script>'
if script not in text:
    pattern = re.compile(r"(sub_filter\s+'</body>'\s+'[^']*)(</body>'\s*;)")
    match = pattern.search(text)
    if not match:
        raise SystemExit("canvas_sub_filter_marker_missing")
    text = text[:match.start()] + match.group(1) + script + match.group(2) + text[match.end():]

path.write_text(text, encoding="utf-8")
PY

sudo install -m 0644 "$TMP" "$CANVAS_SNIPPET"

if ! sudo nginx -t; then
  rollback "nginx_validation_failed"
fi

sudo systemctl reload nginx
sleep 2

[ "$(systemctl is-active nginx)" = "active" ] || rollback "nginx_not_active_after_reload"
curl -fsS --max-time 5 http://127.0.0.1:8766/healthz >/dev/null || rollback "panel_health_failed"

grep -q 'mitigate-approval-overlay.js' "$CANVAS_SNIPPET" || rollback "overlay_injection_missing"
grep -q 'mitigate-ai-canvas-approval.conf' "$CANVAS_SNIPPET" || rollback "approval_include_missing"
grep -q 'MITIGATE_CANVAS_APPROVAL_INTEGRATION' "$APPROVAL_SNIPPET" || rollback "approval_route_missing"

[ -z "$(git status --porcelain)" ] || rollback "canonical_repository_became_dirty"

printf '%s\n' \
  "CANVAS_APPROVAL_INTEGRATION=ACTIVE" \
  "CANVAS_SOURCE_MODIFIED=no" \
  "CANVAS_UPDATE_SURVIVAL=external_nginx_overlay" \
  "APPROVAL_OVERLAY=$ASSET" \
  "APPROVAL_ROUTE=/mitigate-runtime/api/" \
  "BACKUP_DIR=$BACKUP_DIR" \
  "NGINX=active" \
  "PANEL=active" \
  "REPOSITORY_CLEAN=yes"
