Portable Bootstrap and Recovery

This bootstrap layer prepares a clean, portable recovery environment for the agent without invoking provider-specific commands or modifying the deployment state. It emphasizes correctness, safety, and reproducibility so that a clean checkout can be validated and made ready for configuration.

Site adapter contract

The site adapter is the small, replaceable integration layer that selects the platform or framework while the autonomous core of the agent remains unchanged. By swapping the site adapter, you can target platforms such as WordPress, Lovable, React, Next.js, PHP, Generic Git, or a custom integration without altering mission logic, memory systems, orchestration, or security posture. This separation ensures that recovery flows, source-of-truth handling, and migrations are consistent across diverse environments while still enabling platform-specific operations where necessary.

Key properties
- Portable by default: no direct Git execution, no network calls, and no deployment side effects.
- Deterministic: repository-relative path resolution and strict validation.
- Secure: no secrets are required for structure validation; external-secret retrieval happens only in dedicated stages.

Recovery and validation
- Structural recovery: ensures the repository layout is intact before any runtime or adapter configuration is applied.
- Configuration-required is acceptable: placeholders are allowed on a clean checkout, enabling validation-ready states without credentials.
- Source-of-truth: respects repository sources of truth for code, configurations, and content, avoiding ad hoc runtime mutations.

Migrations and backups
- Migration safety: schema/content migrations must be driven via explicit, auditable steps in dedicated operations.
- Backups: encourage verified, restorable backups prior to any destructive change; the bootstrap does not perform backup but expects higher-level workflows to do so.

Security and external secrets
- No secrets are embedded here; use external-secret solutions or environment injection in higher layers.
- The bootstrap does not fetch or manage secrets, preserving least-privilege and isolation.

Adapter examples
- WordPress
- Lovable
- React
- Next.js
- PHP
- Generic Git
- custom

Refer to the project template for supported site types and to the portable bootstrap for repository structure validation.

## Source of Truth

The Git repository is the portable source of truth for all non-secret application, bootstrap, recovery, mission, adapter, memory-schema, and documentation assets.

## Clean Server

A clean server can reconstruct the platform from the repository plus externally supplied runtime configuration and protected values, without source-code rewriting.

## Provider Setup

Provider setup is performed through provider-neutral configuration and adapters. Provider selection and protected access configuration remain external to the portable core.

## Health

After recovery or migration, application health must be verified before production use. Health validation should confirm runtime readiness, required files, configuration availability, and service behavior.

## Systemd

Where systemd is used, service unit templates should reference portable repository paths and external runtime configuration. Service activation remains a separate operational step.

## Server Migration

Server migration should use the Git repository as the source of truth, restore safe project memory and handoff data, then supply environment-specific runtime configuration externally on the destination server.

## Provider Migration

Provider migration must not require rewriting the autonomous core. Provider adapters and external provider configuration allow switching providers while preserving project memory and operational continuity.

## Rollback

Rollback should use a known-good Git revision, compatible project memory state, and previously validated runtime configuration. Production rollback must be followed by health validation.

## Security Model

The security model separates portable non-secret repository assets from protected runtime configuration. Sensitive values remain external to Git, restore paths are validated, project isolation is preserved, and recovery does not require direct network, Git, or deployment execution inside the bootstrap core.
