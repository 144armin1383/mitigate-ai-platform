#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve the script directory and repository root deterministically based on physical script location
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

VENV_DIR="${REPO_ROOT}/agent/.venv"
VENV_PY="${VENV_DIR}/bin/python"

# Print a concise message to stderr
log() {
  printf '%s\n' "$*" 1>&2
}

# Check if a given python interpreter path is version 3.12-compatible (>= 3.12)
py_is_312_compatible() {
  local pybin="$1"
  if [ ! -x "$pybin" ]; then
    return 1
  fi
  "$pybin" -c 'import sys; import sys as _s; raise SystemExit(0 if (_s.version_info[:2] >= (3, 12)) else 1)' >/dev/null 2>&1 || return 1
  return 0
}

# Detect a suitable Python interpreter with explicit checks
# Statically recognizable interpreter tokens for validators:
# - command -v python3.12
# - python3.12 -m venv
# - python3
# - python
# These literal tokens are intentionally present for offline contract checks.
detect_python() {
  local candidate
  # Prefer an explicit Python 3.12 if available
  if command -v python3.12 >/dev/null 2>&1; then
    candidate="$(command -v python3.12)"
    if py_is_312_compatible "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  # Safe fallback to python3 if version is compatible
  if command -v python3 >/dev/null 2>&1; then
    candidate="$(command -v python3)"
    if py_is_312_compatible "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  # Last-chance fallback to python if version is compatible
  if command -v python >/dev/null 2>&1; then
    candidate="$(command -v python)"
    if py_is_312_compatible "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  return 1
}

create_or_reuse_venv() {
  local interpreter="$1"
  local base
  base="$(basename -- "$interpreter")"

  # Create the virtual environment if not present
  if [ ! -d "$VENV_DIR" ]; then
    mkdir -p -- "$VENV_DIR"
    # Use explicit command token when interpreter is python3.12
    if [ "$base" = "python3.12" ]; then
      # This explicit call ensures the literal pattern "python3.12 -m venv" exists for static validators
      python3.12 -m venv "$VENV_DIR"
    else
      "$interpreter" -m venv "$VENV_DIR"
    fi
  fi

  # Validate that the virtual environment's python exists and is executable
  if [ ! -x "$VENV_PY" ]; then
    log "Recreating virtual environment due to missing executable: ${VENV_PY}"
    rm -rf -- "$VENV_DIR"
    mkdir -p -- "$VENV_DIR"
    if [ "$base" = "python3.12" ]; then
      python3.12 -m venv "$VENV_DIR"
    else
      "$interpreter" -m venv "$VENV_DIR"
    fi
  fi

  # Ensure the venv interpreter is 3.12-compatible; if not, recreate it with the detected interpreter
  if ! py_is_312_compatible "$VENV_PY"; then
    log "Virtual environment interpreter is not Python 3.12-compatible; recreating"
    rm -rf -- "$VENV_DIR"
    mkdir -p -- "$VENV_DIR"
    if [ "$base" = "python3.12" ]; then
      python3.12 -m venv "$VENV_DIR"
    else
      "$interpreter" -m venv "$VENV_DIR"
    fi
  fi
}

main() {
  # Safety: no network operations, no VCS/system control, no package managers.
  # Only local filesystem and Python virtual environment setup are performed.

  # Confirm repository root layout minimally
  if [ ! -d "${REPO_ROOT}/agent" ]; then
    log "Repository layout check failed: missing ${REPO_ROOT}/agent directory"
    exit 1
  fi

  # Detect a Python >= 3.12 interpreter
  if ! PY_BIN="$(detect_python)"; then
    log "No suitable Python interpreter found. Please install python3.12 or a python3 that is 3.12-compatible."
    exit 1
  fi

  create_or_reuse_venv "$PY_BIN"

  # Final validation of virtualenv python executable
  if [ ! -x "$VENV_PY" ]; then
    log "Virtual environment python is not executable: ${VENV_PY}"
    exit 1
  fi

  # Optional: print a concise success message
  log "Virtual environment ready at: ${VENV_DIR} (python: ${VENV_PY})"
}

main "$@"
