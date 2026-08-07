MITIGATE AI Portable Bootstrap and Recovery Core

Overview
- Mission: Build a provider-neutral, platform-neutral bootstrap and recovery subsystem that allows the complete MITIGATE AI platform to be cloned from GitHub and restored on a clean server without recoding.
- This directory contains only portable, non-secret assets. Real credentials must be configured externally.

Clean Server Prerequisites
- Git client to clone the repository
- Python 3.12+
- Bash (for provided scripts)
- No provider SDKs required for bootstrap

Recovery Workflow (End-to-End)
1) Fresh clone
   - git clone <repo-url>
   - cd mitigate-ai-platform
2) Bootstrap
   - bash agent/bootstrap/bootstrap.sh
   - Creates agent/.venv, local directories under agent/.data, and validates repository layout
3) Configuration
   - Copy agent/bootstrap/env.example to .env if not already auto-copied by bootstrap
   - Update .env with your environment name, project ID, and provider/site adapter identifiers (placeholders only in Git)
4) Provider credential setup
   - Set API keys, tokens, and any secrets via secure environment variables or your secret manager. Do not commit secrets.
5) Project adapter configuration
   - Choose a site adapter (e.g., wordpress, lovable, react, nextjs, static, php, generic_git, custom)
   - Choose a provider adapter (e.g., openai, anthropic, gemini, local, custom). No provider APIs are implemented here; only identifiers are used.
6) Memory restore
   - Prepare a safe restore bundle directory structure on the same server (no network contact required):
     restore_source/
       manifest.json               (optional; schema_version and project_id)
       memory/                     (safe JSON/NDJSON/TXT/MD/YAML only)
       handoff/
       snapshots/
       decisions/
       work/
       issues/
       config/                     (non-secret project config, e.g., project.json)
   - Run:
     agent/.venv/bin/python -m agent.bootstrap.restore_manager \
       --repository-root "$(pwd)" \
       --agent-root "$(pwd)/agent" \
       --data-root "$(pwd)/agent/.data" \
       --runtime-data-root "$(pwd)/agent/.data/runtime" \
       --memory-root "$(pwd)/agent/.data/memory" \
       --config-root "$(pwd)/agent/config" \
       --environment-name "${MITIGATE_AI_ENVIRONMENT_NAME:-dev}" \
       --expected-project-id "${MITIGATE_AI_DEFAULT_PROJECT_ID:-default}" \
       --restore-source "/path/to/restore_source"
7) Validation
   - bash agent/bootstrap/validate_installation.sh
8) Runtime start
   - Use your documented deployment tooling in agent/deploy (e.g., invoking the existing runtime entrypoint). This bootstrap system does not start services automatically.
9) Health check
   - Verify the runtime’s HTTP endpoint (host/port configured via environment) responds as expected.
10) Rollback
   - If issues arise, revert to a previous Git revision and re-run bootstrap and validation. Memory restore is safe and non-destructive by design.

Portable vs External Assets
- Portable (in Git): application code, missions, tests, schemas, sample config, deployment scripts, bootstrap scripts, adapter interfaces, memory schema, handoff format, documentation.
- External-only (NEVER in Git): API keys, passwords, TLS private keys, production database backups, provider credentials, bearer tokens, cookies, refresh tokens, authorization headers, raw provider responses.

Security Model
- No secret persistence in this directory or in the provided Python code.
- No dynamic code execution, no subprocess calls from production Python.
- All paths are validated to reside within the repository root; traversal and null bytes are rejected.
- Restore process scans for secret-like content and refuses to restore any file that appears to contain secrets.

Versioning and Compatibility
- Bootstrap schema version: 1.0
- Memory schema version: 1.0
- Project configuration version: 1.0
- The system reports incompatible schema or project identity mismatches safely and deterministically.
- No destructive migrations are performed automatically.

WordPress Adapter Example (Provider-neutral)
- Set in .env: MITIGATE_AI_SITE_ADAPTER=wordpress
- Configure your WordPress site externally (e.g., database, wp-config.php) — the bootstrap core does not assume WordPress internals.
- Use adapter wiring in your runtime to connect site operations; this bootstrap keeps adapter-specific logic out of core.

Lovable / Generic Git Adapter Example
- Set in .env: MITIGATE_AI_SITE_ADAPTER=lovable (or generic_git)
- Provide a repository URL and branch in your project configuration (see project.example.json). The core remains CMS-agnostic.

Generic Web Project Example
- Set in .env: MITIGATE_AI_SITE_ADAPTER=generic
- Deploy static or custom sites using your preferred tooling; the bootstrap prepares portable directories and validates the codebase only.

Memory Portability
- Safe memory files (JSON/NDJSON/TXT/MD/YAML) remain readable across providers and models.
- The restore manager validates schema version, project identity, path safety, and skips secret-like content.

Systemd Integration Reference (Non-automated)
- Use your existing unit files in repository (if any) under agent/deploy. This bootstrap does not enable or manage services.

Migration Between Servers
- Steps: Fresh clone -> Bootstrap -> Configure .env externally -> Restore memory -> Validate -> Start runtime.
- No source-code rewriting required; adapters and configuration remain provider-neutral.

Migration Between Providers
- Update provider adapter and model identifiers via environment variables (e.g., MITIGATE_AI_PROVIDER, MITIGATE_AI_PROVIDER_MODEL).
- Memory remains portable; no provider-specific code in the bootstrap path.

Backup Strategy
- Periodically export safe memory, handoff bundles, decisions, and non-secret configs into a restore bundle directory (see structure above).
- Never include API keys, tokens, or raw provider responses.

Rollback Strategy
- Revert Git revision and re-run bootstrap and validation.
- Restore from the latest safe bundle if needed.

Scripts
- bootstrap.sh: Creates/validates local directories and venv, copies env.example to .env if missing, runs portable bootstrap in bootstrap mode. Deterministic exit codes; refuses root unless explicitly allowed.
- validate_installation.sh: Verifies repository layout, Python interpreter, virtualenv, importability of critical modules, memory schema readability, and adapter name syntax (from environment). Does not contact external providers.

Portable Bootstrap Python API
- BootstrapConfig, BootstrapResult, BootstrapStatus, PortableBootstrap
- RestoreConfig, RestoreResult, RestoreStatus, RestoreManager
- build_portable_bootstrap, build_restore_manager

Notes
- This subsystem never performs real deployment, Git, DNS, Nginx, or systemd operations.
- Provider credentials and routing are configured externally via environment variables.
