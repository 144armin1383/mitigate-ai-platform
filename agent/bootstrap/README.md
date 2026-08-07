# Portable Bootstrap and Recovery Guide

This document is the production-grade, operator-ready recovery contract for the MITIGATE AI platform. It enables a strict clean-checkout bootstrap, safe recovery, and validated activation without weakening any security, portability, or secret-handling guarantees.

The GitHub repository is the portable source of truth for all non-secret MITIGATE AI platform assets.


## Prerequisites

Prepare a fresh server with:

- Supported Linux environment: a recent, stable Linux distribution with system packages available for Python 3.12 tooling (Debian/Ubuntu/RHEL/Alma/Rocky are typical). Containers/VMs are acceptable if they provide the below capabilities.
- Python interpreter compatible with Python 3.12 (python3.12 or newer compatible runtime). Ability to create and activate a virtual environment via `python -m venv`.
- Git installed and network access to the repository remote.
- Repository access (deploy key, read-only token, or operator account) configured outside of Git (no secrets committed).
- Ability to create a Python virtual environment and install dependencies user-locally (no root required) or with appropriate privileges if system tools are used.
- External access to required credentials through a secure channel or secret manager. Credentials are injected at runtime via environment or secret manager only (never from Git).
- Sufficient filesystem permissions for the deploying user to:
  - clone the repository
  - create directories for logs and data
  - manage virtual environments in the project workspace
  - optionally install and manage `systemd` units when performing managed service activation
- Project-specific adapter configuration values ready for injection (provider adapter, site adapter, platform parameters). All values must be supplied as environment variables or via an external secret store at deployment time.


## Clean Server Bootstrap

Perform these steps on a clean machine. Use placeholders during validation. Real credentials must be set only through external secret injection.

1. Clone repository
   - `git clone <REPOSITORY_URL> <TARGET_DIR>`
   - `cd <TARGET_DIR>`

2. Run bootstrap
   - Create a virtual environment and install the project:
     - `python3.12 -m venv .venv`
     - `source .venv/bin/activate`
     - `pip install --upgrade pip`
     - `pip install -r requirements.txt`
   - Do not place real secrets in the tree. Keep `agent/bootstrap/env.example` as reference only.

3. Configure external secrets
   - Provision required credentials in your external secret manager or environment injector. Typical secret values include provider API keys, tokens, and any authorization headers.
   - Never write these values into Git or `.env` files in the repository.

4. Configure provider adapter
   - Supply the provider adapter name and any provider-specific endpoints via environment variables. Example placeholders:
     - `MITIGATE_AI_PROVIDER_ADAPTER=<PROVIDER_ADAPTER>`
     - `MITIGATE_AI_PROVIDER_NAME=<PROVIDER_NAME>`
     - `MITIGATE_AI_PROVIDER_API_BASE=<PROVIDER_API_BASE>`
     - `MITIGATE_AI_PROVIDER_API_KEY=<PROVIDER_API_KEY>` (injected securely; not stored in Git)
     - `MITIGATE_AI_MODEL_NAME=<MODEL_NAME>`

5. Configure site adapter
   - Supply the site adapter and site platform via environment variables:
     - `MITIGATE_AI_SITE_ADAPTER=<SITE_ADAPTER>`
     - `MITIGATE_AI_SITE_PLATFORM=<SITE_PLATFORM>`
   - The autonomous core is platform-neutral; all site/platform specifics are expressed via adapters.

6. Restore safe memory/handoff
   - If migrating or restoring, place safe, non-secret project continuity bundles (safe memory, handoff bundles, ADRs) into their expected paths, or point the runtime to them via environment variables (e.g., `MITIGATE_AI_SAFE_MEMORY_PATH`, `MITIGATE_AI_HANDOFF_PATH`, `MITIGATE_AI_ADR_PATH`). Do not place secrets in these bundles.

7. Validate installation
   - From the virtual environment, run the test suite to confirm bootstrap integrity:
     - `pytest -q`
   - Resolve any failures before proceeding.

8. Start runtime
   - Start the runtime via your documented entrypoint (for example, a CLI, API server, or job runner). Use environment injection to supply required credentials.

9. Run health validation
   - Perform Health Validation as documented below before any production activation.


## Restore

Restore only safe, non-secret continuity artifacts. Credentials are never restored from Git.

- Safe project memory: restore the latest compatible safe memory bundle to `MITIGATE_AI_SAFE_MEMORY_PATH`.
- Handoff bundles: restore handoff artifacts to `MITIGATE_AI_HANDOFF_PATH`.
- Architecture decisions (ADRs): restore ADR records to `MITIGATE_AI_ADR_PATH`.
- Work history: restore non-secret logs or structured records to `MITIGATE_AI_WORK_HISTORY_PATH`.
- Known issues: restore issue lists or registries to `MITIGATE_AI_KNOWN_ISSUES_PATH`.
- Non-secret configuration: restore adapter configuration templates and schema files from the repository. Do not copy secrets.

Credentials, API keys, tokens, provider credentials, and any authorization material must be injected via your external secret mechanism at runtime and must not be stored in Git or in versioned files.


## Health Validation

Perform comprehensive Health checks before activating or switching traffic. This includes:

- Runtime liveness validation: confirm the process starts and remains alive, and liveness probes (if any) return success.
- Readiness validation: confirm the runtime can serve its responsibilities (e.g., respond to a readiness endpoint, run a dry-run inference path, or load required adapters and models) without external data mutations.
- Bootstrap validation: confirm the clean checkout, environment injection, and adapter discovery work without missing dependencies.
- Installation validation: confirm unit tests, schema validations, and adapter contracts pass (e.g., `pytest -q`).
- Failure investigation before production activation: if any Health signal fails, stop and investigate. Do not activate services, DNS, or traffic routing until Health is green.

Record the validation outcome in project memory (non-secret) for traceability.


## Systemd Integration

`systemd` deployment assets are repository-managed under:

- `agent/deploy/systemd/`

Guidance:

- Service activation is an explicit operator/deployment action. Portable recovery validation does not automatically enable or start services.
- Review and, if needed, template the unit files with environment placeholders. Never embed secrets in unit files.
- To activate on a compatible host, copy or link unit files to the system unit directory, reload the daemon, and enable/start as appropriate. Perform this only after Health Validation passes and secrets are securely injected at runtime.


## Server Migration

Server Migration from Server A to Server B follows an auditable, low-risk pattern:

1. Synchronize safe repository state
   - Ensure Server A has committed and pushed all non-secret changes to the GitHub repository.
2. Clone on Server B
   - `git clone <REPOSITORY_URL> <TARGET_DIR>`; `cd <TARGET_DIR>`
3. Bootstrap
   - Create a fresh virtual environment and install dependencies as in Clean Server Bootstrap.
4. Supply Server B external secrets
   - Inject provider credentials and any runtime secrets via the external secret manager or environment injection on Server B only.
5. Restore safe memory
   - Restore latest safe memory, handoff bundles, ADRs, work history, and known issues to their configured paths on Server B.
6. Validate
   - Run tests and Health Validation on Server B. Do not deactivate Server A yet.
7. Start runtime
   - Start the runtime on Server B (foreground or under `systemd`, but do not switch traffic yet).
8. Run health checks
   - Confirm liveness/readiness are green in Server B.
9. Keep Server A available until validation succeeds
   - Only after Server B passes Health Validation should you switch traffic (DNS, load balancer, scheduler) and gracefully retire Server A.


## Provider Migration

Provider Migration allows changing AI providers without rewriting autonomous core code.

- Provider-specific configuration is supplied exclusively through provider adapters and external credentials.
- Update the following at deployment time:
  - `MITIGATE_AI_PROVIDER_ADAPTER`
  - `MITIGATE_AI_PROVIDER_NAME`
  - `MITIGATE_AI_PROVIDER_API_BASE`
  - `MITIGATE_AI_MODEL_NAME` (and `MITIGATE_AI_MODEL_FALLBACK` if applicable)
  - Inject provider credentials via your external secret manager (e.g., API keys, bearer tokens). Do not store secrets in Git.
- Re-run Health Validation after changing providers. The autonomous core remains unchanged.


## Platform Migration

Platform Migration changes the target site stack by replacing or configuring adapters rather than altering the autonomous core. The autonomous core remains platform-neutral.

Site Platform Terminology and adapter responsibilities:

- wordpress: WordPress uses an adapter.
- lovable: Lovable-generated Git projects use an adapter.
- react: React projects use an adapter.
- nextjs: Next.js / nextjs projects use an adapter.
- next.js: Next.js / nextjs projects use an adapter.
- static: Static sites use an adapter.
- php: PHP projects use an adapter.
- generic_git: generic_git projects use an adapter.
- generic git: generic git projects use an adapter.
- custom: custom platforms use injected adapters.

To migrate:

1. Select the appropriate site adapter for the new platform.
2. Set `MITIGATE_AI_SITE_ADAPTER` and `MITIGATE_AI_SITE_PLATFORM` via environment injection.
3. Provide any additional non-secret adapter configuration required by the platform.
4. Do not modify autonomous core code; adapters encapsulate platform specifics.
5. Run tests and Health Validation before activating the new platform path.


## Rollback

Rollback is a controlled, low-risk reversal when validation fails:

- Retain the last known-good Git revision and do not force-push over it.
- Retain safe compatible memory/handoff state used by the known-good revision.
- Do not destroy the prior server before validation of the new change.
- Restore the previous revision/configuration when validation fails:
  - `git checkout <KNOWN_GOOD_REVISION>` on the target host
  - ensure adapters and environment variables match the known-good configuration
- Re-run installation validation (`pytest -q`) and full Health Validation.
- Restart through documented deployment tooling when applicable (foreground or `systemd`).
- Run health checks after rollback to confirm stability.
- Record the rollback outcome in project memory (non-secret) for future reference.


## GitHub Portable Source of Truth

The GitHub repository is the portable source of truth for all non-secret MITIGATE AI platform assets.

Repository-managed assets include:

- source code
- missions
- tests
- schemas
- bootstrap logic
- recovery logic
- deployment assets
- adapter interfaces
- safe memory formats
- handoff formats
- documentation

No secrets or environment-specific credentials are stored in Git. All operational values are injected at runtime via secure channels.


## Security and External Secrets

Strict security posture is mandatory:

- GitHub must never contain real:
  - API keys
  - passwords
  - bearer tokens
  - provider credentials
  - private keys
  - TLS private keys
  - authorization values
  - production secrets
- Use an external secret manager or a secure environment injection mechanism to provide credentials at runtime only.
- Keep `agent/bootstrap/env.example` placeholder-only and safe for public Git. It must not contain machine-specific values or operational defaults (e.g., dev, local, staging, production, default).
- The provider-neutral `ENVIRONMENT` variable in `env.example` is a pure placeholder and must not alter runtime defaults.
- Preserve `MITIGATE_AI_ENVIRONMENT_NAME` as a placeholder. Do not couple activation logic to committed files.
- Validate that all deployments pass Health checks before enabling services, switching traffic, or finalizing cutovers.


## Appendix: Minimal Operator Checklist

- Bootstrap completed on a clean server using a virtual environment
- External secrets injected; no secrets in Git
- Provider adapter configured and reachable
- Site adapter configured; platform-specific assets validated
- Safe memory and handoff restored (non-secret)
- Tests pass; Health liveness and readiness are green
- Optional: `systemd` units prepared but not auto-started by validation
- Activation performed only after successful Health Validation
- Rollback plan validated and documented
