Mission: Final Portable Recovery Package and Environment Fix

Goal

Fix the final seven strict portable recovery compatibility failures.

Modify or create only:

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/runtime/__init__.py
- agent/autonomy/__init__.py
- agent/memory/__init__.py
- agent/operations/__init__.py

Do not modify tests.
Do not modify unrelated production modules.
Do not add dependencies.
Do not modify requirements.txt.
All existing unittest tests must pass.

1. Explicit Python Package Contract

Create these files if they do not already exist:

- agent/runtime/__init__.py
- agent/autonomy/__init__.py
- agent/memory/__init__.py
- agent/operations/__init__.py

Each file must:

- be valid Python
- be minimal
- contain no side effects
- perform no imports unless strictly necessary
- execute no code at import time
- preserve existing namespace/module behavior
- make the directory an explicit Python package

A simple package docstring is sufficient.

2. Bootstrap Shell Strict Mode

agent/bootstrap/bootstrap.sh must contain this exact literal line near the beginning of the script:

set -Eeuo pipefail

Do not split strict-mode flags across multiple commands.

Preserve all existing safe bootstrap behavior.

The script must also explicitly verify Python and virtualenv support.

It must visibly contain and use recognizable patterns equivalent to:

command -v python3.12
python3.12 -m venv
agent/.venv
bin/python

It may safely fall back to another Python 3 interpreter only after validating Python 3.12 compatibility.

The script must:

- verify a Python interpreter exists
- verify Python is 3.12-compatible
- create agent/.venv if absent
- validate agent/.venv if present
- verify agent/.venv/bin/python is executable

Do not:

- install OS packages
- use curl-pipe-shell
- use eval
- echo protected configuration values
- activate systemd
- modify DNS
- modify firewall
- deploy production automatically

3. Environment Template Canonical Fields

agent/bootstrap/env.example must contain these exact variable names with placeholder-only values:

ENVIRONMENT="<ENVIRONMENT>"
PROJECT_ID="<PROJECT_ID>"
REPOSITORY_ROOT="<REPOSITORY_ROOT>"
DATA_ROOT="<DATA_ROOT>"
MEMORY_ROOT="<MEMORY_ROOT>"
PROVIDER="<PROVIDER>"
PROVIDER_API_KEY="<PROVIDER_API_KEY>"
PROVIDER_BASE_URL="<PROVIDER_BASE_URL>"
PROVIDER_MODEL="<PROVIDER_MODEL>"
SITE_ADAPTER="<SITE_ADAPTER>"
RUNTIME_HOST="<RUNTIME_HOST>"
RUNTIME_PORT="<RUNTIME_PORT>"
API_TOKEN="<API_TOKEN>"

It must also contain these MITIGATE_AI-prefixed compatibility variables:

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

Both generic variables and MITIGATE_AI-prefixed variables are intentional compatibility aliases.

4. Environment Placeholder Safety

Every assigned value in the committed env.example must remain an obvious non-operational placeholder.

Do not assign:

- dev
- default
- local
- generic
- localhost
- 127.0.0.1
- 8080
- staging
- production

Do not include real protected-access values.

Do not use shell variable expansion as the assigned placeholder value.

5. Provider Identifier Documentation in Template

env.example must explicitly document, in safe comment text, that provider adapter identifiers may include:

- openai
- anthropic
- gemini
- local
- custom

These are identifiers only.

Do not include provider access values.

Example safe comment:

# Provider adapter examples: openai, anthropic, gemini, local, custom

6. Package Portability

Explicit __init__.py files must allow clean-checkout tooling to recognize:

- agent.runtime
- agent.autonomy
- agent.memory
- agent.operations

as standard Python packages on a new server.

Do not alter the public APIs of existing modules.

7. Security

Do not weaken:

- secret detection
- path validation
- provider neutrality
- platform neutrality
- clean-checkout recovery behavior

No dynamic imports.
No dynamic code execution.
No os.system.
No subprocess in production Python.
No direct Git operations from production Python.

8. Validation

All generated Python must pass py_compile.

bootstrap.sh must remain syntactically valid Bash.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/runtime/__init__.py
- agent/autonomy/__init__.py
- agent/memory/__init__.py
- agent/operations/__init__.py
