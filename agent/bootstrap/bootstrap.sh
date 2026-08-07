#!/usr/bin/env bash

# Portable, console-safe bootstrap for local development.
# - Sets strict bash mode
# - Resolves repository root reliably
# - Validates Python availability and version
# - Creates or validates a local virtual environment
# - Creates local data/memory directories
# - Creates a non-destructive local environment file from template if absent
# - Never prints sensitive values or restricted terms

set -Eeuo pipefail
IFS=$'\n\t'

log() {
  # Neutral log messaging with no sensitive terminology
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" 1>&2
  exit 1
}

on_error() {
  log "Bootstrap encountered an error. See messages above for details."
  exit 1
}

trap on_error ERR

# Resolve this script's directory robustly
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Repository root is two levels above: agent/bootstrap -> repo root
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"

if [[ -z "${REPO_ROOT:-}" || ! -d "$REPO_ROOT" ]]; then
  fail "Unable to resolve repository root."
fi

log "Repository root: $REPO_ROOT"

# Python validation (require Python 3.9+ for modern tooling)
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  fail "python3 not found in PATH. Please install Python 3.9 or newer."
fi

if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'; then
  fail "Python 3.9+ is required."
fi

# Virtual environment setup
VENV_DIR="$REPO_ROOT/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating virtual environment (.venv)."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  log "Virtual environment created at: $VENV_DIR"
else
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    log "Using existing virtual environment at: $VENV_DIR"
  else
    log "Existing .venv missing interpreter. Recreating."
    rm -rf "$VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    log "Virtual environment recreated at: $VENV_DIR"
  fi
fi

# Local directory creation (repository-scoped, safe paths)
LOCAL_STATE_DIR="$REPO_ROOT/.mitigate"
DATA_DIR="$LOCAL_STATE_DIR/data"
MEMORY_DIR="$LOCAL_STATE_DIR/memory"
mkdir -p "$DATA_DIR" "$MEMORY_DIR"
log "Ensured local state directories: $DATA_DIR, $MEMORY_DIR"

# Non-destructive local environment file creation from template
TEMPLATE_ENV="$REPO_ROOT/agent/bootstrap/env.example"
LOCAL_ENV="$REPO_ROOT/.env.local"

if [[ ! -f "$TEMPLATE_ENV" ]]; then
  fail "Template environment file not found: $TEMPLATE_ENV"
fi

if [[ -f "$LOCAL_ENV" ]]; then
  log "Local environment file already present and was not modified: $LOCAL_ENV"
else
  cp "$TEMPLATE_ENV" "$LOCAL_ENV"
  log "Created local environment file from template: $LOCAL_ENV"
  log "Review and update the local configuration outside version control before first use."
fi

log "Bootstrap completed successfully."
exit 0
