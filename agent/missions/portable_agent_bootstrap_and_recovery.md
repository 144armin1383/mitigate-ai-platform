Mission: Build Portable Agent Bootstrap and Recovery Core

Goal

Create a provider-neutral, platform-neutral bootstrap and recovery subsystem that allows the complete MITIGATE AI platform to be cloned from GitHub and restored on a clean server without recoding.

The repository must remain the portable source of truth for all non-secret code, missions, schemas, tests, adapters, deployment assets, and safe project memory.

Scope

- Generate production code and repository-managed bootstrap/recovery assets.
- Use Python standard library and shell only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Fully compatible with Python 3.12.
- Do not embed real credentials.
- Do not execute real deployment, Git, network, DNS, Nginx, systemd, or provider operations from production Python code.
- Installation scripts may describe and perform local bootstrap operations only when explicitly invoked by an operator.
- Keep all generated files inside the Mission Runner allowlist under agent/.

Portability Goals

A clean server should be able to:

1. clone the repository
2. run one bootstrap command
3. create required local directories
4. create or validate the Python virtual environment
5. validate repository structure
6. create safe local configuration templates
7. restore non-secret project memory
8. configure provider/API credentials externally
9. validate runtime prerequisites
10. start the existing runtime through documented deployment tooling

No source-code rewriting should be required for normal migration.

The platform must remain usable for:

- WordPress
- Lovable-generated sites
- React
- Next.js
- static sites
- PHP applications
- generic Git-based web projects
- other CMS or web platforms through injected adapters

Do not introduce WordPress-specific assumptions into the core bootstrap logic.

Generated Deliverables

- agent/bootstrap/portable_bootstrap.py
- agent/bootstrap/restore_manager.py
- agent/bootstrap/bootstrap.sh
- agent/bootstrap/validate_installation.sh
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
- agent/bootstrap/README.md

Portable Bootstrap Python API

Provide:

- BootstrapConfig
- BootstrapResult
- BootstrapStatus
- PortableBootstrap
- RestoreConfig
- RestoreResult
- RestoreManager
- build_portable_bootstrap
- build_restore_manager

BootstrapConfig

Support:

- repository_root
- agent_root
- data_root
- runtime_data_root
- memory_root
- config_root
- environment_name
- default_project_id
- python_executable
- virtualenv_path
- provider_name
- provider_adapter_name
- site_adapter_name
- restore_memory
- validate_only
- metadata

Rules:

- reject unknown fields
- reject unsafe paths
- reject traversal
- reject null bytes
- do not accept actual secrets
- do not persist credentials
- do not mutate inputs

Repository Validation

Validate presence of critical repository components including:

- agent/ai
- agent/runtime
- agent/api
- agent/orchestrator
- agent/autonomy
- agent/memory
- agent/operations
- agent/missions
- agent/tests
- agent/deploy

Validate required production modules where present:

- runtime service
- private runtime API
- autonomous development supervisor
- project memory manager
- site operations manager

Validation must return safe structured results.

Environment Template

Generate an example environment file with placeholders only.

Support placeholders for:

- MITIGATE_AI_ENVIRONMENT_NAME
- MITIGATE_AI_DEFAULT_PROJECT_ID
- MITIGATE_AI_REPOSITORY_ROOT
- MITIGATE_AI_DATA_ROOT
- MITIGATE_AI_MEMORY_ROOT
- MITIGATE_AI_PROVIDER
- MITIGATE_AI_PROVIDER_API_KEY
- MITIGATE_AI_PROVIDER_BASE_URL
- MITIGATE_AI_PROVIDER_MODEL
- MITIGATE_AI_SITE_ADAPTER
- MITIGATE_AI_RUNTIME_HOST
- MITIGATE_AI_RUNTIME_PORT
- MITIGATE_AI_API_TOKEN

Rules:

- never include real values
- clearly mark secrets as placeholders
- document that real secrets live outside Git
- do not print secret values

Project Template

Generate provider-neutral project configuration supporting:

- project_id
- project_name
- repository
- default_branch
- site_type
- cms_type
- adapter
- canonical_url
- allowed_paths
- denied_paths
- environment
- seo_enabled
- performance_monitoring_enabled
- availability_monitoring_enabled
- security_monitoring_enabled
- accessibility_monitoring_enabled
- ecommerce_enabled
- autonomous_low_risk_fixes
- autonomous_medium_risk_fixes
- memory_enabled
- metadata

The project template must support:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

Do not hard-code provider credentials into project files.

Restore Manager

Support restoration of:

- safe project memory
- handoff bundles
- snapshots
- decision records
- work records
- issue records
- non-secret project configuration
- provider-neutral routing configuration
- runtime-safe state where portable

Never restore:

- API keys
- passwords
- bearer tokens
- cookies
- private keys
- refresh tokens
- authorization headers
- raw provider responses

Restore must validate:

- schema version
- project identity
- record integrity
- path safety
- cross-project isolation
- stale handoff state
- incompatible versions

Memory Portability

Safe memory must remain readable after migration to a different provider or model.

The bootstrap system must not require:

- OpenAI
- Anthropic
- Gemini
- WordPress
- Lovable

Core continuity must work without provider-specific logic.

Bootstrap Shell Script

bootstrap.sh must:

- use bash strict mode
- run from repository root or resolve repository root safely
- refuse root execution unless explicitly needed
- verify Python 3.12-compatible interpreter
- create or validate agent/.venv
- avoid downloading arbitrary remote scripts
- avoid curl-pipe-shell patterns
- avoid installing unspecified dependencies
- validate required directories
- create local data/config directories safely
- copy env.example only when local environment file does not exist
- never overwrite existing secret configuration automatically
- run portable_bootstrap in validation/bootstrap mode
- provide deterministic exit codes
- never echo credentials

The script must not:

- modify DNS
- modify firewall
- install Nginx
- enable systemd services
- deploy production automatically
- force Git operations

Installation Validation

validate_installation.sh must verify:

- expected repository layout
- Python interpreter
- virtualenv
- importability of critical modules
- existence of safe config
- memory schema readability
- runtime entrypoint importability
- no required secret is stored in Git
- selected provider adapter name is syntactically configured
- selected site adapter name is syntactically configured

Validation must not contact external providers.

Recovery Workflow

Document and support:

- fresh clone
- bootstrap
- configuration
- memory restore
- provider credential setup
- project adapter configuration
- validation
- runtime start
- health check
- rollback

Recovery must not depend on files that only exist on the original server.

GitHub Source-of-Truth Contract

The repository must contain all non-secret assets necessary for rebuild.

Portable assets include:

- application code
- missions
- tests
- schemas
- sample config
- deployment scripts
- bootstrap scripts
- adapter interfaces
- memory schema
- handoff format
- documentation

External-only assets include:

- API keys
- passwords
- secrets
- TLS private keys
- production database backups
- provider credentials

The README must clearly distinguish portable Git assets from external secrets.

Versioning

Support:

- bootstrap schema version
- memory schema version
- project configuration version
- compatibility check
- migration-required status
- unsupported-version status

Do not automatically perform destructive migrations.

Platform Neutrality

Bootstrap core must not assume:

- WordPress directory layout
- wp-config.php
- Lovable runtime internals
- Node.js project structure
- PHP layout
- any single CMS

Platform-specific logic belongs in adapters.

Provider Neutrality

Bootstrap core must not assume any one AI provider.

Provider credentials and routing must be externally configured.

Support provider adapter identifiers such as:

- openai
- anthropic
- gemini
- local
- custom

Do not implement provider APIs in this mission.

Security

- no secret persistence
- no raw exception exposure
- no dynamic code execution
- no dynamic imports
- no subprocess in generated Python production code
- no os.system
- no shell execution from Python
- no direct Git execution
- no direct deployment execution
- no unrestricted filesystem writes

Shell scripts must avoid eval and unsafe interpolation.

Events

Emit safe bootstrap/recovery events:

- bootstrap_started
- repository_validated
- configuration_prepared
- memory_restore_started
- memory_restore_completed
- memory_restore_failed
- installation_validated
- bootstrap_completed
- bootstrap_failed
- recovery_completed
- recovery_failed

Events may include only:

- safe project identifiers
- version identifiers
- status
- counts
- timestamps
- safe failure codes

Failure Codes

Support:

- invalid_bootstrap_config
- unsafe_path
- repository_invalid
- python_incompatible
- virtualenv_invalid
- configuration_invalid
- memory_restore_failed
- schema_incompatible
- project_mismatch
- adapter_configuration_invalid
- installation_validation_failed
- dependency_failed
- timeout

Documentation

README must include:

- clean server prerequisites
- clone procedure
- bootstrap procedure
- secret configuration procedure
- provider configuration
- project configuration
- WordPress adapter example
- Lovable/generic Git adapter example
- generic web project example
- memory restore
- validation
- runtime start
- systemd integration reference
- health check
- migration between servers
- migration between providers
- backup strategy
- rollback strategy
- security model
- GitHub source-of-truth model

Generated File Safety

- Do not import ast, importlib, subprocess, pty, pickle, shelve, or marshal in generated production Python.
- Do not use eval, exec, or compile.
- Do not use os.system.
- Generated Python must pass py_compile.
- Shell files must be syntactically valid by design.
- All existing unittest tests must pass.

Deliverables

- agent/bootstrap/portable_bootstrap.py
- agent/bootstrap/restore_manager.py
- agent/bootstrap/bootstrap.sh
- agent/bootstrap/validate_installation.sh
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
- agent/bootstrap/README.md
