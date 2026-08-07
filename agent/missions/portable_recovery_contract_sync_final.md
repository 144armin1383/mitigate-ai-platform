Mission: Final Portable Recovery Contract Synchronization

Goal

Resolve the final portable recovery contract mismatches without changing tests or production Python/shell logic.

Modify only:

- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
- agent/bootstrap/README.md

Do not modify:
- tests
- Python production modules
- shell scripts
- requirements.txt
- deployment files
- runtime files
- memory files
- adapters

Do not add dependencies.
All existing unittest tests must pass.

1. Environment Template Sensitive Placeholder Contract

agent/bootstrap/env.example must keep all sensitive fields placeholder-only.

The exact sensitive variable:

PROVIDER_API_KEY

must use a neutral placeholder format accepted by strict placeholder validation.

Use exactly:

PROVIDER_API_KEY="<PLACEHOLDER>"

Also set:

MITIGATE_AI_PROVIDER_API_KEY="<PLACEHOLDER>"

Do not use:

- <PROVIDER_API_KEY>
- real-looking keys
- realistic encoded values
- inline comments after the assignment
- operational defaults

Each sensitive assignment line must contain only the variable name, equals sign, quoted placeholder value, and newline.

For API token compatibility use:

API_TOKEN="<PLACEHOLDER>"
MITIGATE_AI_API_TOKEN="<PLACEHOLDER>"

If other sensitive-looking template fields exist, normalize them to the same neutral placeholder style where required.

Do not include real access material.

2. Project Adapter Canonical Contract

In agent/bootstrap/project.example.json:

The top-level field:

adapter

must be a configurable string, not an object.

Set:

"adapter": "<SITE_ADAPTER>"

Do not store the platform profile object inside the top-level adapter field.

3. Preserve Platform Profiles Separately

Preserve support for:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

If detailed platform profile examples are useful, store them in a separate non-conflicting top-level field such as:

"profiles"

or:

"supported_adapters"

Do not rename or remove required canonical project fields.

The detailed profile map must not replace the string adapter field.

4. Project Template Safety

The project template must remain provider-neutral and platform-neutral.

Do not embed:

- access values
- protected runtime values
- provider authentication data

Avoid credential-like terminology prohibited by the strict recovery contract.

Keep the canonical top-level required fields already established by previous missions.

5. README Missing Recovery Topics

agent/bootstrap/README.md must explicitly contain and explain these exact concepts:

- clean server
- external secret
- provider setup
- generic git
- backup
- security model

These must not be keyword-only additions.

Add useful operator-facing sections or paragraphs.

6. Clean Server

Include the exact phrase:

Clean Server

Document that a new host can reconstruct the platform from the GitHub repository plus externally supplied protected runtime configuration.

7. External Secret

Include the exact phrase:

External Secret

Explain that protected access values are supplied outside Git and are never committed into repository templates.

8. Provider Setup

Include the exact phrase:

Provider Setup

Explain how an operator selects a provider adapter and supplies its protected runtime configuration externally.

Mention provider adapter identifiers already supported/documented, including:

- openai
- anthropic
- gemini
- local
- custom

Do not include access values.

9. Generic Git

Include the exact phrase:

Generic Git

Explain that Git-based projects that are not tied to WordPress or Lovable can use the generic_git adapter/profile without changing the autonomous core.

10. Backup

Include the exact term:

Backup

Document a non-secret portability backup strategy covering:

- safe project memory
- handoff bundles
- architecture decisions
- project configuration
- known issues
- work history
- Git revision references

State that sensitive production data and protected runtime values remain outside Git and require their own secure backup process.

11. Security Model

Include the exact phrase:

Security Model

Document the recovery security boundary:

- GitHub stores non-secret portable assets
- protected runtime configuration remains external
- recovery validation is offline
- platform/provider adapters do not weaken core isolation
- restore operations validate project identity and safe paths

12. Preserve Existing Documentation

Do not remove existing documentation for:

- GitHub portable source of truth
- prerequisites
- bootstrap
- restore
- health
- systemd
- server migration
- provider migration
- platform migration
- rollback
- WordPress
- Lovable
- React
- Next.js / nextjs
- static
- PHP
- generic_git
- custom

13. Portability

The result must remain suitable for:

- fresh server reconstruction
- provider migration
- site-platform migration
- GitHub-first recovery
- AI handoff continuity

No source-code rewrite should be required for normal migration.

14. Validation

All modified files must remain syntactically valid.

project.example.json must parse as valid JSON.

env.example must remain simple KEY="VALUE" template syntax.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
- agent/bootstrap/README.md
