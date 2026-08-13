#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
CURRENT_VENV="$RUNTIME_ROOT/venv"
TARGET="${1:-latest}"

log() {
    printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run with sudo/root."
[[ -x "$CURRENT_VENV/bin/python" ]] || die "OpenHands venv missing."

if [[ "$TARGET" == "latest" ]]; then
    TARGET="$(
        python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen(
    "https://pypi.org/pypi/openhands-sdk/json",
    timeout=20,
) as r:
    print(json.load(r)["info"]["version"])
PY
    )"
fi

CURRENT="$(
    "$CURRENT_VENV/bin/python" -c \
    'import importlib.metadata as m; print(m.version("openhands-sdk"))'
)"

log "OpenHands current=$CURRENT target=$TARGET"

if [[ "$CURRENT" == "$TARGET" ]]; then
    echo "OPENHANDS_ALREADY_CURRENT=yes"
    exit 0
fi

FREE_KB="$(df -Pk / | awk 'NR==2 {print $4}')"
(( FREE_KB >= 5 * 1024 * 1024 )) || die "At least 5GB free disk required."

CANDIDATE="$RUNTIME_ROOT/venv.candidate.$$"
BACKUP="$RUNTIME_ROOT/venv.rollback.$$"

cleanup() {
    rm -rf "$CANDIDATE"
}
trap cleanup EXIT

python3 -m venv "$CANDIDATE"

"$CANDIDATE/bin/python" -m pip install --upgrade pip

"$CANDIDATE/bin/python" -m pip install \
    "openhands-sdk==$TARGET" \
    "openhands-tools==$TARGET"

"$CANDIDATE/bin/python" - <<'PY'
import importlib
import importlib.metadata as metadata

for package in ("openhands-sdk", "openhands-tools"):
    print(package, metadata.version(package))

importlib.import_module("openhands.sdk")
print("OPENHANDS_IMPORT=OK")
PY

CANDIDATE_VERSION="$(
    "$CANDIDATE/bin/python" -c \
    'import importlib.metadata as m; print(m.version("openhands-sdk"))'
)"

[[ "$CANDIDATE_VERSION" == "$TARGET" ]] \
    || die "Candidate version mismatch."

log "Activating OpenHands $TARGET"

mv "$CURRENT_VENV" "$BACKUP"
mv "$CANDIDATE" "$CURRENT_VENV"

rollback() {
    local code=$?

    if [[ "$code" -eq 0 ]]; then
        return
    fi

    trap - EXIT

    echo "OPENHANDS_ROLLBACK=yes"

    rm -rf "$CURRENT_VENV"
    mv "$BACKUP" "$CURRENT_VENV"

    systemctl restart mitigate-ai-worker.service || true

    exit "$code"
}
trap rollback EXIT

systemctl restart mitigate-ai-worker.service
sleep 3

[[ "$(systemctl is-active mitigate-ai-worker.service)" == "active" ]] \
    || die "Worker failed after OpenHands upgrade."

"$CURRENT_VENV/bin/python" - <<PY
import importlib.metadata as metadata

assert metadata.version("openhands-sdk") == "$TARGET"
assert metadata.version("openhands-tools") == "$TARGET"

print("OPENHANDS_RUNTIME_VERIFY=OK")
PY

rm -rf "$BACKUP"

trap - EXIT

echo "OPENHANDS_UPGRADE=OK"
echo "OPENHANDS_VERSION=$TARGET"
