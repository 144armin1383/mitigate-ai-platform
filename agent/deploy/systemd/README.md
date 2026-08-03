MITIGATE AI Runtime Private API — systemd Deployment

Overview
- This package installs the Runtime Private API as a hardened, persistent systemd service on Ubuntu 24.04 LTS.
- It does not automatically enable or start the service unless flags are provided to the installer.
- The service runs as user ubuntu, group ubuntu, and reads configuration from /etc/mitigate-ai/runtime.env.
- Default binding is localhost-only (127.0.0.1:8765). Use a reverse proxy (e.g., Nginx) to expose externally.

Prerequisites
- Ubuntu 24.04 LTS with systemd.
- Repository checked out at /srv/mitigate/mitigate-ai-platform.
- Python virtual environment present at /srv/mitigate/mitigate-ai-platform/agent/.venv.
- Operator has root privileges for installation/uninstallation steps.
- Do not commit secrets; store runtime.env outside Git in /etc/mitigate-ai.

Generated Files
- agent/deploy/systemd/mitigate-ai-runtime.service (systemd unit file)
- agent/deploy/systemd/mitigate-ai-runtime.env.example (example environment file; placeholders only)
- agent/deploy/systemd/install.sh (installer; root-required; no automatic enable/start unless requested)
- agent/deploy/systemd/uninstall.sh (uninstaller; preserves runtime.env by default)
- agent/deploy/systemd/healthcheck.sh (localhost-only liveness/readiness checks)

Secure Environment File
- Real file path: /etc/mitigate-ai/runtime.env
- Ownership/permissions: root:root, mode 0600
- Populate using the example: agent/deploy/systemd/mitigate-ai-runtime.env.example
- Replace all placeholders. Never commit this file to Git.
- Variables supported:
  - MITIGATE_AI_HOST
  - MITIGATE_AI_PORT
  - MITIGATE_AI_DATA_ROOT
  - MITIGATE_AI_REPOSITORY_ROOT
  - MITIGATE_AI_DEFAULT_PROJECT_ID
  - MITIGATE_AI_ENVIRONMENT_NAME
  - MITIGATE_AI_AUTH_TOKEN_ENV
  - MITIGATE_AI_API_TOKEN (secret placeholder only; never commit a real token)

Token Generation Guidance
- Obtain or generate a Runtime Private API token using your organization's secure workflow.
- Set MITIGATE_AI_AUTH_TOKEN_ENV to the name of the environment variable containing that token (commonly MITIGATE_AI_API_TOKEN).
- Place the token value in MITIGATE_AI_API_TOKEN within /etc/mitigate-ai/runtime.env.
- Keep /etc/mitigate-ai/runtime.env permissions at 0600 and owned by root.

Installation
1) Copy the example environment file:
   sudo install -d -m 0755 -o root -g root /etc/mitigate-ai
   sudo cp agent/deploy/systemd/mitigate-ai-runtime.env.example /etc/mitigate-ai/runtime.env.example
   sudo cp /etc/mitigate-ai/runtime.env.example /etc/mitigate-ai/runtime.env
   sudo chown root:root /etc/mitigate-ai/runtime.env
   sudo chmod 0600 /etc/mitigate-ai/runtime.env

2) Edit /etc/mitigate-ai/runtime.env and replace all placeholders. Do not print or log tokens.

3) Install the systemd unit and healthcheck script using the provided installer (root required):
   sudo agent/deploy/systemd/install.sh
   - The installer does not enable or start the service unless flags are supplied.

Enable/Start
- To enable the service at boot:
  sudo agent/deploy/systemd/install.sh --enable
- To start immediately after install:
  sudo agent/deploy/systemd/install.sh --start
- To enable and start:
  sudo agent/deploy/systemd/install.sh --enable --start

Validation
- Check unit is installed:
  ls -l /etc/systemd/system/mitigate-ai-runtime.service
- Validate environment and permissions:
  ls -l /etc/mitigate-ai/runtime.env  # Should be -rw------- root root

Service Status
- View status:
  systemctl status mitigate-ai-runtime
- Inspect recent logs via journal:
  journalctl -u mitigate-ai-runtime -e -S -1h

Liveness and Readiness Checks
- Liveness (no auth):
  agent/deploy/systemd/healthcheck.sh
- Readiness (Bearer auth):
  export MITIGATE_AI_API_TOKEN="<redacted>"
  export MITIGATE_AI_AUTH_TOKEN_ENV=MITIGATE_AI_API_TOKEN
  agent/deploy/systemd/healthcheck.sh --ready

Restart
- Restart the service after updating configuration or code:
  sudo systemctl restart mitigate-ai-runtime

Stop
- Stop the service:
  sudo systemctl stop mitigate-ai-runtime

Disable
- Prevent start at boot:
  sudo systemctl disable mitigate-ai-runtime

Uninstall
- Preserve environment file (default):
  sudo agent/deploy/systemd/uninstall.sh
- Destructive purge of environment file as well (explicitly requested):
  sudo agent/deploy/systemd/uninstall.sh --purge-env

Rollback
- If a new unit fails, restore the previously working environment file and re-run install.sh, or reinstall the previously known-good Git revision and run:
  sudo systemctl daemon-reload
  sudo systemctl restart mitigate-ai-runtime

Updating After Git Deployment
- After deploying updated code into /srv/mitigate/mitigate-ai-platform:
  - Review changes to the systemd unit if necessary.
  - Re-run the installer to ensure the unit is current:
    sudo agent/deploy/systemd/install.sh
  - Reload and restart:
    sudo systemctl daemon-reload
    sudo systemctl restart mitigate-ai-runtime

Security Model
- The service runs as ubuntu:ubuntu with WorkingDirectory=/srv/mitigate/mitigate-ai-platform.
- EnvironmentFile=/etc/mitigate-ai/runtime.env is root-owned (0600) and is not committed to Git.
- The systemd unit applies strong hardening:
  - NoNewPrivileges=true, PrivateTmp=true, ProtectSystem=strict, ProtectHome=true
  - ProtectKernel* and ProtectControlGroups=true
  - RestrictSUIDSGID=true, LockPersonality=true, MemoryDenyWriteExecute=true
  - RestrictRealtime=true, RestrictNamespaces=true, SystemCallArchitectures=native
  - UMask=0077
- Write access limited via ReadWritePaths to runtime data and log directories only.
- Secrets are never embedded in the unit file or echoed by scripts.

Localhost-only Binding
- The service is intended to bind to 127.0.0.1:8765.
- Expose externally only through a reverse proxy (e.g., Nginx) that handles TLS termination.

Future Nginx Reverse Proxy Placement
- Recommended to place Nginx in front for public access:
  - Nginx listens on 443 with TLS and proxies to http://127.0.0.1:8765.
  - Apply rate-limiting, access logs, WAF, and header sanitation at the proxy layer.

Troubleshooting
- Unit fails to start:
  - Check journal: journalctl -u mitigate-ai-runtime -e
  - Verify /etc/mitigate-ai/runtime.env exists and permissions are 0600.
  - Confirm Python interpreter path: /srv/mitigate/mitigate-ai-platform/agent/.venv/bin/python
  - Confirm module is importable: agent.api.runtime_private_api
- Permission issues writing data/logs:
  - Ensure runtime writes only to allowed paths (e.g., /srv/mitigate/data, /var/log/mitigate-ai)
  - Adjust ownership and permissions accordingly.
- Health checks failing:
  - Validate host binds to 127.0.0.1 and port matches MITIGATE_AI_PORT.
  - For readiness, ensure a valid token is set and not expired.
