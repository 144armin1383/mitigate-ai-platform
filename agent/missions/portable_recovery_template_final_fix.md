Mission: Final Fix for Portable Recovery Templates

Goal

Fix the final five compatibility gaps identified by the strict portable recovery test suite.

Modify only:

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json

Do not modify tests.
Do not modify Python production modules.
Do not modify README.
Do not add dependencies.
Do not modify requirements.txt.
Do not weaken security or portability requirements.
All existing unittest tests must pass.

1. Bootstrap Python and Virtualenv Contract

agent/bootstrap/bootstrap.sh must explicitly and statically demonstrate that it:

- verifies a Python interpreter is available
- requires Python 3.12-compatible execution
- creates agent/.venv when missing
- validates agent/.venv when already present
- validates the virtualenv Python executable

Use standard recognizable shell commands/patterns including:

command -v python3.12
python3.12 -m venv
agent/.venv
bin/python

Preserve:

set -Eeuo pipefail

Do not perform network installation.
Do not use curl-pipe-shell.
Do not automatically install operating-system packages.
Do not print protected configuration values.
Do not activate systemd.
Do not deploy production.

The script must be safe and useful on a clean checkout.

2. Environment Template Required Semantic Contract

agent/bootstrap/env.example must preserve placeholder-only values.

It must explicitly include these MITIGATE_AI variables:

MITIGATE_AI_ENVIRONMENT_NAME="<ENVIRONMENT>"
MITIGATE_AI_DEFAULT_PROJECT_ID="<PROJECT_ID>"
MITIGATE_AI_REPOSITORY_ROOT="<REPOSITORY_ROOT>"
MITIGATE_AI_DATA_ROOT="<DATA_ROOT>"
MITIGATE_AI_MEMORY_ROOT="<MEMORY_ROOT>"
MITIGATE_AI_PROVIDER="<PROVIDER>"
MITIGATE_AI_PROVIDER_API_KEY="<PROVIDER_API_KEY>"
MITIGATE_AI_PROVIDER_BASE_URL="<PROVIDER_BASE_URL>"
MITIGATE_AI_PROVIDER_MODEL="<PROVIDER_MODEL>"
MITIGATE_AI_SITE_ADAPTER="<SITE_ADAPTER>"
MITIGATE_AI_RUNTIME_HOST="<RUNTIME_HOST>"
MITIGATE_AI_RUNTIME_PORT="<RUNTIME_PORT>"
MITIGATE_AI_API_TOKEN="<API_TOKEN>"

Also preserve any generic compatibility variables already intentionally present.

Rules:

- Every committed value must remain an obvious placeholder.
- Do not use operational defaults.
- Do not use dev, default, local, generic, localhost, 127.0.0.1, 8080, staging, or production as assigned values.
- Do not include real access material.
- Do not remove required existing placeholder fields.

3. Project Example Canonical Contract

agent/bootstrap/project.example.json must be a canonical provider-neutral project template.

It must contain these top-level fields exactly:

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

Additional safe fields may remain only when they do not conflict with this canonical contract.

4. Project Template Values

Use safe illustrative values that demonstrate structure without embedding protected configuration.

Required shape:

- project_id: non-empty example identifier
- project_name: non-empty example name
- repository: example repository location
- default_branch: "main"
- site_type: a valid neutral/example type accepted by the platform
- cms_type: neutral or appropriate example
- adapter: provider-neutral/site-adapter configuration object
- canonical_url: example URL
- allowed_paths: safe relative/project scope examples as expected by the existing project contract
- denied_paths: safe examples
- environment: non-sensitive environment configuration structure
- feature flags: booleans
- metadata: safe neutral metadata only

5. Supported Site Types

The template must clearly support or represent:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

If profiles/adapters are used, preserve these supported profiles.

The top-level site_type must itself be either:

- a recognized example site type
or
- a clearly neutral value accepted by the existing platform contract.

Prefer a recognized generic portable example if supported by production behavior.

Do not invent a site_type value that existing validators reject.

6. Clean Checkout Contract

A parser loading project.example.json from a clean checkout must immediately find:

project_id

at the top level.

Do not substitute:

default_project_id

for project_id.

If backward compatibility requires default_project_id elsewhere, it may coexist only if safe, but project_id remains mandatory.

7. Project Template Safety

The serialized project.example.json must not contain credential-like or protected-access terminology prohibited by the recovery contract.

Avoid these terms entirely in keys and descriptive strings:

- secret
- secrets
- password
- token
- credential
- credentials
- api_key
- private_key
- authorization

Use neutral wording such as:

- external runtime configuration
- protected runtime configuration
- provider access configuration supplied externally

Do not embed actual access values.

8. Preserve Portability

The result must continue supporting:

- clean GitHub checkout
- fresh server reconstruction
- provider migration
- site platform migration
- WordPress adapters
- Lovable adapters
- React adapters
- Next.js adapters
- static sites
- PHP sites
- generic Git projects
- custom adapters

No source-code rewriting should be required for normal deployment migration.

9. Validation

All generated assets must remain syntactically valid.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
