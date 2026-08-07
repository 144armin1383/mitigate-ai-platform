MITIGATE AI Bootstrap Guide

Overview
This directory contains the portable bootstrap template for initializing, restoring, or migrating a project instance from a GitHub-first source of truth. It is designed to be provider-neutral and platform-agnostic so that a Clean Server can reconstruct the system from versioned assets plus externally supplied protected runtime configuration.

Key Principles
- GitHub portable source of truth: Only non-secret, reproducible assets live in Git.
- External Secret: Protected runtime configuration (access tokens, API keys, DB passwords) is never committed and must be injected outside Git.
- Provider Setup is pluggable: You select a provider adapter (e.g., openai, anthropic, gemini, local, custom) and supply credentials and settings outside this repo.
- Platform/profile separation: Choose an adapter in project.example.json while keeping detailed profiles under a separate key so portability remains intact.
- Recovery validation is offline: No external calls are needed to validate structure and readiness during recovery planning.

File Inventory
- env.example: Environment template containing only placeholder values for sensitive variables.
- project.example.json: Provider-neutral, platform-agnostic project template. The top-level adapter is a configurable string; detailed profiles are stored separately.

Clean Server
A Clean Server is a new or rebuilt host with no residual state. It can reconstruct the platform solely from the GitHub repository plus an External Secret bundle supplied at restore time. The bootstrap process reads project.example.json for structure and injects runtime variables from a secure channel, enabling fresh provision without leaking credentials into Git.

External Secret
An External Secret is any protected runtime configuration provided outside version control. Operators deliver API tokens, PROVIDER_API_KEY, database URLs, and similar confidential values via a secure secret manager, offline envelope, or one-time host injection. These values are never placed in env.example, project.example.json, or any committed file. The template includes placeholder lines only and prohibits realistic or operational defaults for sensitive variables.

Provider Setup
Provider Setup is the operator task of selecting a provider adapter and injecting its protected configuration. Supported provider adapter identifiers include: openai, anthropic, gemini, local, and custom. To switch providers:
1) Select an adapter in agent/bootstrap/project.example.json by setting the top-level adapter string (e.g., "openai" or "local").
2) Provide the provider runtime configuration via External Secret mechanisms (never commit these values).
3) Restart or redeploy following the restore section below. No source-code rewrite is required for normal migration.

Generic Git
Generic Git projects that are not tied to WordPress or Lovable can use the generic_git adapter/profile without changing the autonomous core. This path supports general repositories, monorepos, or mixed-language projects while preserving the portability guarantees of this platform.

Backup
Backup in this context refers to a non-secret portability backup strategy. Operators should maintain human-readable and reproducible artifacts:
- Safe project memory and notes that do not contain secrets.
- Handoff bundles that include high-level runbooks, operator checklists, and contact points.
- Architecture decisions (ADRs) capturing constraints, trade-offs, and interfaces.
- Project configuration that is non-secret (profiles, adapters, and build commands).
- Known issues and limitations with mitigation steps.
- Work history summaries mapped to Git revision references.

Sensitive production data and protected runtime values remain outside Git and require their own secure backup process in a compliant secret storage system. Keep these streams separate to maintain a clean recovery boundary.

Security Model
The Security Model centers on strict separation of concerns:
- GitHub stores non-secret portable assets only.
- Protected runtime configuration remains external and is injected as an External Secret at restore or deploy time.
- Recovery validation is offline and does not depend on external networks.
- Platform/provider adapters do not weaken core isolation: choosing a provider or platform profile cannot force secrets into Git.
- Restore operations validate project identity and safe paths to avoid path traversal and unauthorized file writes.

Prerequisites
- Git installed and access to the repository.
- Secure channel for delivering External Secret material to operators.
- System user with permission to deploy and configure services (e.g., systemd where applicable).

Bootstrap
1) Clone the GitHub repository to the target host.
2) Review agent/bootstrap/project.example.json and select the appropriate adapter by setting the top-level adapter string.
3) Prepare an External Secret bundle containing the necessary runtime configuration for the chosen provider and platform.
4) Provision runtime dependencies (language runtimes, web server, process manager) per profile guidance below.
5) Start services and verify health checks.

Restore
To perform a restore on a Clean Server:
1) Fetch the repository at the desired Git revision reference.
2) Copy env.example to a private .env file and replace placeholder values using only the External Secret bundle.
3) Confirm project.example.json adapter matches the intended platform/provider.
4) Execute any documented bootstrap/restore scripts and confirm application health without committing new secrets.

Health
- Validate process readiness via application logs and health endpoints.
- Ensure no secret material is written to Git or world-readable locations.
- Confirm static assets and build artifacts are generated in expected directories for the chosen profile.

systemd
Where systemd is used:
- Provide unit files that reference environment files located outside the repository.
- Validate Restart and ExecStart settings point to safe, absolute paths.
- Keep environment files permission-restricted and excluded from Git.

Server Migration
- Rebuild the destination as a Clean Server.
- Transfer only Git-hosted assets and the External Secret bundle via a secure channel.
- Validate integrity with Git revision references and checksums of handoff bundles.

Provider Migration
- Update the adapter in project.example.json to the new provider identifier (e.g., openai, anthropic, gemini, local, custom).
- Rotate and deliver a fresh External Secret bundle appropriate for the new provider.
- Restart services and validate behavior. No code rewrite is required for normal migration.

Platform Migration
- Change the adapter string in project.example.json to the target platform profile (e.g., wordpress, lovable, react, nextjs, static, php, generic_git, custom).
- Apply any documented build/run steps for the new profile.
- Do not commit secrets; inject only through External Secret channels.

Rollback
- Use GitHub as the source of truth to roll back to a prior Git revision reference.
- Re-apply or reuse compatible External Secret values if unchanged; otherwise rotate as needed.
- Validate the environment in offline mode first when possible.

Platform Profiles and Adapters
- WordPress: Use the wordpress profile. Web root typically resides under public. Database and salts must be provided as External Secret values.
- Lovable: Use the lovable profile for builder-driven static or hybrid sites. All provider keys remain external.
- React: Use the react profile with a build step (npm run build). Serve the build directory.
- Next.js / nextjs: Use the nextjs profile. Ensure server/runtime configuration is injected externally.
- static: Use the static profile for simple HTML/CSS/JS without server-side code.
- PHP: Use the php profile for generic PHP applications. Keep DB and API tokens external.
- generic_git: Use the generic_git profile for Git-based projects not tied to a specific framework.
- custom: Use the custom profile for bespoke integrations. Implement adapters outside committed templates.

Template Contracts
- env.example: Only placeholder values for sensitive variables. Example lines:
  - PROVIDER_API_KEY and MITIGATE_AI_PROVIDER_API_KEY must be set to "<PLACEHOLDER>".
  - API_TOKEN and MITIGATE_AI_API_TOKEN must be set to "<PLACEHOLDER>".
- project.example.json:
  - The top-level adapter is a configurable string (e.g., "wordpress", "react", "openai", or "local").
  - Detailed platform profiles are preserved under the separate profiles key (and/or supported_adapters).
  - No provider authentication data is embedded.

Portability
This template supports:
- Fresh server reconstruction (Clean Server) using Git plus External Secret.
- Provider migration by switching the adapter and rotating secrets.
- Site-platform migration by selecting a different platform profile without code rewrites.
- GitHub-first recovery and AI handoff continuity via documented profiles and non-secret artifacts.

Compliance Notes
- Do not place access values, tokens, or provider secrets in any committed file.
- Validate restore steps offline where possible and verify safe file paths.
- Keep non-secret documentation current to support rapid, deterministic recovery.
