#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# MITIGATE AI - Runtime Private API systemd deployment uninstaller
# - Requires root privileges
# - Stops/disables the service when present
# - Removes only files installed by this deployment package
# - Preserves /etc/mitigate-ai/runtime.env by default; use --purge-env to remove

UNIT_PATH="/etc/systemd/system/mitigate-ai-runtime.service"
ENV_DIR="/etc/mitigate-ai"
ENV_EXAMPLE_PATH="${ENV_DIR}/runtime.env.example"
ENV_REAL_PATH="${ENV_DIR}/runtime.env"

PURGE_ENV=0

usage() {
  cat <<EOF
Usage: sudo $(basename "$0") [--purge-env]

Options:
  --purge-env    Also remove /etc/mitigate-ai/runtime.env (DESTRUCTIVE)
  -h, --help     Show this help message

Behavior:
  - Stops and disables 'mitigate-ai-runtime' if present
  - Removes ${UNIT_PATH} and ${ENV_EXAMPLE_PATH}
  - Preserves ${ENV_REAL_PATH} unless --purge-env is provided
  - Reloads systemd units
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-env)
      PURGE_ENV=1
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
  echo "This uninstaller must be run as root." >&2
  exit 3
fi

# Stop/disable service if it exists
if systemctl list-unit-files | grep -q '^mitigate-ai-runtime.service'; then
  systemctl stop mitigate-ai-runtime || true
  systemctl disable mitigate-ai-runtime || true
fi

# Remove installed files (preserving real env by default)
if [[ -f "${UNIT_PATH}" ]]; then
  rm -f "${UNIT_PATH}"
fi
if [[ -f "${ENV_EXAMPLE_PATH}" ]]; then
  rm -f "${ENV_EXAMPLE_PATH}"
fi

if [[ ${PURGE_ENV} -eq 1 ]]; then
  if [[ -f "${ENV_REAL_PATH}" ]]; then
    rm -f "${ENV_REAL_PATH}"
    echo "Removed ${ENV_REAL_PATH} (operator requested destructive purge)."
  fi
else
  echo "Preserved ${ENV_REAL_PATH}. Use --purge-env to remove."
fi

# Reload systemd units
systemctl daemon-reload

echo "Uninstallation complete."
exit 0
