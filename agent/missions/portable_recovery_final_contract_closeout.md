Mission: Final Portable Recovery Contract Closeout

Goal

Resolve the final five portable recovery compatibility failures and close the strict portable recovery suite without modifying tests.

Modify only:

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/bootstrap/README.md
- agent/bootstrap/project.example.json
- agent/bootstrap/portable_bootstrap.py

Do not modify tests.
Do not modify restore_manager.py.
Do not modify requirements.txt.
Do not add dependencies.
Use Python standard library only.
All existing unittest tests must pass.

1. Bootstrap Repository Root Resolution

agent/bootstrap/bootstrap.sh must resolve repository root from the location of the script itself.

The strict recovery test expects a recognizable dirname "$0" pattern.

Use an implementation equivalent to:

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

Requirements:

- preserve set -Eeuo pipefail
- do not use git rev-parse
- do not depend on caller working directory
- use REPO_ROOT for repository-relative paths
- quote paths safely
- preserve Python and virtualenv validation
- no direct Git execution
- no deployment execution

2. Environment Compatibility Aliases

agent/bootstrap/env.example must preserve existing variables and also include these exact compatibility variable names with placeholder-only values:

ENV="<ENV>"
PROJECT="<PROJECT>"
MITIGATE_REPO_ROOT="<MITIGATE_REPO_ROOT>"
AGENT_DATA_ROOT="<AGENT_DATA_ROOT>"
AGENT_MEMORY_ROOT="<AGENT_MEMORY_ROOT>"
ADAPTER="<SITE_ADAPTER>"
BIND_HOST="<BIND_HOST>"
BIND_PORT="<BIND_PORT>"
AGENT_TOKEN="<PLACEHOLDER>"

Also preserve existing generic and MITIGATE_AI-prefixed fields.

All values must remain non-operational placeholders.

Do not add real values.
Do not add provider-specific access variables.
Do not add inline comments after assignments.

3. README Site Adapter Contract

agent/bootstrap/README.md must explicitly contain and explain the exact phrase:

site adapter

Add a useful paragraph explaining that the site adapter selects the platform integration while the autonomous core remains unchanged.

It must mention examples including:

- WordPress
- Lovable
- React
- Next.js
- PHP
- Generic Git
- custom

Do not remove existing recovery, source-of-truth, migration, backup, security, or external-secret documentation.

4. Project Template Supported Site Types

agent/bootstrap/project.example.json must preserve all existing canonical top-level fields.

Add a safe top-level array:

"supported_site_types": [
  "wordpress",
  "lovable",
  "react",
  "nextjs",
  "static",
  "php",
  "generic_git",
  "custom"
]

Do not replace the existing site_type field.

Preserve:

"adapter": "<SITE_ADAPTER>"

as a configurable string.

Do not embed authentication values.

The file must remain valid JSON.

5. Required Directory Validation

agent/bootstrap/portable_bootstrap.py must reject a repository layout that is missing required directories.

Required repository directories must include at minimum the critical platform directories already expected by the portable recovery contract, such as:

- agent
- agent/bootstrap
- agent/ai
- agent/runtime
- agent/api
- agent/orchestrator
- agent/autonomy
- agent/memory
- agent/operations
- agent/missions
- agent/tests
- agent/deploy

When a required directory is missing, validation must raise a safe exception such as:

FileNotFoundError

or ValueError with a clear safe message.

Do not silently return success for a structurally incomplete repository.

However:

- placeholder configuration on a structurally valid repository may still return configuration-required state
- missing external runtime configuration must not be treated the same as missing repository structure

Preserve clean-checkout semantics:

valid repository + placeholders
=
safe configuration-required/validation-ready state

missing required repository directory
=
exception / structural validation failure

6. Safety

Do not use:

- subprocess
- os.system
- eval
- exec
- compile
- dynamic imports
- network calls
- direct Git execution
- deployment execution

Do not weaken:

- path validation
- project isolation
- provider neutrality
- platform neutrality
- clean-checkout recovery behavior

7. Regression

All existing unittest tests must pass.

All generated Python must pass py_compile.

bootstrap.sh must remain valid Bash.

project.example.json must parse successfully.

env.example must remain KEY="VALUE" syntax.

Deliverables

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/env.example
- agent/bootstrap/README.md
- agent/bootstrap/project.example.json
- agent/bootstrap/portable_bootstrap.py
