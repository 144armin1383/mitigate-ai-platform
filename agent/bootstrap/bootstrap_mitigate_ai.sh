#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# MITIGATE AI full-stack operational bootstrap.
# Intended usage on Ubuntu 24.04 after cloning this repository to:
#   /srv/mitigate/mitigate-ai-platform
#
# Installs/configures, idempotently where practical:
# - host prerequisites, Node 22+, Docker Engine + Compose
# - MITIGATE Python runtime venv and runtime data directories
# - isolated OpenHands/OpenClaw/Ruflo execution runtimes
# - MITIGATE Worker + Runtime API systemd services
# - runtime-consolidation worker activation
# - OpenHands Agent Canvas (localhost only)
# - MITIGATE Web Panel (localhost only)
# - protected runtime/canvas secrets and health verification
#
# No real secret is stored in Git. Existing /etc/mitigate-ai secrets are preserved.

ROOT="${MITIGATE_ROOT:-/srv/mitigate/mitigate-ai-platform}"
SERVICE_USER="${MITIGATE_SERVICE_USER:-ubuntu}"
ENV_DIR="/etc/mitigate-ai"
RUNTIME_ENV="$ENV_DIR/runtime.env"
CANVAS_ENV="$ENV_DIR/agent-canvas.env"
DATA_ROOT="${MITIGATE_DATA_ROOT:-/srv/mitigate/data}"
EXTERNAL_ROOT="${MITIGATE_EXTERNAL_RUNTIME_ROOT:-/srv/mitigate/external-runtimes}"
CANVAS_VERSION="${MITIGATE_AGENT_CANVAS_VERSION:-1.12.0}"
CANVAS_PORT="${MITIGATE_AGENT_CANVAS_PORT:-8000}"
PANEL_PORT="${MITIGATE_AI_PANEL_PORT:-8766}"
PROJECT_ID="${MITIGATE_AI_DEFAULT_PROJECT_ID:-mitigate-ai-platform}"

log() { printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "Run with sudo/root: sudo ./agent/bootstrap/bootstrap_mitigate_ai.sh"
[[ -d "$ROOT/.git" ]] || die "Repository must be cloned to $ROOT"
id "$SERVICE_USER" >/dev/null 2>&1 || die "Service user not found: $SERVICE_USER"

cd "$ROOT"

install_base_packages() {
  log "Installing base host packages"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl git openssl sudo python3 python3-venv python3-pip
}

install_node22() {
  local major="0"
  if command -v node >/dev/null 2>&1; then
    major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  fi
  if [[ "$major" -ge 22 ]]; then
    log "Node.js $(node --version) already satisfies Node 22+"
    return
  fi
  log "Installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
  [[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ]] || die "Node 22+ installation failed"
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker and Compose already installed"
    systemctl enable --now docker
    return
  fi

  log "Installing Docker Engine and Compose from Docker's Ubuntu repository"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  docker version >/dev/null
  docker compose version >/dev/null
}

ensure_core_paths() {
  log "Preparing MITIGATE directories and Python environment"
  install -d -m 0755 -o root -g root "$ENV_DIR"
  install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" \
    "$DATA_ROOT" "$DATA_ROOT/runtime" "$DATA_ROOT/runtime/checkpoints" \
    "$DATA_ROOT/runtime/execution-reports" "$DATA_ROOT/runtime/technology" \
    "$DATA_ROOT/openhands" /srv/mitigate/ai-logs /var/log/mitigate-ai "$EXTERNAL_ROOT"

  if [[ ! -x "$ROOT/agent/.venv/bin/python" ]]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$ROOT/agent/.venv"
  fi
}

get_env_value() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  awk -F= -v key="$key" '$1==key {sub(/^[^=]*=/, ""); gsub(/^["'\'' ]+|["'\'' ]+$/, ""); print; exit}' "$file"
}

set_env_value() {
  local file="$1" key="$2" value="$3"
  touch "$file"
  chmod 600 "$file"
  if grep -q "^${key}=" "$file"; then
    local escaped
    escaped="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

configure_runtime_secrets() {
  log "Configuring protected runtime environment"
  touch "$RUNTIME_ENV"
  chmod 600 "$RUNTIME_ENV"
  chown root:root "$RUNTIME_ENV"

  local runtime_token openai_key panel_password
  runtime_token="$(get_env_value "$RUNTIME_ENV" MITIGATE_AI_API_TOKEN)"
  [[ -n "$runtime_token" ]] || runtime_token="$(openssl rand -hex 32)"

  openai_key="$(get_env_value "$RUNTIME_ENV" OPENAI_API_KEY)"
  if [[ -z "$openai_key" && -n "${OPENAI_API_KEY:-}" ]]; then
    openai_key="$OPENAI_API_KEY"
  fi
  if [[ -z "$openai_key" ]]; then
    printf 'Enter OpenAI API key (input hidden; never committed): ' >/dev/tty
    IFS= read -r -s openai_key </dev/tty
    printf '\n' >/dev/tty
  fi
  [[ -n "$openai_key" ]] || die "OPENAI_API_KEY is required"

  panel_password="$(get_env_value "$RUNTIME_ENV" MITIGATE_AI_PANEL_PASSWORD)"
  [[ -n "$panel_password" ]] || panel_password="$(openssl rand -hex 18)"

  set_env_value "$RUNTIME_ENV" MITIGATE_AI_HOST 127.0.0.1
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_PORT 8765
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_DATA_ROOT "$DATA_ROOT"
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_REPOSITORY_ROOT "$ROOT"
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_DEFAULT_PROJECT_ID "$PROJECT_ID"
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_ENVIRONMENT_NAME production
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_AUTH_TOKEN_ENV MITIGATE_AI_API_TOKEN
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_API_TOKEN "$runtime_token"
  set_env_value "$RUNTIME_ENV" OPENAI_API_KEY "$openai_key"
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_PANEL_HOST 127.0.0.1
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_PANEL_PORT "$PANEL_PORT"
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_PANEL_USERNAME admin
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_PANEL_PASSWORD "$panel_password"
  set_env_value "$RUNTIME_ENV" MITIGATE_AI_RUNTIME_BASE_URL http://127.0.0.1:8765

  chmod 600 "$RUNTIME_ENV"
  chown root:root "$RUNTIME_ENV"
}

install_external_runtimes() {
  log "Installing isolated execution runtimes"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$EXTERNAL_ROOT"
  sudo -u "$SERVICE_USER" -H env \
    MITIGATE_ROOT="$ROOT" \
    MITIGATE_EXTERNAL_RUNTIME_ROOT="$EXTERNAL_ROOT" \
    MITIGATE_INSTALL_RUFLO=1 \
    "$ROOT/agent/bootstrap/install_external_runtimes.sh"
}

install_runtime_services() {
  log "Installing MITIGATE Worker and Runtime API services"
  install -m 0644 "$ROOT/agent/deploy/systemd/mitigate-ai-worker.service" \
    /etc/systemd/system/mitigate-ai-worker.service
  install -m 0644 "$ROOT/agent/deploy/systemd/mitigate-ai-runtime-api.service" \
    /etc/systemd/system/mitigate-ai-runtime-api.service
  systemctl daemon-reload
  systemctl enable mitigate-ai-worker.service mitigate-ai-runtime-api.service
  systemctl restart mitigate-ai-worker.service
  systemctl restart mitigate-ai-runtime-api.service
  sleep 3
  [[ "$(systemctl is-active mitigate-ai-worker.service)" == active ]] || die "Worker failed to start"
  [[ "$(systemctl is-active mitigate-ai-runtime-api.service)" == active ]] || die "Runtime API failed to start"
}

enable_consolidated_worker() {
  log "Enabling consolidated OpenHands-capable worker"
  # Existing activation script validates clean main, external runtimes, tests, and rollback.
  sudo -u "$SERVICE_USER" -H env \
    MITIGATE_ROOT="$ROOT" \
    MITIGATE_EXTERNAL_RUNTIME_ROOT="$EXTERNAL_ROOT" \
    "$ROOT/agent/bootstrap/enable_runtime_consolidation.sh"
}

configure_canvas() {
  log "Configuring OpenHands Agent Canvas"
  local openai_key canvas_key canvas_uid canvas_gid
  openai_key="$(get_env_value "$RUNTIME_ENV" OPENAI_API_KEY)"
  canvas_key="$(get_env_value "$CANVAS_ENV" LOCAL_BACKEND_API_KEY)"
  [[ -n "$canvas_key" ]] || canvas_key="$(openssl rand -hex 32)"

  cat >"$CANVAS_ENV" <<EOF
MITIGATE_AGENT_CANVAS_VERSION=$CANVAS_VERSION
MITIGATE_AGENT_CANVAS_PORT=$CANVAS_PORT
MITIGATE_OPENHANDS_STATE_PATH=$DATA_ROOT/openhands
MITIGATE_PROJECTS_PATH=/srv/mitigate
LOCAL_BACKEND_API_KEY=$canvas_key
OPENAI_API_KEY=$openai_key
EOF
  chmod 600 "$CANVAS_ENV"
  chown root:root "$CANVAS_ENV"

  docker pull "ghcr.io/openhands/agent-canvas:$CANVAS_VERSION"
  canvas_uid="$(docker run --rm --entrypoint sh "ghcr.io/openhands/agent-canvas:$CANVAS_VERSION" -c 'id -u')"
  canvas_gid="$(docker run --rm --entrypoint sh "ghcr.io/openhands/agent-canvas:$CANVAS_VERSION" -c 'id -g')"
  chown -R "$canvas_uid:$canvas_gid" "$DATA_ROOT/openhands"
  chmod -R u+rwX "$DATA_ROOT/openhands"

  cd "$ROOT/agent/deploy/agent-canvas"
  docker compose --env-file "$CANVAS_ENV" pull
  docker compose --env-file "$CANVAS_ENV" up -d --force-recreate
}

install_panel_service() {
  [[ -f "$ROOT/agent/web/panel_server.py" ]] || { log "MITIGATE Panel code not present; skipping panel service"; return; }
  log "Installing MITIGATE web panel service"
  cat >/etc/systemd/system/mitigate-ai-panel.service <<EOF
[Unit]
Description=MITIGATE AI Web Control Panel
After=network-online.target mitigate-ai-runtime-api.service
Wants=network-online.target
Requires=mitigate-ai-runtime-api.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$ROOT
EnvironmentFile=$RUNTIME_ENV
ExecStart=$ROOT/agent/.venv/bin/python -m agent.web.panel_server
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=$ROOT
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now mitigate-ai-panel.service
}

wait_http() {
  local url="$1" attempts="${2:-30}"
  local i
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

verify_stack() {
  log "Verifying full MITIGATE AI stack"
  [[ "$(systemctl is-active mitigate-ai-worker.service)" == active ]] || die "Worker inactive"
  [[ "$(systemctl is-active mitigate-ai-runtime-api.service)" == active ]] || die "Runtime API inactive"
  wait_http http://127.0.0.1:8765/health/live 20 || die "Runtime API health failed"
  wait_http "http://127.0.0.1:$CANVAS_PORT/ready" 45 || die "Agent Canvas readiness failed"
  wait_http "http://127.0.0.1:$CANVAS_PORT/canvas" 10 || die "Agent Canvas frontend failed"

  if systemctl list-unit-files mitigate-ai-panel.service >/dev/null 2>&1; then
    [[ "$(systemctl is-active mitigate-ai-panel.service)" == active ]] || die "MITIGATE Panel inactive"
    wait_http "http://127.0.0.1:$PANEL_PORT/healthz" 20 || die "MITIGATE Panel health failed"
  fi

  local inside_key
  inside_key="$(cd "$ROOT/agent/deploy/agent-canvas" && docker compose --env-file "$CANVAS_ENV" exec -T agent-canvas sh -c 'if [ -n "${OPENAI_API_KEY:-}" ]; then echo configured; else echo missing; fi')"
  [[ "$inside_key" == configured ]] || die "OPENAI_API_KEY not available inside Agent Canvas"

  printf '\n==================================================\n'
  printf 'MITIGATE AI FULL STACK READY\n'
  printf '==================================================\n'
  printf 'Worker: active\nRuntime API: http://127.0.0.1:8765\n'
  printf 'Agent Canvas: http://127.0.0.1:%s/canvas\n' "$CANVAS_PORT"
  if systemctl is-active --quiet mitigate-ai-panel.service 2>/dev/null; then
    printf 'MITIGATE Panel: http://127.0.0.1:%s/\n' "$PANEL_PORT"
  fi
  printf 'Secrets: %s and %s (root-only, never commit)\n' "$RUNTIME_ENV" "$CANVAS_ENV"
  printf 'For remote browser access use SSH local port forwarding; do not expose these ports directly.\n'
}


install_auto_update_management() {
  log "Configuring host resources and automatic component updates"

  "$ROOT/agent/maintenance/ensure_host_resources.sh"

  install -m 0644 \
    "$ROOT/agent/deploy/systemd/mitigate-ai-auto-update.service" \
    /etc/systemd/system/mitigate-ai-auto-update.service

  install -m 0644 \
    "$ROOT/agent/deploy/systemd/mitigate-ai-auto-update.timer" \
    /etc/systemd/system/mitigate-ai-auto-update.timer

  systemctl daemon-reload
  systemctl enable --now mitigate-ai-auto-update.timer
}

install_base_packages
install_node22
install_docker
ensure_core_paths
configure_runtime_secrets
install_external_runtimes
install_runtime_services
enable_consolidated_worker
configure_canvas
install_panel_service
install_auto_update_management
verify_stack
