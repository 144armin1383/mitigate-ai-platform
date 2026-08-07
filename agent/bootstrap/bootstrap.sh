#!/usr/bin/env bash
set -Eeuo pipefail

# MITIGATE AI portable bootstrap: Python 3.12 virtual environment
# Contract requirements implemented:
# - Verifies a Python interpreter is available
# - Requires Python 3.12-compatible execution
# - Creates agent/.venv when missing
# - Validates agent/.venv when already present
# - Validates the virtualenv Python executable

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
AGENT_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
VENV_DIR="${AGENT_DIR}/.venv"           # must be agent/.venv
PYTHON_BIN="python3.12"                 # require python3.12-compatible execution
VENV_PY="${VENV_DIR}/bin/python"        # validate bin/python

echo "[mitigate-ai] Bootstrap starting"

# 1) Verify python3.12 is available on PATH
if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Error: python3.12 not found in PATH. This project requires Python 3.12." >&2
  echo "Please install Python 3.12 and ensure 'python3.12' is available on PATH." >&2
  exit 1
fi

# 2) Create agent/.venv when missing using python3.12 -m venv
if [ ! -d "${VENV_DIR}" ]; then
  echo "[mitigate-ai] Creating virtual environment at agent/.venv using python3.12 -m venv"
  python3.12 -m venv "${VENV_DIR}"
fi

# 3) Validate agent/.venv directory
if [ ! -d "${VENV_DIR}" ]; then
  echo "Error: expected virtual environment directory at ${VENV_DIR} was not created." >&2
  exit 1
fi

# 4) Validate the virtualenv Python executable exists
if [ ! -x "${VENV_PY}" ]; then
  echo "Error: expected virtualenv Python executable not found at ${VENV_PY} (bin/python)." >&2
  echo "If this environment was created with a different interpreter, remove ${VENV_DIR} and re-run this script." >&2
  exit 1
fi

# 5) Validate the virtualenv Python version is 3.12.x
VENV_PY_VERSION="$(${VENV_PY} -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
if [ "${VENV_PY_VERSION}" != "3.12" ]; then
  echo "Error: agent/.venv/bin/python is Python ${VENV_PY_VERSION}, but Python 3.12 is required." >&2
  echo "Please remove ${VENV_DIR} and recreate it with: python3.12 -m venv agent/.venv" >&2
  exit 1
fi

# 6) Basic execution sanity check (no network actions performed)
if ! "${VENV_PY}" -c 'import sys; sys.exit(0)'; then
  echo "Error: agent/.venv/bin/python failed basic execution test." >&2
  exit 1
fi

# Success summary (no protected values printed)
echo "[mitigate-ai] Virtual environment ready at agent/.venv"
echo "[mitigate-ai] Detected interpreter: $(${VENV_PY} -V 2>&1)"
echo "[mitigate-ai] Usage example: ${VENV_DIR}/bin/python -m pip --help"

exit 0
