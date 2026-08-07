#!/usr/bin/env bash

# Portable Installation Validation for MITIGATE AI
# - Validates repository layout, interpreter, venv, and runtime entrypoints
# - No network or provider contact

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"

if [ ! -d "${REPO_ROOT}/agent" ]; then
  echo "[ERROR] agent directory missing in repository root: ${REPO_ROOT}" >&2
  exit 12
fi

# Python detection (require 3.12+)
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

# Virtualenv
VENV_DIR="${REPO_ROOT}/agent/.venv"
if [ ! -d "${VENV_DIR}" ] || [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "[ERROR] Virtual environment not found or invalid at ${VENV_DIR}" >&2
  exit 14
fi
VENV_PY="${VENV_DIR}/bin/python"

# Repository layout
REQ_DIRS=(
  "agent/ai"
  "agent/runtime"
  "agent/api"
  "agent/orchestrator"
  "agent/autonomy"
  "agent/memory"
  "agent/operations"
  "agent/missions"
  "agent/tests"
  "agent/deploy"
)
MISSING=0
for d in "${REQ_DIRS[@]}"; do
  if [ ! -d "${REPO_ROOT}/${d}" ]; then
    echo "[ERROR] Missing required directory: ${d}" >&2
    MISSING=1
  fi
done
if [ ${MISSING} -ne 0 ]; then
  exit 12
fi

# Safe config exists (env example must exist; .env may or may not)
if [ ! -f "${REPO_ROOT}/agent/bootstrap/env.example" ]; then
  echo "[ERROR] env.example missing at agent/bootstrap/env.example" >&2
  exit 15
fi
if [ -f "${REPO_ROOT}/.env" ]; then
  echo "[INFO] .env present (not inspected)."
else
  echo "[INFO] .env not present yet. Configure secrets externally before runtime."
fi

# Validate importability of bootstrap modules and runtime entry guesses without contacting providers
# Use Python within venv to avoid system pollution
"${VENV_PY}" - <<'PY'
import sys, pkgutil
mods = [
    'agent.bootstrap.portable_bootstrap',
    'agent.bootstrap.restore_manager',
]
failed = []
for m in mods:
    if pkgutil.find_loader(m) is None:
        failed.append(m)
if failed:
    print("IMPORT_FAILURE:" + ",".join(failed))
    sys.exit(1)
sys.exit(0)
PY
if [ $? -ne 0 ]; then
  echo "[ERROR] Unable to locate critical bootstrap modules." >&2
  exit 20
fi

# Validate default memory schema readability (if memory exists)
MEM_ROOT="${REPO_ROOT}/agent/.data/memory"
if [ -d "${MEM_ROOT}" ]; then
  if ! find "${MEM_ROOT}" -type f -name "*.json" -maxdepth 3 -print -quit | grep -q .; then
    echo "[INFO] No JSON memory files detected (ok for fresh installs)."
  else
    # Try reading a few JSON files safely
    SAMPLE=$(find "${MEM_ROOT}" -type f -name "*.json" -maxdepth 3 | head -n 3)
    OK=0
    while IFS= read -r f; do
      if [ -z "$f" ]; then continue; fi
      "${VENV_PY}" - <<PY
import json, sys, pathlib
p = pathlib.Path(r'''$f''')
try:
    json.loads(p.read_text(encoding='utf-8'))
except Exception:
    sys.exit(2)
sys.exit(0)
PY
      RC=$?
      if [ ${RC} -ne 0 ]; then
        echo "[ERROR] Memory file unreadable JSON: $f" >&2
        exit 15
      fi
      OK=1
    done <<< "${SAMPLE}"
    if [ ${OK} -eq 1 ]; then
      echo "[INFO] Memory schema files are readable."
    fi
  fi
else
  echo "[INFO] Memory root not present (ok)."
fi

# Adapter names syntactic check from environment (optional)
PAT='^[a-z0-9_.-]+$'
if [ -n "${MITIGATE_AI_PROVIDER:-}" ]; then
  if ! [[ "${MITIGATE_AI_PROVIDER}" =~ ${PAT} ]]; then
    echo "[ERROR] Provider adapter name contains invalid characters." >&2
    exit 19
  fi
fi
if [ -n "${MITIGATE_AI_SITE_ADAPTER:-}" ]; then
  if ! [[ "${MITIGATE_AI_SITE_ADAPTER}" =~ ${PAT} ]]; then
    echo "[ERROR] Site adapter name contains invalid characters." >&2
    exit 19
  fi
fi

# Call bootstrap in validate-only mode for a final structured check
set +e
VALIDATE_JSON="$(${VENV_PY} -m agent.bootstrap.portable_bootstrap \
  --repository-root "${REPO_ROOT}" \
  --agent-root "${REPO_ROOT}/agent" \
  --data-root "${REPO_ROOT}/agent/.data" \
  --runtime-data-root "${REPO_ROOT}/agent/.data/runtime" \
  --memory-root "${REPO_ROOT}/agent/.data/memory" \
  --config-root "${REPO_ROOT}/agent/config" \
  --validate-only 2>/dev/null)"
RC=$?
set -e
if [ ${RC} -ne 0 ]; then
  echo "[ERROR] Installation validation failed." >&2
  exit 20
fi

echo "[INFO] Installation validation completed successfully."
exit 0
