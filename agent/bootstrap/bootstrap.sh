#!/usr/bin/env bash

# Portable Bootstrap Script for MITIGATE AI
# - Bash strict mode
# - No external network calls
# - No credential echoing
# - Deterministic exit codes

set -euo pipefail
IFS=$'\n\t'

# Refuse root unless explicitly allowed
if [ "${ALLOW_ROOT:-0}" != "1" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    echo "[ERROR] Do not run as root. Set ALLOW_ROOT=1 to override (not recommended)." >&2
    exit 1
  fi
fi

# Resolve repository root relative to this script
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"

if [ ! -d "${REPO_ROOT}/agent" ]; then
  echo "[ERROR] Unable to locate repository root. Expected 'agent/' directory at ${REPO_ROOT}" >&2
  exit 12
fi

# Choose Python interpreter (require 3.12+)
USER_PY="${PYTHON:-}"
if [ -n "${USER_PY}" ]; then
  PY_BIN="${USER_PY}"
else
  if command -v python3.12 >/dev/null 2>&1; then
    PY_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
  else
    echo "[ERROR] No Python interpreter found." >&2
    exit 13
  fi
fi

# Verify version is 3.12-compatible
if ! "${PY_BIN}" - <<'PY'
import sys
maj, minr = sys.version_info[:2]
if not (maj == 3 and minr >= 12):
    sys.exit(1)
PY
then
  echo "[ERROR] Python 3.12+ required. Found: $(${PY_BIN} -V 2>&1)" >&2
  exit 13
fi

# Create or validate virtual environment under agent/.venv
VENV_DIR="${REPO_ROOT}/agent/.venv"
if [ ! -d "${VENV_DIR}" ]; then
  echo "[INFO] Creating virtual environment at ${VENV_DIR}"
  "${PY_BIN}" -m venv "${VENV_DIR}" || { echo "[ERROR] Failed to create virtualenv" >&2; exit 14; }
fi

VENV_PY="${VENV_DIR}/bin/python"
if [ ! -x "${VENV_PY}" ]; then
  echo "[ERROR] Virtualenv python missing at ${VENV_PY}" >&2
  exit 14
fi

# Create local data/config directories safely
mkdir -p "${REPO_ROOT}/agent/.data/runtime" || { echo "[ERROR] Failed to create runtime data directory" >&2; exit 15; }
mkdir -p "${REPO_ROOT}/agent/.data/memory" || { echo "[ERROR] Failed to create memory directory" >&2; exit 15; }
mkdir -p "${REPO_ROOT}/agent/config" || { echo "[ERROR] Failed to create config directory" >&2; exit 15; }

# Copy env.example to repo .env only if not present
if [ ! -f "${REPO_ROOT}/.env" ]; then
  if [ -f "${REPO_ROOT}/agent/bootstrap/env.example" ]; then
    cp "${REPO_ROOT}/agent/bootstrap/env.example" "${REPO_ROOT}/.env"
    echo "[INFO] Created ${REPO_ROOT}/.env from env.example (placeholders only). Update with real secrets outside Git."
  else
    echo "[WARN] env.example not found at agent/bootstrap/env.example"
  fi
else
  echo "[INFO] .env already exists. Not overwriting."
fi

# Run portable bootstrap in bootstrap mode (not validate-only)
set +e
BOOTSTRAP_JSON="$(${VENV_PY} -m agent.bootstrap.portable_bootstrap \
  --repository-root "${REPO_ROOT}" \
  --agent-root "${REPO_ROOT}/agent" \
  --data-root "${REPO_ROOT}/agent/.data" \
  --runtime-data-root "${REPO_ROOT}/agent/.data/runtime" \
  --memory-root "${REPO_ROOT}/agent/.data/memory" \
  --config-root "${REPO_ROOT}/agent/config" \
  --environment-name "${MITIGATE_AI_ENVIRONMENT_NAME:-dev}" \
  --default-project-id "${MITIGATE_AI_DEFAULT_PROJECT_ID:-default}" \
  --provider-name "${MITIGATE_AI_PROVIDER:-local}" \
  --provider-adapter "${MITIGATE_AI_PROVIDER:-local}" \
  --site-adapter "${MITIGATE_AI_SITE_ADAPTER:-generic}" \
  --bootstrap 2>/dev/null)"
EC=$?
set -e

if [ ${EC} -ne 0 ]; then
  echo "[ERROR] Portable bootstrap failed with exit ${EC}" >&2
  # Try to extract failure_code
  FCODE=$(printf '%s' "${BOOTSTRAP_JSON}" | sed -n 's/.*"failure_code"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
  case "${FCODE}" in
    invalid_bootstrap_config) exit 10;;
    unsafe_path) exit 11;;
    repository_invalid) exit 12;;
    python_incompatible) exit 13;;
    virtualenv_invalid) exit 14;;
    configuration_invalid) exit 15;;
    memory_restore_failed) exit 16;;
    schema_incompatible) exit 17;;
    project_mismatch) exit 18;;
    adapter_configuration_invalid) exit 19;;
    installation_validation_failed) exit 20;;
    dependency_failed) exit 21;;
    timeout) exit 22;;
    *) exit 1;;
  esac
fi

echo "[INFO] Portable bootstrap completed."
exit 0
