# MITIGATE AI Bootstrap and Portable Recovery

This directory contains portable bootstrap and recovery tooling intended to reconstruct a working installation from the GitHub repository without source-code rewriting.

## GitHub Portable Source of Truth

"The GitHub repository is the portable source of truth for all non-secret MITIGATE AI platform assets."

Included in the repository as portable, non-secret assets:
- production source code
- missions
- tests
- schemas
- bootstrap and recovery tooling
- deployment templates
- adapter interfaces
- safe project-memory formats
- handoff formats
- documentation

Explicitly not included in GitHub and must remain external:
- API keys
- passwords
- bearer tokens
- provider credentials
- private keys
- TLS private keys
- production secrets
- production database backups where sensitive

## Clean Recovery and Portable Bootstrap

A fresh server should not require source-code rewriting. The recovery model is designed to be provider-neutral and server-neutral, relying on adapters and externalized secrets.

Intended clean-recovery model:
1. Clone the GitHub repository.
2. Run the portable bootstrap.
3. Supply external credentials and secrets.
4. Configure provider and site adapters.
5. Restore safe project memory and handoff data.
6. Validate the installation.
7. Start the runtime using repository deployment tooling.

Migration expectations:
- Migration to another supported AI provider must not require rewriting the autonomous core.
- Migration between supported site platforms must use adapters rather than core rewrites.

## Platform Neutrality

The autonomous core is not WordPress-specific. The platform supports multiple site technologies through adapters, including:
- WordPress
- Lovable-generated Git projects
- React
- Next.js
- static sites
- PHP
- generic Git-based websites
- custom web platforms

Adapters isolate provider- or platform-specific logic from the autonomous core so that recovery, migration, and upgrades do not necessitate changing the core.

## Security and Secret Handling

- Do not add real credentials to this repository.
- Keep placeholder values non-operational and safe for Git.
- Do not embed server-specific secrets or private environment state in version control.
- Do not expose authorization values (API keys, tokens, credentials, private keys).
- Store secrets in external secret managers or environment-specific secure storage.
- Treat production database backups as sensitive and keep them external to this repository.

## Environment Placeholders

Use placeholder-only values in example environment files. For example:
- MITIGATE_AI_ENVIRONMENT_NAME uses a canonical placeholder value and must remain non-operational in version control.

See env.example for the placeholder format and copy it to a private environment file when deploying or recovering.

## Deterministic, Portable Operations

- The bootstrap and recovery process must be reproducible without dynamic downloads of secret materials.
- A fresh server should follow the clean recovery model without editing core source code.
- Provider- and platform-specific details are configured via adapters and external configuration only.

## Notes

- Keep GitHub as the non-secret recovery source and do not weaken placeholder requirements.
- The autonomous core must remain portable across providers and site platforms.
