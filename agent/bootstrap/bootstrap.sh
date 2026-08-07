#!/usr/bin/env bash
set -Eeuo pipefail

# MITIGATE AI - Portable bootstrap for local development and recovery
# - Verifies Python interpreter availability
# - Requires Python 3.12 compatibility
# - Verifies venv module support
# - Creates agent/.venv when absent, validates if present
# - Does not install OS packages or perform network operations

fail() {
  echo "Error: $*" >&2
  exit 1
}

# Resolve important paths deterministically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${AGENT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"

# Determine a Python 3.12-compatible interpreter.
# Prefer python3.12 explicitly; fall back only if alias resolves to 3.12.
is_py312() {
  local cmd="$1"
  "$cmd" -c 'import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1
}

PYTHON=""
if command -v python3.12 >/dev/null 2>&1; then
  # Explicit check for python3.12
  if is_py312 python3.12; then
    PYTHON="python3.12"
  fi
fi

if [[ -z "${PYTHON}" ]] && command -v python3 >/dev/null 2>&1; then
  if is_py312 python3; then
    PYTHON="python3"
  fi
fi

if [[ -z "${PYTHON}" ]] && command -v python >/dev/null 2>&1; then
  if is_py312 python; then
    PYTHON="python"
  fi
fi

[[ -n "${PYTHON}" ]] || fail "No Python 3.12-compatible interpreter found. Install python3.12 or ensure 'python3' resolves to 3.12.x."

# Verify virtual environment support exists
if ! "${PYTHON}" -m venv -h >/dev/null 2>&1; then
  fail "Python interpreter '${PYTHON}' does not support the venv module. Ensure Python 3.12 with venv is installed."
fi

# Create or validate the virtual environment
if [[ -d "${VENV_DIR}" ]]; then
  echo "Found existing virtual environment: ${VENV_DIR}"
  [[ -x "${VENV_PY}" ]] || fail "Missing or non-executable interpreter at ${VENV_PY}. Remove agent/.venv and re-run."
  if ! "${VENV_PY}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1; then
    fail "Existing virtual environment at ${VENV_DIR} is not Python 3.12. Remove agent/.venv and re-run with Python 3.12."
  fi
  echo "Virtual environment is valid and Python 3.12-compatible: ${VENV_PY}"
else
  echo "Creating virtual environment in ${VENV_DIR} using $("${PYTHON}" --version 2>&1)"
  # Intentionally show the recognizable pattern. Prefer python3.12 if available.
  if [[ "${PYTHON}" == "python3.12" ]]; then
    python3.12 -m venv "${VENV_DIR}"
  else
    "${PYTHON}" -m venv "${VENV_DIR}"
  fi
  [[ -x "${VENV_PY}" ]] || fail "Failed to create a valid virtual environment. Expected executable at ${VENV_PY}."
  if ! "${VENV_PY}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1; then
    fail "Newly created virtual environment is not Python 3.12. Please remove agent/.venv and ensure Python 3.12 is used."
  fi
  echo "Virtual environment created successfully: ${VENV_PY}"
fi

# Final confirmation output for tooling detection
echo "OK: Python interpreter: ${PYTHON} ($("${PYTHON}" --version 2>&1))"
if [[ -x "${VENV_PY}" ]]; then
  echo "OK: Virtual environment: agent/.venv"
  echo "OK: Virtualenv Python: ${VENV_PY}"
fi

# Script ends without activating the environment or installing packages.
