#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve repository root relative to this script location (portable, caller-agnostic)
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

# Export for downstream tools that rely on this being present in the environment
export REPO_ROOT

# Basic, safe validation helpers (no side effects beyond checks)
die() {
  echo "bootstrap: $*" >&2
  exit 1
}

# Ensure Python is available (do not attempt to install or modify system)
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 is required but was not found in PATH"

# Virtual environment validation (do not create or mutate)
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
VENV_PY=""
if [ -d "${VENV_DIR}" ] && [ -x "${VENV_DIR}/bin/python" ]; then
  VENV_PY="${VENV_DIR}/bin/python"
fi

# If a venv is present, ensure it looks sane without executing arbitrary code
if [ -n "${VENV_PY}" ] && [ ! -f "${VENV_DIR}/pyvenv.cfg" ]; then
  die ".venv appears corrupted: missing pyvenv.cfg"
fi

# No direct Git execution, no deployment, and no network access here — portable bootstrap only.

# Provide a quiet success path for callers that source this script
return 0 2>/dev/null || exit 0
