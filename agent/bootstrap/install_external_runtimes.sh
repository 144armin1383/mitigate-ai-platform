#!/usr/bin/env bash

set -euo pipefail

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
RUNTIME_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
VENV="${MITIGATE_EXTERNAL_RUNTIME_VENV:-$RUNTIME_ROOT/venv}"

OPENHANDS_VERSION="${MITIGATE_OPENHANDS_VERSION:-1.24.0}"
OPENCLAW_VERSION="${MITIGATE_OPENCLAW_VERSION:-2026.7.1}"
RUFLO_VERSION="${MITIGATE_RUFLO_VERSION:-3.38.8}"

INSTALL_RUFLO="${MITIGATE_INSTALL_RUFLO:-0}"

printf '%s\n' "=================================================="
printf '%s\n' "MITIGATE EXTERNAL RUNTIME BOOTSTRAP"
printf '%s\n' "=================================================="

mkdir -p "$RUNTIME_ROOT"

if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

python -m pip install --upgrade pip
python -m pip install --upgrade \
    "openhands-sdk==$OPENHANDS_VERSION" \
    "openhands-tools==$OPENHANDS_VERSION"

if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: Node.js is required for OpenClaw/Ruflo. Install supported Node first."
    exit 20
fi

NODE_VERSION="$(node -p 'process.versions.node')"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 22 ]; then
    echo "ERROR: OpenClaw requires a supported Node 22+/24+/26 runtime."
    exit 21
fi

NPM_PREFIX="${MITIGATE_RUNTIME_NPM_PREFIX:-$RUNTIME_ROOT/npm}"
mkdir -p "$NPM_PREFIX"

npm install --prefix "$NPM_PREFIX" \
    "openclaw@$OPENCLAW_VERSION"

if [ "$INSTALL_RUFLO" = "1" ]; then
    npm install --prefix "$NPM_PREFIX" \
        "ruflo@$RUFLO_VERSION"
fi

BIN_DIR="$NPM_PREFIX/node_modules/.bin"

echo
echo "=== INSTALLED ==="
echo "external_runtime_root=$RUNTIME_ROOT"
echo "external_runtime_venv=$VENV"
echo "node=$NODE_VERSION"

python - <<'PY'
import importlib.metadata as metadata
for package in ("openhands-sdk", "openhands-tools"):
    try:
        print(f"{package}={metadata.version(package)}")
    except metadata.PackageNotFoundError:
        print(f"{package}=missing")
PY

if [ -x "$BIN_DIR/openclaw" ]; then
    "$BIN_DIR/openclaw" --version || true
else
    echo "openclaw=missing"
fi

if [ "$INSTALL_RUFLO" = "1" ]; then
    if [ -x "$BIN_DIR/ruflo" ]; then
        "$BIN_DIR/ruflo" --version || true
    else
        echo "ruflo=missing"
    fi
else
    echo "ruflo=not-installed-benchmark-gated"
fi

echo
echo "RUNTIME_BIN_DIR=$BIN_DIR"
echo "PRODUCTION_VENV_CHANGED=no"
echo "NEXT: expose this isolated runtime to MITIGATE only after compatibility tests pass."
