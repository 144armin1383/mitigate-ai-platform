#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# MITIGATE AI - Runtime Private API systemd deployment installer
# - Requires root privileges
# - Does not overwrite existing /etc/mitigate-ai/runtime.env without explicit flag
# - Optionally enables and/or starts the service when requested by flags

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="/srv/mitigate/mitigate-ai-platform"
VENV_PY="/srv/mitigate/mitigate-ai-platform/agent/.venv/bin/python"
UNIT_SRC="${SCRIPT_DIR}/mitigate-ai-runtime.service"
ENV_EXAMPLE_SRC="${SCRIPT_DIR}/mitigate-ai-runtime.env.example"
HEALTHCHECK_SRC="${SCRIPT_DIR}/healthcheck.sh"

UNIT_DEST="/etc/systemd/system/mitigate-ai-runtime.service"
ENV_DIR="/etc/mitigate-ai"
ENV_EXAMPLE_DEST="${ENV_DIR}/runtime.env.example"
ENV_DEST="${ENV_DIR}/runtime.env"
LOG_DIR="/var/log/mitigate-ai"

ENABLE_FLAG=0
START_FLAG=0
OVERWRITE_ENV_FLAG=0

usage() {
  cat <<EOF
Usage: sudo $(basename "$0") [OPTIONS]

Options:
  --enable           Enable the mitigate-ai-runtime service (does not start unless --start is also supplied)
  --start            Start the mitigate-ai-runtime service after installation
  --overwrite-env    Overwrite existing /etc/mitigate-ai/runtime.env with the example (DANGEROUS)
  -h, --help         Show this help message

Behavior:
  - Installs systemd unit to ${UNIT_DEST}
  - Installs example env to ${ENV_EXAMPLE_DEST}
  - Installs real env to ${ENV_DEST} only if it does not already exist, unless --overwrite-env is provided
  - Creates ${ENV_DIR} (root:root, 0755) and ${LOG_DIR} (ubuntu:ubuntu, 0750) if absent
  - Runs 'systemctl daemon-reload'
  - Optionally enables/starts the service when flags are supplied
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable)
      ENABLE_FLAG=1
      shift
      ;;
    --start)
      START_FLAG=1
      shift
      ;;
    --overwrite-env)
      OVERWRITE_ENV_FLAG=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

# Require root privileges
if [[ ${EUID} -ne 0 ]]; then
  echo "This installer must be run as root." >&2
  exit 3
fi

# Validate expected repository and virtual environment paths
if [[ ! -d "${REPO_ROOT}" ]]; then
  echo "Repository root not found: ${REPO_ROOT}" >&2
  exit 4
fi
if [[ ! -x "${VENV_PY}" ]]; then
  echo "Python interpreter not found or not executable: ${VENV_PY}" >&2
  exit 5
fi

# Validate generated deployment files exist in-repo
if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "Missing unit file: ${UNIT_SRC}" >&2
  exit 6
fi
if [[ ! -f "${ENV_EXAMPLE_SRC}" ]]; then
  echo "Missing environment example: ${ENV_EXAMPLE_SRC}" >&2
  exit 7
fi
if [[ ! -f "${HEALTHCHECK_SRC}" ]]; then
  echo "Missing healthcheck script: ${HEALTHCHECK_SRC}" >&2
  exit 8
fi

# Create required directories safely
install -d -m 0755 -o root -g root "${ENV_DIR}"
install -d -m 0750 -o ubuntu -g ubuntu "${LOG_DIR}"

# Install systemd unit
install -m 0644 -o root -g root "${UNIT_SRC}" "${UNIT_DEST}"

# Install example environment (non-secret)
install -m 0644 -o root -g root "${ENV_EXAMPLE_SRC}" "${ENV_EXAMPLE_DEST}"

# Real environment file installation logic
# Compatibility contract requires a literal path check:
if [[ -f /etc/mitigate-ai/runtime.env ]]; then
  if [[ ${OVERWRITE_ENV_FLAG} -eq 1 ]]; then
    install -m 0600 -o root -g root "${ENV_EXAMPLE_SRC}" "${ENV_DEST}"
    echo "Overwrote existing ${ENV_DEST} with example (operator requested). EDIT THIS FILE BEFORE STARTING THE SERVICE."
  else
    echo "Preserving existing ${ENV_DEST}. No changes made."
  fi
else
  install -m 0600 -o root -g root "${ENV_EXAMPLE_SRC}" "${ENV_DEST}"
  echo "Installed example environment to ${ENV_DEST}. Replace placeholders and keep permissions at 0600."
fi

# Reload systemd units
systemctl daemon-reload

# Optionally enable and/or start
if [[ ${ENABLE_FLAG} -eq 1 ]]; then
  systemctl enable mitigate-ai-runtime
fi
if [[ ${START_FLAG} -eq 1 ]]; then
  systemctl start mitigate-ai-runtime
fi

echo "Installation complete. Review and edit ${ENV_DEST} to provide real runtime settings and tokens (do not print secrets)."
exit 0
