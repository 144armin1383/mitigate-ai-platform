#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

RUNTIME_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
CURRENT="$RUNTIME_ROOT/npm"
TARGET="${1:-latest}"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
[[ -d "$CURRENT" ]] || die "Runtime npm directory missing."

if [[ "$TARGET" == "latest" ]]; then
    TARGET="$(npm view openclaw version)"
fi

OPENCLAW_BIN="$CURRENT/node_modules/.bin/openclaw"
RUFLO_BIN="$CURRENT/node_modules/.bin/ruflo"

CURRENT_VERSION="$(
    "$OPENCLAW_BIN" --version |
    sed -E 's/^OpenClaw ([^ ]+).*/\1/'
)"

RUFLO_VERSION="$(
    "$RUFLO_BIN" --version |
    sed -E 's/^ruflo v//'
)"

echo "OPENCLAW_CURRENT=$CURRENT_VERSION"
echo "OPENCLAW_TARGET=$TARGET"

if [[ "$CURRENT_VERSION" == "$TARGET" ]]; then
    echo "OPENCLAW_ALREADY_CURRENT=yes"
    exit 0
fi

CANDIDATE="$RUNTIME_ROOT/npm.openclaw-candidate.$$"
BACKUP="$RUNTIME_ROOT/npm.openclaw-rollback.$$"

OWNER_UID="$(stat -c '%u' "$CURRENT")"
OWNER_GID="$(stat -c '%g' "$CURRENT")"

cleanup_candidate() {
    rm -rf "$CANDIDATE"
}

trap cleanup_candidate EXIT

mkdir -p "$CANDIDATE"

npm init --prefix "$CANDIDATE" -y >/dev/null 2>&1

npm install \
    --save-exact \
    --prefix "$CANDIDATE" \
    "openclaw@$TARGET" \
    "ruflo@$RUFLO_VERSION"

"$CANDIDATE/node_modules/.bin/openclaw" --version
"$CANDIDATE/node_modules/.bin/ruflo" --version

TEST_VERSION="$(
    "$CANDIDATE/node_modules/.bin/openclaw" --version |
    sed -E 's/^OpenClaw ([^ ]+).*/\1/'
)"

[[ "$TEST_VERSION" == "$TARGET" ]] ||
    die "OpenClaw candidate verification failed."

chown -R "$OWNER_UID:$OWNER_GID" "$CANDIDATE"

mv "$CURRENT" "$BACKUP"
mv "$CANDIDATE" "$CURRENT"

rollback() {
    local code=$?

    if [[ "$code" -eq 0 ]]; then
        return
    fi

    trap - EXIT

    echo "OPENCLAW_ROLLBACK=yes"

    rm -rf "$CURRENT"
    mv "$BACKUP" "$CURRENT"

    systemctl restart mitigate-ai-worker.service || true

    exit "$code"
}

trap rollback EXIT

systemctl restart mitigate-ai-worker.service
sleep 3

[[ "$(systemctl is-active mitigate-ai-worker.service)" == "active" ]] ||
    die "Worker failed after OpenClaw upgrade."

FINAL_VERSION="$(
    "$CURRENT/node_modules/.bin/openclaw" --version |
    sed -E 's/^OpenClaw ([^ ]+).*/\1/'
)"

[[ "$FINAL_VERSION" == "$TARGET" ]] ||
    die "OpenClaw final verification failed."

rm -rf "$BACKUP"

trap - EXIT

echo "OPENCLAW_UPGRADE=OK"
echo "OPENCLAW_VERSION=$TARGET"
