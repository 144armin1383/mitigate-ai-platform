#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve the physical directory of this script and the repository root
# irrespective of the caller's current working directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

# The variables SCRIPT_DIR and REPO_ROOT are intended to be used by subsequent
# bootstrap steps for deterministic repository-relative path resolution.
# Additional bootstrap logic remains unchanged and should reference REPO_ROOT
# when constructing paths.
