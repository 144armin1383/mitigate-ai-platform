Mission: Finalize Portable Recovery Contract

Goal

Finalize the production portable bootstrap and recovery documentation/template contract so strict clean-checkout recovery tests pass without weakening any safety, portability, or secret-handling requirement.

Modify only:

- agent/bootstrap/env.example
- agent/bootstrap/README.md

Do not modify tests.
Do not modify Python production code.
Do not add dependencies.
Do not modify requirements.txt.
Do not weaken security requirements.
All existing unittest tests must pass.

Environment Compatibility Contract

The committed env.example must remain placeholder-only and non-operational.

Preserve all existing MITIGATE_AI_* variables.

Additionally include a generic portable environment compatibility variable exactly as:

ENVIRONMENT="<ENVIRONMENT>"

This variable is a provider-neutral and platform-neutral environment descriptor intended for portable bootstrap consumers.

It must:

- contain only the placeholder <ENVIRONMENT>
- contain no real environment value
- contain no machine-specific value
- contain no secret
- remain safe for Git
- not replace MITIGATE_AI_ENVIRONMENT_NAME
- not cause bootstrap runtime defaults to change automatically

Keep:

MITIGATE_AI_ENVIRONMENT_NAME="<ENVIRONMENT>"

Do not introduce operational defaults such as:

- dev
- local
- staging
- production
- default

All committed configuration values must remain placeholders.

README Production Recovery Contract

The README must become a complete operational recovery guide, not merely a conceptual overview.

It must include explicit sections with these headings or exact terms:

- Prerequisites
- Clean Server Bootstrap
- Restore
- Health Validation
- Systemd Integration
- Server Migration
- Provider Migration
- Platform Migration
- Rollback
- GitHub Portable Source of Truth
- Security and External Secrets

Prerequisites

Explicitly document prerequisites for a fresh server including:

- supported Linux environment
- Python 3.12-compatible interpreter
- Git
- repository access
- ability to create a Python virtual environment
- external access to required credentials
- sufficient filesystem permissions
- project-specific adapter configuration

Clean Server Bootstrap

Document the sequence:

1. clone repository
2. run bootstrap
3. configure external secrets
4. configure provider adapter
5. configure site adapter
6. restore safe memory/handoff
7. validate installation
8. start runtime
9. run health validation

Restore

Document restoration of:

- safe project memory
- handoff bundles
- architecture decisions
- work history
- known issues
- non-secret configuration

Explicitly state that credentials are never restored from Git.

Health Validation

Include the exact term:

Health

Document:

- runtime liveness validation
- readiness validation
- bootstrap validation
- installation validation
- failure investigation before production activation

Systemd Integration

Include the exact term:

systemd

Document that repository-managed systemd deployment assets are available under:

agent/deploy/systemd/

Explain that service activation is an explicit operator/deployment action and is not performed automatically by portable recovery validation.

Server Migration

Include the exact phrase:

Server Migration

Document migration from Server A to Server B:

1. synchronize safe repository state
2. clone on Server B
3. bootstrap
4. supply Server B external secrets
5. restore safe memory
6. validate
7. start runtime
8. run health checks
9. keep Server A available until validation succeeds

Provider Migration

Include the exact phrase:

Provider Migration

Document changing AI providers without rewriting autonomous core code.

Provider-specific configuration must be supplied through provider adapters and external credentials.

Site Platform Terminology

README must explicitly contain all of these literal platform terms:

- wordpress
- lovable
- react
- nextjs
- next.js
- static
- php
- generic_git
- generic git
- custom

Explain that:

- WordPress uses an adapter.
- Lovable-generated Git projects use an adapter.
- React projects use an adapter.
- Next.js / nextjs projects use an adapter.
- Static sites use an adapter.
- PHP projects use an adapter.
- generic_git projects use an adapter.
- custom platforms use injected adapters.

The autonomous core must remain platform-neutral.

Platform Migration

Include the exact phrase:

Platform Migration

Explain that migration between supported site stacks must replace or configure adapters rather than rewrite the autonomous core.

Rollback

Include the exact term:

Rollback

Document a safe rollback procedure:

- retain the last known-good Git revision
- retain safe compatible memory/handoff state
- do not destroy the prior server before validation
- restore the previous revision/configuration when validation fails
- re-run installation validation
- restart through documented deployment tooling when applicable
- run health checks after rollback
- record the rollback outcome in project memory

GitHub Portable Source of Truth

Explicitly include this exact statement:

The GitHub repository is the portable source of truth for all non-secret MITIGATE AI platform assets.

Document repository-managed assets including:

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

Security and External Secrets

Explicitly state that GitHub must never contain real:

- API keys
- passwords
- bearer tokens
- provider credentials
- private keys
- TLS private keys
- authorization values
- production secrets

Do not weaken existing secret controls.

Completeness Requirement

The documentation must be sufficient for an operator or a new AI agent with no prior conversation history to understand how to:

- reconstruct the platform
- restore project continuity
- change servers
- change AI providers
- change supported site platforms
- validate health
- activate systemd deployment when appropriate
- rollback safely

Do not merely mention these concepts in passing.
Provide actionable recovery guidance for each.

Generated File Safety

- Do not include real secrets.
- Do not include realistic private-key material.
- Do not introduce dynamic downloads.
- Do not use eval.
- Do not weaken placeholder validation.
- Do not introduce server-specific state.
- All existing unittest tests must pass.

Deliverables

- agent/bootstrap/env.example
- agent/bootstrap/README.md
