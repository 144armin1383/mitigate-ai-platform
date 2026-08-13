#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
CURRENT="$RUNTIME_ROOT/npm"
TARGET="${1:-latest}"

log() {
    printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."

if [[ "$TARGET" == "latest" ]]; then
    TARGET="$(npm view ruflo version)"
fi

CURRENT_VERSION="missing"

if [[ -x "$CURRENT/node_modules/.bin/ruflo" ]]; then
    CURRENT_VERSION="$(
        "$CURRENT/node_modules/.bin/ruflo" --version \
        | sed -E 's/^ruflo v//'
    )"
fi

log "Ruflo current=$CURRENT_VERSION target=$TARGET"

if [[ "$CURRENT_VERSION" == "$TARGET" ]]; then
    echo "RUFLO_ALREADY_CURRENT=yes"
    exit 0
fi

CANDIDATE="$RUNTIME_ROOT/npm.ruflo-candidate.$$"

mkdir -p "$CANDIDATE"

OPENCLAW_VERSION="$(
    "$CURRENT/node_modules/.bin/openclaw" --version \
    | sed -E 's/^OpenClaw ([^ ]+).*/\1/'
)"

npm install \
    --prefix "$CANDIDATE" \
    "openclaw@$OPENCLAW_VERSION" \
    "ruflo@$TARGET"

"$CANDIDATE/node_modules/.bin/openclaw" --version
"$CANDIDATE/node_modules/.bin/ruflo" --version

rm -rf "$CURRENT/node_modules"
mv "$CANDIDATE/node_modules" "$CURRENT/node_modules"

rm -f "$CURRENT/package-lock.json"
[[ -f "$CANDIDATE/package-lock.json" ]] \
    && mv "$CANDIDATE/package-lock.json" "$CURRENT/package-lock.json"

rm -rf "$CANDIDATE"

systemctl restart mitigate-ai-worker.service
sleep 3

[[ "$(systemctl is-active mitigate-ai-worker.service)" == "active" ]] \
    || die "Worker failed after Ruflo upgrade."

VERSION="$(
    "$CURRENT/node_modules/.bin/ruflo" --version \
    | sed -E 's/^ruflo v//'
)"

[[ "$VERSION" == "$TARGET" ]] || die "Ruflo version verification failed."

echo "RUFLO_UPGRADE=OK"
echo "RUFLO_VERSION=$TARGET"
