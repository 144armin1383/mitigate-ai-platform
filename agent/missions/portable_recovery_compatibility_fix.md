Mission: Fix Portable Recovery Compatibility

Goal

Fix all remaining production compatibility issues discovered by the strict portable-agent clean-recovery test suite.

This is a production compatibility mission.

Do not modify the recovery tests.
Do not weaken security checks.
Do not add dependencies.
Do not modify requirements.txt.
Use Python standard library only.
All existing unittest tests must pass.

Modify only:

- agent/bootstrap/portable_bootstrap.py
- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/bootstrap/README.md
- agent/bootstrap/project.example.json

Do not modify unrelated files.

1. BootstrapConfig Portable Alias Compatibility

The public bootstrap configuration must accept both the existing canonical field names and these provider-neutral portable aliases:

- environment
- project_id
- provider
- site_adapter

Map the aliases deterministically to existing canonical fields:

- environment -> environment_name
- project_id -> default_project_id
- provider -> provider_name
- site_adapter -> site_adapter_name

If the production implementation uses a different but equivalent canonical site-adapter field name, map to that existing field without creating duplicate state.

Rules:

- Preserve existing canonical configuration compatibility.
- Alias use must not create duplicate configuration values.
- If both an alias and its canonical field are supplied with conflicting values, reject the configuration with a safe ValueError.
- Unknown fields must still be rejected.
- Do not silently ignore unsupported configuration fields.
- Input mappings must not be mutated.
- Configuration must remain provider-neutral and platform-neutral.

2. Unsafe Path Error Contract

Unsafe repository/bootstrap paths must be rejected with a safe error message containing a recognizable path-safety term.

For path traversal, absolute escape, null-byte, or otherwise unsafe path errors, the safe exception message must contain at least one appropriate term such as:

- unsafe_path
- invalid_path
- unsafe path
- invalid path
- traversal
- null byte

Do not expose unrestricted filesystem details or raw exceptions.

Do not weaken path validation.

3. Bootstrap Shell Strict Mode

agent/bootstrap/bootstrap.sh must contain standard Bash strict mode in a form detectable by static validation.

Use exactly:

set -Eeuo pipefail

near the beginning of the script after the shebang/comments.

Preserve all existing safe behavior.

Do not add eval.
Do not add remote downloads.
Do not add curl-pipe-shell.
Do not print credential values.
Do not perform DNS, firewall, Nginx, systemd activation, or production deployment.

4. Environment Template Compatibility

agent/bootstrap/env.example must remain placeholder-only and safe for Git.

It must contain explicit portable semantic variables for:

ENVIRONMENT="<ENVIRONMENT>"
DATA_ROOT="<DATA_ROOT>"
MEMORY_ROOT="<MEMORY_ROOT>"
PROVIDER_BASE_URL="<PROVIDER_BASE_URL>"
RUNTIME_HOST="<RUNTIME_HOST>"

Also preserve the MITIGATE_AI-prefixed equivalents:

MITIGATE_AI_ENVIRONMENT_NAME="<ENVIRONMENT>"
MITIGATE_AI_DATA_ROOT="<DATA_ROOT>"
MITIGATE_AI_MEMORY_ROOT="<MEMORY_ROOT>"
MITIGATE_AI_PROVIDER_BASE_URL="<PROVIDER_BASE_URL>"
MITIGATE_AI_RUNTIME_HOST="<RUNTIME_HOST>"

Preserve or provide the other required MITIGATE_AI template variables including:

- MITIGATE_AI_DEFAULT_PROJECT_ID
- MITIGATE_AI_REPOSITORY_ROOT
- MITIGATE_AI_PROVIDER
- MITIGATE_AI_PROVIDER_API_KEY
- MITIGATE_AI_PROVIDER_MODEL
- MITIGATE_AI_SITE_ADAPTER
- MITIGATE_AI_RUNTIME_PORT
- MITIGATE_AI_API_TOKEN

Every committed value must be a non-operational placeholder.

Do not assign operational defaults such as:

- dev
- default
- local
- generic
- 127.0.0.1
- 8080
- production
- staging

Do not put real credentials in comments or values.

Generic compatibility variables and MITIGATE_AI-prefixed variables may coexist intentionally.

5. Provider Documentation Compatibility

agent/bootstrap/README.md must explicitly document provider adapter identifiers including these literal terms:

- openai
- anthropic
- gemini
- local
- custom

Document them as adapter identifiers/examples only.

Do not embed credentials.

Explain that changing between these providers uses provider adapters and external runtime configuration without rewriting the autonomous core.

The README must preserve existing documentation for:

- GitHub portable source of truth
- prerequisites
- clean bootstrap
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
- nextjs
- Next.js
- static
- PHP
- generic_git
- custom

Do not replace unittest instructions with pytest.

Where the README currently instructs operators to run repository tests using pytest, correct the documentation to use the repository's existing unittest policy, for example:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Do not introduce pytest as a dependency or requirement.

6. Project Example Credential-Neutral Contract

agent/bootstrap/project.example.json must contain no credential-like or secret-like keys or prose.

The serialized JSON must not contain these terms as keys or descriptive text:

- secret
- secrets
- password
- token
- credential
- credentials
- api_key
- private_key
- authorization

Remove wording such as:

- "do not include secrets"
- "set provider credentials externally"
- "secret manager"

Use neutral non-sensitive wording instead, for example:

- "provider-neutral project configuration template"
- "provider access configuration is supplied externally at runtime"
- "protected runtime configuration is external to this project file"

Do not add credential values.

Do not add credential-reference fields.

Project example must remain safe, portable, provider-neutral, and platform-neutral.

7. Project Template Operational Defaults

The committed project.example.json is a template.

Avoid environment-specific provider defaults where practical.

Adapter/profile examples may identify adapter types, but must not embed authentication or credential information.

Preserve support for:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

8. Portability Contract

The resulting bootstrap system must remain reconstructable from GitHub on a fresh server with:

- repository clone
- bootstrap
- external runtime configuration
- provider adapter selection
- site adapter selection
- safe memory restore
- validation
- runtime startup

No source-code rewrite should be required for normal server, provider, or supported platform migration.

9. Security

Do not weaken:

- secret detection
- path safety
- project isolation
- provider neutrality
- platform neutrality
- clean-checkout behavior

No real credentials.
No realistic credential fixtures.
No raw exceptions.
No dynamic code execution.
No dynamic imports.
No subprocess in production Python.
No os.system.
No shell execution from production Python.
No direct Git execution from production Python.

10. Validation

Every generated Python file must pass py_compile.

Shell syntax must remain valid by design.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/portable_bootstrap.py
- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/bootstrap/README.md
- agent/bootstrap/project.example.json
