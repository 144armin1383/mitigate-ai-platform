Mission: Final Portable Recovery Shell Safety Fix

Goal

Fix the final three portable recovery test failures involving bootstrap shell assets.

Modify only:

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/validate_installation.sh

Do not modify tests.
Do not modify Python production code.
Do not modify env.example.
Do not modify project.example.json.
Do not modify README.
Do not add dependencies.
Do not modify requirements.txt.
All existing unittest tests must pass.

1. bootstrap.sh Python Detection Contract

agent/bootstrap/bootstrap.sh must explicitly contain recognizable Python commands and terminology.

It must:

- preserve this exact strict mode line:

set -Eeuo pipefail

- resolve SCRIPT_DIR from BASH_SOURCE
- resolve REPO_ROOT from SCRIPT_DIR
- detect a Python 3.12-compatible interpreter
- explicitly contain the word python in executable checks
- create or validate agent/.venv
- verify the virtualenv interpreter exists and is executable

Use statically recognizable patterns including:

command -v python3.12
python3.12 -m venv
python
python3
agent/.venv
bin/python

A safe fallback to python3 may be supported only after validating version compatibility.

The script must work regardless of caller working directory.

Repository root must be based on the physical script location.

Use a conventional structure equivalent to:

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

Do not rely on caller pwd for repository root.

2. bootstrap.sh Safety

bootstrap.sh must not:

- execute git
- execute systemctl
- execute deployment tools
- modify DNS
- modify firewall
- modify Nginx
- perform production deployment
- use eval
- use curl-pipe-shell
- install OS packages
- print protected configuration values

It may perform local filesystem setup and Python virtualenv setup only.

3. validate_installation.sh Validation-Only Contract

agent/bootstrap/validate_installation.sh is validation-only.

It must never execute:

- git
- systemctl
- service
- docker
- docker-compose
- kubectl
- helm
- terraform
- ansible
- deploy commands
- production activation commands

Do not invoke these commands even for version or status checks.

If repository validation is required, inspect repository-controlled files and directories using ordinary shell filesystem tests such as:

- test
- [
- -f
- -d
- -x
- find only if already permitted by existing policy

Do not call Git.

4. validate_installation.sh Sensitive-Term Hygiene

The complete textual contents of validate_installation.sh must not contain these literal uppercase or lowercase sensitive configuration terms anywhere, including:

- API_KEY
- TOKEN
- PASSWORD
- SECRET
- api_key
- token
- password
- secret

This restriction applies to:

- variable names
- comments
- echo messages
- grep patterns
- validation lists
- documentation inside the script

Use neutral terminology instead, such as:

- protected configuration
- external configuration
- runtime access configuration
- protected values

Do not weaken actual security boundaries.

The validator does not need to inspect protected-value names directly.

5. validate_installation.sh Required Validation

Preserve safe validation for:

- repository layout
- Python interpreter availability
- Python version compatibility
- virtualenv existence
- virtualenv Python executable
- critical Python package/module presence
- bootstrap configuration file presence
- project template presence
- runtime entrypoint importability where currently supported
- project memory/recovery asset presence
- provider adapter identifier syntax
- site adapter identifier syntax

All validation must remain local and offline.

Do not contact providers.
Do not make network calls.
Do not start services.

6. Repository Root Resolution

validate_installation.sh should also resolve repository root from its own physical location rather than caller working directory.

Use SCRIPT_DIR and REPO_ROOT based on BASH_SOURCE.

The script location is:

<repo-root>/agent/bootstrap/validate_installation.sh

Therefore:

${SCRIPT_DIR}/../..

must resolve to repository root.

7. Shell Safety

Both shell scripts must:

- use bash
- use strict mode
- quote variables safely
- avoid eval
- avoid unsafe interpolation
- use deterministic exit codes
- avoid leaving temporary files
- remain server-neutral
- remain provider-neutral
- remain platform-neutral

8. Portability

The fixes must preserve clean-checkout operation for:

- WordPress
- Lovable-generated projects
- React
- Next.js
- static sites
- PHP
- generic Git-based projects
- custom adapters

No platform-specific behavior belongs in these shell scripts.

9. Validation

Both scripts must remain syntactically valid Bash.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/bootstrap.sh
- agent/bootstrap/validate_installation.sh
