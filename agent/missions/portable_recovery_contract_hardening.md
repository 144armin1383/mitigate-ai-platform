Mission: Harden Portable Recovery Contract

Goal

Align the existing portable bootstrap assets with the strict clean-recovery contract required for provider-neutral and server-neutral reconstruction from GitHub.

Modify only:

- agent/bootstrap/env.example
- agent/bootstrap/README.md

Do not modify any other production file.
Do not generate tests.
Do not add dependencies.
Do not modify requirements.txt.
All existing unittest tests must pass.

Environment Placeholder Contract

In agent/bootstrap/env.example:

- Preserve the variable name MITIGATE_AI_ENVIRONMENT_NAME.
- Change its placeholder value from <ENVIRONMENT_NAME> to the canonical generic placeholder <ENVIRONMENT>.
- Keep it clearly non-operational and safe for Git.
- Do not introduce a real environment name.
- Do not introduce dev, staging, production, local, or another operational default as the assigned value.
- Keep all other secret and configuration fields placeholder-only.
- Do not add duplicate environment variables solely for compatibility.

The resulting line must be:

MITIGATE_AI_ENVIRONMENT_NAME="<ENVIRONMENT>"

GitHub Source-of-Truth Contract

Add an explicit section to agent/bootstrap/README.md titled:

GitHub Portable Source of Truth

The section must explicitly state:

"The GitHub repository is the portable source of truth for all non-secret MITIGATE AI platform assets."

Also document that the repository includes portable non-secret assets such as:

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

Explicitly state that the following remain external to GitHub:

- API keys
- passwords
- bearer tokens
- provider credentials
- private keys
- TLS private keys
- production secrets
- production database backups where sensitive

Recovery Guarantee Documentation

README must explicitly explain that a fresh server should not require source-code rewriting.

The intended recovery model is:

1. Clone the GitHub repository.
2. Run the portable bootstrap.
3. Supply external credentials and secrets.
4. Configure provider and site adapters.
5. Restore safe project memory and handoff data.
6. Validate the installation.
7. Start the runtime using repository deployment tooling.

Document that migration to another supported AI provider must not require rewriting the autonomous core.

Document that migration between supported site platforms must use adapters rather than core rewrites.

Platform Neutrality

README must explicitly mention that the core is not WordPress-specific.

It must support through adapters:

- WordPress
- Lovable-generated Git projects
- React
- Next.js
- static sites
- PHP
- generic Git-based websites
- custom web platforms

Security

- Do not add real credentials.
- Do not weaken placeholder requirements.
- Do not embed server-specific secrets.
- Do not add private environment state.
- Do not expose authorization values.
- Keep GitHub safe as the non-secret recovery source.

Generated File Safety

- Do not use dynamic code execution.
- Do not add remote downloads.
- Do not introduce secret material.
- All existing unittest tests must pass.

Deliverables

- agent/bootstrap/env.example
- agent/bootstrap/README.md
