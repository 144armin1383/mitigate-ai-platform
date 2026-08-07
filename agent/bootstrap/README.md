# MITIGATE AI Portable Bootstrap

This directory contains the portable bootstrap layer for reconstructing a safe, provider-neutral runtime from a clean Git checkout. The source of truth is the GitHub repository itself. No production credentials are committed here and no remote downloads are performed by the bootstrap script.

Key capabilities:
- Provider-neutral configuration via adapters
- Site/platform-neutral configuration via site adapters
- Clean bootstrap from a repository checkout
- Restore from safe memory state
- Health validation
- Systemd service integration (optional, external)
- Server migration, provider migration, platform migration, and rollback paths

Provider adapters (identifiers/examples only):
- openai
- anthropic
- gemini
- local
- custom

Changing between these providers uses provider adapters and external runtime configuration. You do not need to rewrite the autonomous core to migrate between providers.

Supported site/platform adapters include, but are not limited to:
- wordpress
- lovable
- react
- nextjs / Next.js
- static
- php
- generic_git
- custom

Prerequisites
- Python 3.12+ runtime available
- Git checkout of the repository (GitHub portable source of truth)
- External runtime configuration (environment variables or system service configuration)

Clean Bootstrap
1. Clone the repository to the target server.
2. Copy agent/bootstrap/env.example to your external configuration store and set values there (do not commit credentials to the repo).
3. Use the bootstrap script for local validation and guidance:

   ./agent/bootstrap/bootstrap.sh

Restore
- Restore uses safe, provider-neutral memory roots defined externally. Ensure the DATA_ROOT and MEMORY_ROOT are set via environment configuration.

Health
- A minimal health check can be run via your runtime entrypoint. Ensure configuration is provided externally before launching.

Systemd
- Integrate with systemd by configuring a unit file that sources your external environment. Do not write secrets into service files. Activation is performed outside of this repository.

Server Migration
- Reconstruct the runtime on a fresh server using:
  - repository clone
  - bootstrap
  - external runtime configuration
  - provider adapter selection
  - site adapter selection
  - safe memory restore
  - validation
  - runtime startup

Provider Migration
- Switch provider adapters (e.g., openai, anthropic, gemini, local, custom) purely by changing external configuration. No source-code rewrite is required for normal provider changes.

Platform Migration
- Switch supported platforms (wordpress, lovable, react, nextjs/Next.js, static, php, generic_git, custom) using site adapters and external configuration. No source-code rewrite is required for normal site/platform migration.

Rollback
- Use Git to roll back to a known state, then re-apply external configuration and restart the runtime. No committed credentials or environment-specific defaults are required here.

WordPress, Lovable, React, Next.js, Static, PHP, generic_git, custom
- These are supported via site adapters and project configuration examples. Adapters are chosen via external configuration, not hard-coded in the autonomous core.

Testing Policy
- This repository uses Python's standard unittest framework. To run repository tests locally:

  python -m unittest discover -s agent/tests -p 'test_*.py' -v

Notes
- Do not embed credentials in README, configuration files, or code.
- The bootstrap remains deterministic and neutral across providers and platforms.
- Unknown configuration fields are rejected by the strict bootstrap parser.
- Unsafe paths (e.g., traversal, absolute escape, null byte) are rejected with safe error messages.
