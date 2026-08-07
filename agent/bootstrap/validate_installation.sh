#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve script and repository root from physical location, not caller working directory
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

VENV_DIR="${REPO_ROOT}/agent/.venv"
VENV_PY="${VENV_DIR}/bin/python"

# Utility: print to stderr
note() { printf '%s\n' "$*" 1>&2; }

# Track validation outcome
ALL_OK=1

mark_fail() { ALL_OK=0; note "ERROR: $*"; }

# Validation: repository layout
validate_layout() {
  local ok=1
  [ -d "${REPO_ROOT}/agent" ] || { mark_fail "Missing directory: agent"; ok=0; }
  [ -d "${REPO_ROOT}/agent/bootstrap" ] || { mark_fail "Missing directory: agent/bootstrap"; ok=0; }
  [ -f "${REPO_ROOT}/agent/bootstrap/bootstrap.sh" ] || { mark_fail "Missing file: agent/bootstrap/bootstrap.sh"; ok=0; }
  [ -f "${REPO_ROOT}/agent/bootstrap/validate_installation.sh" ] || { mark_fail "Missing file: agent/bootstrap/validate_installation.sh"; ok=0; }
  # Common project bootstrap configuration templates typically present in repo root
  [ -f "${REPO_ROOT}/env.example" ] || note "INFO: Optional file not found: env.example"
  [ -f "${REPO_ROOT}/project.example.json" ] || note "INFO: Optional file not found: project.example.json"
  # Project documentation marker
  [ -f "${REPO_ROOT}/README.md" ] || note "INFO: README.md not found at repository root"
  return $ok
}

# Determine if a python interpreter is 3.12-compatible (>= 3.12)
py_is_312_compatible() {
  local pybin="$1"
  [ -x "$pybin" ] || return 1
  "$pybin" -c 'import sys; raise SystemExit(0 if (sys.version_info[:2] >= (3, 12)) else 1)' >/dev/null 2>&1 || return 1
  return 0
}

# Validation: python interpreter availability (system-level, without creating anything)
validate_python_availability() {
  local candidate=""
  if command -v python3.12 >/dev/null 2>&1 && py_is_312_compatible "$(command -v python3.12)"; then
    candidate="$(command -v python3.12)"
  elif command -v python3 >/dev/null 2>&1 && py_is_312_compatible "$(command -v python3)"; then
    candidate="$(command -v python3)"
  elif command -v python >/dev/null 2>&1 && py_is_312_compatible "$(command -v python)"; then
    candidate="$(command -v python)"
  fi
  if [ -z "$candidate" ]; then
    mark_fail "No Python 3.12-compatible interpreter found (checked python3.12, python3, python)"
    return 1
  fi
  note "INFO: Found Python interpreter: $candidate"
  return 0
}

# Validation: virtualenv existence and interpreter executability
validate_virtualenv() {
  local ok=1
  if [ ! -d "$VENV_DIR" ]; then
    mark_fail "Virtual environment not found: agent/.venv (run bootstrap to create it)"
    ok=0
  else
    [ -x "$VENV_PY" ] || { mark_fail "Virtual environment python missing or not executable: agent/.venv/bin/python"; ok=0; }
    if [ -x "$VENV_PY" ] && ! py_is_312_compatible "$VENV_PY"; then
      mark_fail "Virtual environment interpreter is not Python 3.12-compatible: agent/.venv/bin/python"
      ok=0
    fi
  fi
  return $ok
}

# Validation: critical Python package/module presence (local/offline)
# Only performs import checks if a virtualenv python is available
validate_python_modules() {
  if [ ! -x "$VENV_PY" ]; then
    note "INFO: Skipping module import checks; virtual environment python not available"
    return 0
  fi
  # Verify stdlib and repository package importability without network calls
  if ! "$VENV_PY" - <<'PY'
import sys, os, importlib
# Ensure repository root is importable
repo_root = os.environ.get('REPO_ROOT', '')
if repo_root and repo_root not in sys.path:
    sys.path.insert(0, repo_root)
# Basic stdlib check
import json  # noqa: F401
# Attempt to import the local agent package if present
try:
    importlib.import_module('agent')
except Exception:
    # Non-fatal: repository may structure packages differently
    pass
PY
  then
    mark_fail "Python import checks failed under the virtual environment"
    return 1
  fi
  return 0
}

# Validation: bootstrap configuration and project template presence (non-fatal hints)
validate_bootstrap_assets() {
  # Presence of bootstrap scripts already validated; here we check additional common assets
  [ -d "${REPO_ROOT}/agent/bootstrap" ] || mark_fail "Missing directory: agent/bootstrap"
  # Memory/recovery assets presence hints (non-fatal)
  if [ -d "${REPO_ROOT}/agent/recovery" ] || [ -d "${REPO_ROOT}/recovery" ] || [ -d "${REPO_ROOT}/agent/state" ]; then
    note "INFO: Found recovery/state assets"
  else
    note "INFO: Recovery/state assets directory not found (optional)"
  fi
  return 0
}

# Validation: provider/site adapter identifier syntax (if such directories exist)
# Strategy: if adapter directories exist, ensure filenames are alphanumeric, dash, underscore, or dot.
validate_adapter_identifiers() {
  local dirs=()
  [ -d "${REPO_ROOT}/adapters/providers" ] && dirs+=("${REPO_ROOT}/adapters/providers")
  [ -d "${REPO_ROOT}/adapters/sites" ] && dirs+=("${REPO_ROOT}/adapters/sites")
  [ -d "${REPO_ROOT}/agent/adapters/providers" ] && dirs+=("${REPO_ROOT}/agent/adapters/providers")
  [ -d "${REPO_ROOT}/agent/adapters/sites" ] && dirs+=("${REPO_ROOT}/agent/adapters/sites")
  local d f base
  for d in "${dirs[@]:-}"; do
    [ -d "$d" ] || continue
    for f in "$d"/*; do
      [ -e "$f" ] || continue
      base="$(basename -- "$f")"
      # Allow letters, numbers, underscore, dash, dot, and common extensions
      if [[ "$base" =~ ^[A-Za-z0-9._-]+$ ]]; then
        :
      else
        mark_fail "Invalid adapter identifier: ${base} in ${d}"
      fi
    done
  done
  return 0
}

main() {
  export REPO_ROOT
  validate_layout || true
  validate_python_availability || true
  validate_virtualenv || true
  validate_python_modules || true
  validate_bootstrap_assets || true
  validate_adapter_identifiers || true

  if [ "$ALL_OK" -eq 1 ]; then
    note "Validation completed successfully"
    exit 0
  else
    note "Validation reported one or more issues"
    exit 1
  fi
}

main "$@"
