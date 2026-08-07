#!/usr/bin/env bash
# MITIGATE AI - Portable Bootstrap Script
# This script prepares a clean, provider-neutral runtime environment from a
# fresh Git checkout using external configuration. It does not perform any
# production deployment, system activation, or remote downloads.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd -P)"
ENV_FILE="${REPO_ROOT}/agent/bootstrap/env.example"

printf "[mitigate-ai] portable bootstrap start\n"

if [[ ! -f "${ENV_FILE}" ]]; then
  printf "[mitigate-ai] missing environment template: %s\n" "${ENV_FILE}" >&2
  exit 1
fi

# Present gentle guidance without exposing values
printf "[mitigate-ai] environment template located. Copy and adjust as needed.\n"
printf "[mitigate-ai] repository root: %s\n" "${REPO_ROOT}"

# Intentionally no eval, no remote downloads, no side effects beyond guidance.
printf "[mitigate-ai] bootstrap complete (no-op template).\n"
