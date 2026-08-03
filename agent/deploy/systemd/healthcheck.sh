#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# MITIGATE AI - Runtime Private API Health Check Script
# - Liveness: GET http://127.0.0.1:<PORT>/health/live (no auth)
# - Readiness: GET http://127.0.0.1:<PORT>/health/ready (Bearer auth)
# - Uses bounded connection and total timeouts
# - Never prints tokens

MODE="live"  # live | ready
PORT="${MITIGATE_AI_PORT:-8765}"
CONNECT_TIMEOUT=2
MAX_TIME=5

usage() {
  cat <<EOF
Usage: $(basename "$0") [--ready]

Checks:
  --ready     Use readiness check (requires token). Otherwise liveness is checked.

Environment:
  MITIGATE_AI_PORT            Port to connect to (default: 8765)
  MITIGATE_AI_AUTH_TOKEN_ENV  Name of the environment variable containing the token (default: MITIGATE_AI_API_TOKEN)
  MITIGATE_AI_API_TOKEN       Token value when MITIGATE_AI_AUTH_TOKEN_ENV is not set

Exit codes:
  0 - success (HTTP 200)
  1 - failure (non-200 or error)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ready)
      MODE="ready"
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

BASE_URL="http://127.0.0.1:${PORT}"
PATH_LIVE="/health/live"
PATH_READY="/health/ready"

if [[ "${MODE}" == "live" ]]; then
  CODE=$(curl --silent --show-error --output /dev/null \
    --connect-timeout "${CONNECT_TIMEOUT}" --max-time "${MAX_TIME}" \
    --write-out "%{http_code}" \
    "${BASE_URL}${PATH_LIVE}" || true)
  if [[ "${CODE}" == "200" ]]; then
    exit 0
  else
    echo "Liveness check failed with HTTP ${CODE:-none}" >&2
    exit 1
  fi
else
  TOKEN_ENV_NAME="${MITIGATE_AI_AUTH_TOKEN_ENV:-MITIGATE_AI_API_TOKEN}"
  # Indirect expansion to read token value without printing it
  TOKEN_VALUE="${!TOKEN_ENV_NAME-}"
  if [[ -z "${TOKEN_VALUE}" ]]; then
    echo "Readiness check requires a token in \"${TOKEN_ENV_NAME}\"." >&2
    exit 1
  fi
  CODE=$(curl --silent --show-error --output /dev/null \
    --connect-timeout "${CONNECT_TIMEOUT}" --max-time "${MAX_TIME}" \
    --write-out "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN_VALUE}" \
    "${BASE_URL}${PATH_READY}" || true)
  if [[ "${CODE}" == "200" ]]; then
    exit 0
  else
    echo "Readiness check failed with HTTP ${CODE:-none}" >&2
    exit 1
  fi
fi
