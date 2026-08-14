#!/usr/bin/env bash
set -Eeuo pipefail

REAL_BINARY="${MITIGATE_OPENCLAW_REAL_BINARY:-/srv/mitigate/external-runtimes/npm/node_modules/.bin/openclaw}"
WORKSPACE_ROOT="${MITIGATE_WORKSPACE_ROOT:-/srv/mitigate/data/runtime/workspaces}"

[[ -x "$REAL_BINARY" ]] || {
  echo "openclaw real binary unavailable" >&2
  exit 127
}

args=("$@")
filtered=()
cwd=""

for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[$i]}" == "--cwd" ]]; then
    ((i+1 < ${#args[@]})) || {
      echo "--cwd requires a value" >&2
      exit 2
    }
    cwd="${args[$((i+1))]}"
    ((i++))
    continue
  fi
  filtered+=("${args[$i]}")
done

if [[ -n "$cwd" ]]; then
  resolved="$(realpath -e "$cwd")"
  root="$(realpath -e "$WORKSPACE_ROOT")"
  case "$resolved/" in
    "$root"/*) ;;
    *)
      echo "refusing cwd outside MITIGATE disposable workspace root" >&2
      exit 2
      ;;
  esac
  cd "$resolved"
fi

unset NODE_OPTIONS
exec "$REAL_BINARY" "${filtered[@]}"
