Mission: Fix Portable Recovery Import and Repository Root Resolution

Goal

Fix the final two production issues identified by the strict portable recovery test suite.

Modify only:

- agent/bootstrap/restore_manager.py
- agent/bootstrap/bootstrap.sh

Do not modify tests.
Do not modify env.example.
Do not modify project.example.json.
Do not modify README.
Do not add dependencies.
Do not modify requirements.txt.
Use Python standard library only.
All existing unittest tests must pass.

1. Restore Manager Import Compatibility

agent/bootstrap/restore_manager.py must be safely importable both through normal Python package import and through a direct importlib module-spec execution pattern.

The module must work when a caller performs the equivalent of:

- create a module spec from the file
- create a module from the spec
- execute the module through the spec loader

without assuming that the caller manually inserted the module object into sys.modules before exec_module.

Current failure occurs during dataclass processing because dataclasses attempts to resolve annotation context through sys.modules and the dynamically executed module is not present there.

Fix the production module itself.

Requirements:

- Preserve the existing public API.
- Preserve existing dataclass semantics where practical.
- Preserve frozen/immutable result/config types where currently intended.
- Do not require callers to modify sys.modules manually.
- Do not introduce dynamic imports.
- Do not mutate global import state as a workaround.
- Do not insert the current module into sys.modules from inside the module.
- Do not monkey-patch dataclasses.
- Do not catch and hide import errors.

Preferred compatibility strategy:

- Avoid dataclass annotation processing that requires resolving the module through sys.modules during class creation.
- If the module currently uses postponed/string annotations through `from __future__ import annotations`, remove or restructure that dependency where safe so dataclass field annotations are concrete runtime types.
- Use Python 3.12-compatible explicit typing that remains safe under direct spec-loader execution.
- Ensure all referenced annotation types are defined/imported before dataclass declarations.
- Preserve serialization, validation, equality, immutability, and existing interfaces.

The resulting module must import successfully through:

- normal `import agent.bootstrap.restore_manager`
- direct module-spec execution by validation tooling

Do not change business behavior merely to satisfy import mechanics.

2. Repository Root Resolution

agent/bootstrap/bootstrap.sh must determine the repository root from the physical location of bootstrap.sh, not from the caller's current working directory.

Use a conventional statically recognizable pattern equivalent to:

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

The repository layout is:

<repo-root>/agent/bootstrap/bootstrap.sh

Therefore `${SCRIPT_DIR}/../..` must resolve to the repository root.

Requirements:

- Define SCRIPT_DIR.
- Define REPO_ROOT.
- Resolve both to absolute paths.
- Do not assume the script is launched from repository root.
- Do not depend on `pwd` from the caller.
- Quote all path expansions safely.
- Preserve symlink/path safety where existing behavior supports it.
- Use REPO_ROOT as the basis for repository-relative paths.

3. Bootstrap Safety

Preserve this exact strict-mode line near the beginning:

set -Eeuo pipefail

Preserve existing:

- Python 3.12 compatibility validation
- virtualenv creation/validation
- placeholder-only configuration behavior
- clean-checkout operation
- deterministic exit codes
- provider neutrality
- platform neutrality

Do not:

- use eval
- use curl-pipe-shell
- install OS packages
- modify DNS
- modify firewall
- configure Nginx
- enable/start systemd
- deploy production automatically
- echo protected configuration values

4. Restore Manager Safety

Do not:

- use subprocess
- use os.system
- use eval
- use exec
- use compile
- use dynamic imports
- make network calls
- execute Git
- perform deployment actions
- weaken path validation
- weaken project isolation
- persist protected configuration

5. Regression Compatibility

The fixes must not alter unrelated behavior.

All existing tests must continue to pass.

The generated Python must pass py_compile.

The shell script must remain valid Bash.

Deliverables

- agent/bootstrap/restore_manager.py
- agent/bootstrap/bootstrap.sh
