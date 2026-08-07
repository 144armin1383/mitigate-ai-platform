Mission: Fix Portable Recovery External Secret Documentation

Goal

Resolve the final env.example documentation mismatch identified by the strict portable recovery suite.

Modify only:

- agent/bootstrap/env.example

Do not modify tests.
Do not modify Python code.
Do not modify shell scripts.
Do not modify project.example.json.
Do not modify README.
Do not add dependencies.
All existing unittest tests must pass.

Requirements

agent/bootstrap/env.example must explicitly document that protected runtime values and secrets remain external to Git.

Add clear comment text near the top of env.example containing the exact concepts:

- secrets remain external to Git
- protected runtime values are supplied externally
- real access values must never be committed
- the committed file contains placeholders only

Use safe documentation wording only.

Do not add any real values.

Do not change the existing placeholder assignments unless required for syntax preservation.

Preserve all existing generic and MITIGATE_AI-prefixed compatibility variables.

The file must remain simple KEY="VALUE" template syntax with comments.

All sensitive assignments must remain neutral placeholders.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/env.example

Provider-Neutral Environment Requirement

The generated env.example must remain strictly provider-neutral.

Do not add provider-specific environment variable names.

In particular, do not add environment assignments for specific AI providers.

Do not add or generate provider-specific access-key variable assignments.

Use only the existing generic portable variables:

PROVIDER="<PROVIDER>"
PROVIDER_API_KEY="<PLACEHOLDER>"
PROVIDER_BASE_URL="<PROVIDER_BASE_URL>"
PROVIDER_MODEL="<PROVIDER_MODEL>"

and the existing MITIGATE_AI-prefixed generic equivalents.

Provider-specific identifiers may appear only in safe explanatory comments where needed, but provider-specific authentication variable names must not be introduced.

External Secret Documentation

Add plain comment text near the top of env.example stating:

# Secrets remain external to Git.
# Protected runtime values are supplied externally.
# Real access values must never be committed.
# This committed template contains placeholders only.

These comments document the security boundary without adding provider-specific access fields.

Do not change existing placeholder assignments except where required to preserve the generic provider-neutral contract.

The generated env.example must pass Mission Runner forbidden-content validation.
