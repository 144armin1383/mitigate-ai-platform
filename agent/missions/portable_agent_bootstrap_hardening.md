Mission: Harden Portable Agent Bootstrap Configuration

Goal

Harden the existing portable bootstrap assets so they strictly satisfy the portable clean-recovery contract.

Modify only:

- agent/bootstrap/env.example
- agent/bootstrap/bootstrap.sh

Do not modify any other production file.
Do not generate tests in this mission.
Do not add dependencies.
Do not modify requirements.txt.
All existing unittest tests must continue to pass.

Environment Template Contract

agent/bootstrap/env.example must be a true template.

Every configurable value must use an obvious placeholder rather than an operational default.

Use explicit placeholder values such as:

MITIGATE_AI_ENVIRONMENT_NAME="<ENVIRONMENT_NAME>"
MITIGATE_AI_DEFAULT_PROJECT_ID="<DEFAULT_PROJECT_ID>"
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

Rules:

- Do not use real operational defaults such as dev, default, local, generic, 127.0.0.1, 8080, or server-specific absolute paths as assigned values.
- Do not use shell variable expansion inside template values.
- Do not put inline comments after assigned values.
- Put examples on separate comment lines above the relevant variable.
- All secret-like fields must contain placeholders only.
- No real API key, token, password, credential, private key, or environment-specific value may appear.
- The file must be safe to commit publicly from a secret-handling perspective.
- Documentation comments may describe configuration but must never contain real secret material.

Bootstrap Script Console Safety

agent/bootstrap/bootstrap.sh must never print credential-like or secret-related values.

Console output must not contain lines that combine echo/printf output with sensitive terms such as:

- key
- token
- secret
- password
- credential
- private key
- authorization

This applies even when the line is only informational.

Replace messages such as:

"update with real secrets outside git"

with neutral wording such as:

"Review and update the local configuration outside version control before first use."

The script may internally reference environment variable names when required for operation, but it must never echo their values.

Bootstrap Behavior

Preserve all existing safe bootstrap behavior:

- bash strict mode
- repository-root resolution
- Python compatibility validation
- virtual environment creation or validation
- local directory creation
- non-destructive local configuration creation
- no overwrite of an existing local environment file
- no network bootstrap
- no curl-pipe-shell
- no DNS changes
- no firewall changes
- no Nginx changes
- no systemd activation
- no production deployment
- deterministic exit codes
- no credential output

Template and Runtime Separation

The committed env.example is documentation and bootstrap input only.

Operational defaults, when needed internally by application code, must remain separate from the committed template.

Do not weaken runtime validation merely to support placeholders.

Portability

The result must remain:

- provider-neutral
- server-neutral
- CMS-neutral
- WordPress-compatible through adapters
- Lovable-compatible through adapters
- React/Next.js-compatible through adapters
- generic Git-project compatible through adapters

Generated File Safety

- Do not use eval.
- Do not use dynamic code execution.
- Do not introduce remote downloads.
- Do not introduce real credentials.
- Shell syntax must remain valid.
- All existing unittest tests must pass.

Deliverables

- agent/bootstrap/env.example
- agent/bootstrap/bootstrap.sh
