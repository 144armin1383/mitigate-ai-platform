#!/usr/bin/env bash
set -Eeuo pipefail

REAL_BINARY="${MITIGATE_OPENCLAW_REAL_BINARY:-/srv/mitigate/external-runtimes/npm/node_modules/.bin/openclaw}"
WORKSPACE_ROOT="${MITIGATE_WORKSPACE_ROOT:-/srv/mitigate/data/runtime/workspaces}"

if [[ "${MITIGATE_OPENCLAW_CODING_DISABLED:-0}" == "1" ]]; then
  echo "MITIGATE_OPENCLAW_CODING_DISABLED" >&2
  exit 64
fi

[[ -x "$REAL_BINARY" ]] || {
  echo "openclaw real binary unavailable" >&2
  exit 127
}

supports_agent_exec() {
  local help
  help="$($REAL_BINARY agent exec --help 2>&1 || true)"
  [[ "$help" == *"--message-file"* && "$help" == *"--cwd"* && "$help" == *"--json"* ]]
}

supports_agent_local() {
  local help
  help="$($REAL_BINARY agent --help 2>&1 || true)"
  [[ "$help" == *"--message-file"* && "$help" == *"--local"* && "$help" == *"--session-key"* && "$help" == *"--json"* ]]
}

execution_mode() {
  if supports_agent_exec; then
    printf '%s\n' "agent-exec"
    return 0
  fi
  if supports_agent_local; then
    printf '%s\n' "agent-local-compat"
    return 0
  fi
  return 1
}

if [[ $# -eq 1 && "$1" == "--version" ]]; then
  if ! execution_mode >/dev/null; then
    echo "MITIGATE_OPENCLAW_CODING_CLI_UNSUPPORTED" >&2
    exit 64
  fi
  exec "$REAL_BINARY" --version
fi

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

if [[ ${1:-} == "agent" && ${2:-} == "exec" ]]; then
  [[ -n "$cwd" ]] || {
    echo "MITIGATE OpenClaw coding requires an explicit disposable --cwd" >&2
    exit 2
  }

  if supports_agent_exec; then
    exec "$REAL_BINARY" "${filtered[@]}"
  fi

  if ! supports_agent_local; then
    echo "MITIGATE_OPENCLAW_CODING_CLI_UNSUPPORTED" >&2
    exit 64
  fi

  # OpenClaw v2026.7.1-2 does not yet expose `agent exec`, but its documented
  # embedded `agent --local` path supports message-file input and a workspace
  # override through OPENCLAW_WORKSPACE_DIR. Translate only the narrow command
  # shape emitted by MITIGATE; reject unknown arguments instead of silently
  # weakening the execution boundary.
  local_args=()
  for ((i=2; i<${#filtered[@]}; i++)); do
    case "${filtered[$i]}" in
      --message-file)
        ((i+1 < ${#filtered[@]})) || {
          echo "--message-file requires a value" >&2
          exit 2
        }
        local_args+=("--message-file" "${filtered[$((i+1))]}")
        ((i++))
        ;;
      --json)
        local_args+=("--json")
        ;;
      --timeout)
        ((i+1 < ${#filtered[@]})) || {
          echo "--timeout requires a value" >&2
          exit 2
        }
        local_args+=("--timeout" "${filtered[$((i+1))]}")
        ((i++))
        ;;
      *)
        echo "unsupported MITIGATE OpenClaw compatibility argument: ${filtered[$i]}" >&2
        exit 2
        ;;
    esac
  done

  session="mitigate-$(basename "$resolved" | tr -c 'A-Za-z0-9_-' '-')"
  session="${session:0:120}"
  export OPENCLAW_WORKSPACE_DIR="$resolved"
  export MITIGATE_OPENCLAW_EXEC_MODE="agent-local-compat"
  exec "$REAL_BINARY" agent \
    --session-key "$session" \
    --local \
    "${local_args[@]}"
fi

exec "$REAL_BINARY" "${filtered[@]}"
