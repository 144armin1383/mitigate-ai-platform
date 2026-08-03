Mission: Build Runtime Systemd Deployment Package

Goal

Create a secure production deployment package for running the existing Runtime Private API as a persistent systemd service on Ubuntu.

Scope

- Generate deployment files and documentation only.
- Do not install or enable the service automatically.
- Do not execute systemctl, sudo, Git, shell commands, Nginx, Certbot, or firewall commands.
- Do not modify production server state.
- Do not add application dependencies.
- Do not modify requirements.txt.
- Keep all generated files inside the repository.
- Use the existing Runtime Private API entrypoint.
- Target Ubuntu 24.04 LTS and systemd.

Existing Runtime Entrypoint

Use:

- Python virtual environment:
  /srv/mitigate/mitigate-ai-platform/agent/.venv

- Repository root:
  /srv/mitigate/mitigate-ai-platform

- Runtime module:
  agent.api.runtime_private_api

- Default private API binding:
  127.0.0.1:8765

Do not create a replacement HTTP server.

Systemd Unit Requirements

The service must:

- Run as user ubuntu.
- Run as group ubuntu.
- Set WorkingDirectory to /srv/mitigate/mitigate-ai-platform.
- Load secrets and runtime configuration from:
  /etc/mitigate-ai/runtime.env
- Execute:
  /srv/mitigate/mitigate-ai-platform/agent/.venv/bin/python
  -m agent.api.runtime_private_api
- Bind only to 127.0.0.1 by default.
- Use port 8765 by default.
- Use the configured repository root.
- Use the configured data root.
- Use the configured default project identifier.
- Use the configured environment name.
- Resolve the API authentication token from an environment-variable reference.
- Enable restart on failure.
- Use a bounded restart delay.
- Stop gracefully with SIGTERM.
- Use a bounded stop timeout.
- Start only after the network target is available.
- Never embed secrets in the unit file.

Systemd Hardening

Apply compatible security settings where appropriate:

- NoNewPrivileges=true
- PrivateTmp=true
- ProtectSystem=strict
- ProtectHome=true
- ProtectKernelTunables=true
- ProtectKernelModules=true
- ProtectKernelLogs=true
- ProtectControlGroups=true
- RestrictSUIDSGID=true
- LockPersonality=true
- MemoryDenyWriteExecute=true
- RestrictRealtime=true
- RestrictNamespaces=true
- SystemCallArchitectures=native
- UMask=0077

Allow write access only to explicitly required runtime data and log directories.

Environment File

The example environment file must contain placeholders only.

Support:

- MITIGATE_AI_HOST
- MITIGATE_AI_PORT
- MITIGATE_AI_DATA_ROOT
- MITIGATE_AI_REPOSITORY_ROOT
- MITIGATE_AI_DEFAULT_PROJECT_ID
- MITIGATE_AI_ENVIRONMENT_NAME
- MITIGATE_AI_AUTH_TOKEN_ENV
- MITIGATE_AI_API_TOKEN

Rules:

- Never include a real token.
- Clearly mark secret values as placeholders.
- The real environment file must be stored outside Git.
- Recommended permissions must be root-owned and mode 0600.
- Do not echo secret values in scripts.

Install Script

The installation script must:

- Use bash strict mode.
- Require root privileges.
- Validate expected repository and virtual-environment paths.
- Validate generated deployment files exist.
- Create required directories safely.
- Install the unit file into /etc/systemd/system.
- Create /etc/mitigate-ai if absent.
- Install the example environment only when the real environment file does not already exist.
- Never overwrite an existing real environment file without explicit operator confirmation.
- Apply secure ownership and permissions.
- Run systemd daemon-reload.
- Optionally enable and start only when explicit flags are supplied.
- Provide deterministic exit codes.
- Avoid exposing secrets.

Uninstall Script

The uninstall script must:

- Use bash strict mode.
- Require root privileges.
- Stop and disable the service when present.
- Remove only files installed by this deployment package.
- Preserve /etc/mitigate-ai/runtime.env by default.
- Remove the real environment file only with an explicit destructive flag.
- Run systemd daemon-reload.
- Provide deterministic exit codes.

Health Check

The health-check script must:

- Use localhost only.
- Call GET /health/live.
- Use bounded connection and total timeouts.
- Validate an HTTP 200 response.
- Avoid printing tokens or Authorization headers.
- Support a readiness mode that calls GET /health/ready with bearer authentication.
- Read the token from the configured environment without printing it.
- Return deterministic exit codes suitable for monitoring.

README

Document:

- prerequisites
- generated files
- secure environment-file creation
- token generation guidance
- installation
- validation
- enable/start commands
- service status
- liveness and readiness checks
- journal inspection
- restart
- stop
- disable
- uninstall
- rollback
- updating after Git deployment
- security model
- localhost-only binding
- future Nginx reverse proxy placement
- troubleshooting

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Do not execute systemctl, sudo, install scripts, uninstall scripts, or network commands in tests.
- Read and validate generated files as text.
- Use TemporaryDirectory where needed.
- Do not modify system files.
- Do not modify sys.path.
- Use repository-root imports.
- Do not use dynamic code execution or dynamic imports.
- Generated tests must not contain the forbidden function-call pattern checked by Mission Runner.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Testing Requirements

Test:

- all deliverables exist
- unit uses the expected Python interpreter
- unit uses the expected module entrypoint
- unit loads /etc/mitigate-ai/runtime.env
- unit runs as ubuntu
- unit restart policy
- unit graceful shutdown settings
- unit hardening directives
- unit does not contain secrets
- environment example contains placeholders only
- environment example contains all required variables
- install script uses strict mode
- install script requires root
- install script preserves existing real environment file
- install script supports explicit enable/start flags
- uninstall script preserves environment file by default
- destructive environment removal requires an explicit flag
- health check uses localhost
- health check uses bounded timeouts
- health check does not print tokens
- README includes required operational procedures
- scripts contain no real credentials
- unrelated files remain unchanged
- all existing and newly generated unittest tests pass

Generated File Safety

- Shell scripts must pass bash syntax validation in their content design.
- Do not use eval.
- Do not use dynamically constructed shell execution.
- Do not download remote scripts.
- Do not use curl piped into shell.
- Do not embed credentials.
- Keep destructive operations explicitly gated.

Deliverables

- agent/deploy/systemd/mitigate-ai-runtime.service
- agent/deploy/systemd/mitigate-ai-runtime.env.example
- agent/deploy/systemd/install.sh
- agent/deploy/systemd/uninstall.sh
- agent/deploy/systemd/healthcheck.sh
- agent/deploy/systemd/README.md
- agent/tests/test_runtime_systemd_deployment.py

Systemd Directive Test Contract

- Tests that validate systemd directives must inspect complete logical lines.
- Do not use a beginning-of-string regular expression such as r"^RestartSec=" against the entire multi-line unit content without multiline mode.
- Acceptable validation methods include:
  - assertIn("RestartSec=5s", service_content)
  - checking service_content.splitlines()
  - a regular expression compiled with re.MULTILINE
- Apply the same rule to Restart, TimeoutStopSec, KillSignal, User, Group, EnvironmentFile, ExecStart, and all other line-oriented systemd directives.
- Do not require RestartSec or another Service directive to appear at the beginning of the entire file.
- Keep all directives inside their valid systemd sections.
- The generated systemd unit must remain syntactically valid.
- All existing and newly generated unittest tests must pass.

Install Script Compatibility Contract

For compatibility with repository tests, the install script must contain a literal file existence check using:

-f /etc/mitigate-ai/runtime.env

Do not hide this path behind a shell variable for that specific existence check.

The script may still define ENV_DEST, but the preservation logic must visibly contain:

if [[ -f /etc/mitigate-ai/runtime.env ]]

or an equivalent literal path check.

Repository compatibility takes precedence over shell abstraction for this single check.

