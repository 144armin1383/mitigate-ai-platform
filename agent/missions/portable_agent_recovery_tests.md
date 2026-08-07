Mission: Build Portable Agent Recovery and Clean Checkout Tests

Goal

Create a comprehensive unittest suite that validates the existing portable bootstrap and recovery subsystem from a clean repository checkout model.

The tests must prove that the MITIGATE AI platform can be reconstructed on another server using the Git repository plus external credentials, without requiring source-code rewriting or hidden files from the original server.

Scope

- Generate test code only.
- Do not modify production bootstrap or recovery modules.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use Python standard library unittest only.
- Fully compatible with Python 3.12.
- Do not perform real network calls.
- Do not clone real repositories.
- Do not execute real Git commands.
- Do not execute systemd, Nginx, DNS, firewall, provider, or deployment operations.
- Use TemporaryDirectory for clean-checkout simulations.
- Tests must never depend on files outside the repository except explicitly simulated external secret/config locations.

Modules Under Test

- agent.bootstrap.portable_bootstrap
- agent.bootstrap.restore_manager

Repository Assets Under Test

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/validate_installation.sh
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
- agent/bootstrap/README.md

Clean Checkout Model

Simulate a clean server containing only:

- repository-controlled files
- Python interpreter
- temporary writable directories
- externally supplied placeholder credential/config values

The simulation must not depend on:

- /etc/mitigate-ai
- existing runtime data from the current server
- current machine-specific environment files
- current shell history
- hidden local files
- existing project memory outside the repository
- existing service units
- existing provider sessions
- existing API credentials

Portability Contract

Verify that all non-secret assets required for rebuild are repository-managed.

Repository-managed assets include:

- production code
- missions
- tests
- schemas
- bootstrap logic
- recovery logic
- deployment templates
- sample configuration
- safe project-memory formats
- handoff formats
- adapter interfaces
- documentation

External-only assets include:

- provider API keys
- passwords
- bearer tokens
- private keys
- TLS private keys
- production database backups
- production credentials

Verify that missing external secrets produce safe configuration-required states rather than source-code failures.

Bootstrap Configuration Tests

Test:

- valid BootstrapConfig
- unknown field rejection
- unsafe repository path rejection
- traversal rejection
- null byte rejection
- configuration input not mutated
- no real secret accepted as repository state
- provider-neutral configuration
- site-adapter-neutral configuration

Repository Validation Tests

Verify detection of required repository directories:

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
- agent/bootstrap

Verify detection of critical modules:

- Runtime Service
- Runtime Private API
- Autonomous Development Supervisor
- Project Memory Manager
- Site Operations Manager
- Portable Bootstrap
- Restore Manager

Test:

- complete repository
- missing required directory
- missing required module
- malformed path
- deterministic validation result

Environment Template Tests

Verify env.example:

- contains placeholders only
- contains no real secret
- includes environment name
- includes project identifier
- includes repository root
- includes data root
- includes memory root
- includes provider
- includes provider API key placeholder
- includes provider base URL placeholder
- includes provider model
- includes site adapter
- includes runtime host
- includes runtime port
- includes API token placeholder

Verify secrets are explicitly documented as external to Git.

Project Template Tests

Verify project.example.json supports:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

Verify project configuration contains:

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

Verify no provider credentials are embedded.

Platform Neutrality Tests

Verify bootstrap core contains no required assumptions about:

- WordPress
- wp-config.php
- wp-content
- Lovable internals
- React
- Next.js
- Node.js
- PHP
- any single CMS

Platform-specific behavior must be represented through adapter configuration.

Provider Neutrality Tests

Verify the bootstrap can represent provider adapter identifiers such as:

- openai
- anthropic
- gemini
- local
- custom

Verify:

- no provider is mandatory in core logic
- no provider SDK dependency exists
- API credentials are external
- provider changes do not require modifying bootstrap source
- restored memory remains provider-neutral

Restore Tests

Test restoration of:

- safe project memory
- handoff bundle
- snapshots
- decision records
- work records
- issue records
- project configuration
- provider-neutral routing configuration

Verify restore rejects or excludes:

- API keys
- passwords
- bearer tokens
- cookies
- private keys
- refresh tokens
- authorization headers
- raw provider responses

Test:

- valid schema
- unsupported schema
- incompatible schema
- project mismatch
- cross-project memory
- corrupted memory
- stale handoff
- path traversal
- deterministic result
- input not mutated

Memory Continuity Tests

Create a simulated project history containing:

- architecture decision
- completed work
- failed attempt
- known issue
- pending work
- next action
- security constraint
- deployment summary

Generate or restore safe handoff state.

Verify a fresh manager can determine:

- what project it is
- architecture state
- completed work
- failed approaches to avoid
- open issues
- remaining work
- approval boundaries
- next action

The test must require no prior conversation history.

Server Migration Tests

Simulate:

Server A:
- project memory exists
- handoff generated
- safe repository export exists

Server B:
- starts with clean repository-controlled state
- receives safe memory/handoff data
- receives externally simulated credentials
- restores project state

Verify Server B can continue without source-code rewriting.

Provider Migration Tests

Simulate:

- original provider identifier = one provider
- new provider identifier = different provider
- same project memory
- same handoff
- same site adapter

Verify:

- project continuity remains intact
- prior provider-specific secrets are absent
- new provider credentials can be external
- no production module rewrite is required

Site Platform Migration Tests

Verify bootstrap/recovery supports configurations for:

- WordPress
- Lovable-generated Git project
- React
- Next.js
- static
- PHP
- generic Git project

The bootstrap and memory layers must remain unchanged across these configurations.

Bootstrap Script Tests

Read bootstrap.sh as text.

Verify:

- bash strict mode
- resolves repository root safely
- verifies compatible Python
- creates or validates agent/.venv
- does not overwrite existing environment configuration automatically
- does not print credentials
- does not use eval
- does not use curl-pipe-shell
- does not modify DNS
- does not modify firewall
- does not install Nginx
- does not enable systemd
- does not deploy production
- deterministic exit behavior is documented

Installation Validation Script Tests

Read validate_installation.sh as text.

Verify validation for:

- repository structure
- Python
- virtualenv
- critical imports
- configuration existence
- memory schema readability
- runtime entrypoint importability
- provider adapter configuration
- site adapter configuration

Verify:

- no real provider call
- no network requirement
- no secret output

GitHub Source-of-Truth Tests

Verify repository includes all non-secret assets necessary for recovery.

Verify bootstrap/recovery documentation explicitly states:

- GitHub/repository is the portable source of truth
- secrets remain external
- safe memory and handoff are portable
- a fresh server does not require recoding
- provider migration does not require recoding
- site-platform migration uses adapters

Clean Checkout Reconstruction Test

Create a TemporaryDirectory representing a clean cloned repository.

Copy only repository-controlled bootstrap/recovery fixtures needed for the test.

Do not copy current server-specific configuration.

Run production Python bootstrap validation functions through their public interfaces.

Verify result indicates either:

- ready for external configuration
or
- successfully validated

It must not fail because of missing hidden original-server state.

No real secret may be required for validation-only mode.

Recovery Documentation Tests

Verify README documents:

- clean server prerequisites
- clone
- bootstrap
- external secret setup
- provider setup
- site adapter setup
- WordPress example
- Lovable/generic Git example
- generic web project example
- memory restore
- validation
- runtime start
- systemd reference
- health check
- server migration
- provider migration
- backup
- rollback
- GitHub source-of-truth model
- security model

Security Tests

Verify no:

- actual secrets
- credentials
- authorization headers
- private keys
- access tokens
- refresh tokens
- cookies
- provider raw responses
- raw traceback persistence
- unrestricted filesystem writes
- dynamic code execution
- direct Git execution
- direct production deployment

Repository Safety

- Do not create persistent temporary files in repository root.
- Use TemporaryDirectory.
- Clean up all test resources.
- Do not modify unrelated files.
- Tests must leave a clean working tree when started from a clean checkout.

Generated Test Safety

- Do not import ast.
- Do not use dynamic imports.
- Do not use dynamic code execution.
- Do not use subprocess, os.system, pty, pickle, shelve, or marshal.
- Do not execute bootstrap.sh or validate_installation.sh.
- Read shell scripts only as text.
- Generated Python must pass py_compile.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/tests/test_portable_agent_recovery.py

Forbidden Secret Fixture Safety

Tests must never embed realistic credential, private-key, certificate-key, bearer-token, API-key, or authentication-secret material.

In particular:

- Do not include PEM private-key headers or footers.
- Do not include strings resembling real private keys.
- Do not include realistic JWTs.
- Do not include realistic API keys.
- Do not include bearer-token examples that resemble production credentials.
- Do not include credential fixtures that trigger Mission Runner forbidden-content validation.

Use neutral synthetic placeholders instead, for example:

- "<PRIVATE_KEY_PLACEHOLDER>"
- "<API_KEY_PLACEHOLDER>"
- "<TOKEN_PLACEHOLDER>"
- "<PASSWORD_PLACEHOLDER>"
- "<AUTHORIZATION_PLACEHOLDER>"
- "<COOKIE_PLACEHOLDER>"

Security tests must validate key-name redaction and secret exclusion using safe placeholder values rather than realistic secret formats.

Do not weaken secret-detection expectations.
Do not modify production secret-redaction logic merely to satisfy the test suite.
All existing and newly generated unittest tests must pass.
