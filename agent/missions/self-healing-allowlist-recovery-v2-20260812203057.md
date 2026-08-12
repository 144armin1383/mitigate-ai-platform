# MITIGATE Allowlist-Aware Self-Healing V2

Mission ID: self-healing-allowlist-recovery-v2-20260812203057
Request ID: self-healing-allowlist-recovery-v2-20260812203057
Task Type: backend

## Objective

Implement a PURE, SIDE-EFFECT-FREE native contract that helps an autonomous
repair attempt recover when generated output proposes repository paths that
are not included in the mission's declared deliverables.

This component does NOT manage an allowlist file.

It does NOT add anything to an allowlist.

It does NOT write any policy/configuration file.

It only compares:

1. declared allowed deliverable paths
2. proposed generated paths
3. protected repository paths

and returns deterministic structured recovery guidance.

## Previous Incorrect Attempt

The previous attempt incorrectly implemented an AllowlistRecovery class that:

- read an allowlist file
- added tokens
- wrote the allowlist
- created backups
- broadened the allowlist from events

That design is REJECTED.

Do not reuse that behavior.

Do not copy that implementation.

## Exact Deliverables

Generate exactly and only:

agent/repair/allowlist_recovery.py
agent/tests/test_allowlist_recovery.py
docs/architecture/autonomous-self-healing-allowlist-recovery-v2.json

No other generated files are permitted.

## Mandatory Purity Rules

agent/repair/allowlist_recovery.py MUST NOT:

- open files for writing
- write files
- modify files
- create files
- delete files
- rename files
- create backups
- call os.replace
- call shutil
- call tempfile
- mutate Git
- mutate MissionQueue
- mutate runtime state
- modify an allowlist
- append to an allowlist
- expand an allowlist
- install packages
- perform network calls
- execute generated code
- call subprocess
- call shell commands

The implementation must operate entirely on values passed by the caller.

## Required Public Contract

Implement a deterministic provider-independent API equivalent in purpose to:

class PathRecoveryDecision

and a function equivalent in purpose to:

classify_generated_path(
    generated_path,
    allowed_paths,
    protected_paths=(),
    previous_rejected_paths=(),
)

Exact naming may vary only if repository conventions strongly justify it.

The returned structured result must contain at minimum:

- normalized_path
- classification
- allowed
- safely_repairable
- human_approval_required
- repeated_invalid_path
- allowed_paths
- recovery_instruction
- fingerprint

## Required Classifications

Support at minimum:

- allowed
- outside_allowlist
- repository_escape
- absolute_path
- protected_core
- malformed_path
- repeated_invalid_path

## Path Safety Rules

Reject:

- absolute paths
- ../ traversal
- repository escape
- undeclared paths
- protected Core paths
- empty/malformed paths

Do not normalize an unsafe path into an allowed path.

Do not silently rewrite:

mitigate/autonomy/example.py

into:

agent/repair/example.py

Instead classify it as outside_allowlist and return recovery guidance telling
the next generation attempt to regenerate using only the exact declared
deliverables.

## Recovery Guidance

For an ordinary outside_allowlist result:

allowed = false
safely_repairable = true
human_approval_required = false

The recovery instruction must explicitly communicate:

- the rejected path
- the exact allowed paths
- no new paths may be created
- the next generation response must use only declared deliverables

For protected Core, repository escape, or dangerous malformed path:

allowed = false

and fail closed.

Human approval should be required where protected Core is the requested
target.

## Repeated Repair Detection

Use deterministic fingerprints.

If the same or equivalent invalid path is proposed again across attempts,
set:

repeated_invalid_path = true

This allows the outer bounded repair system to avoid repeating ineffective
repairs indefinitely.

Do not maintain global mutable state.

Previous rejected paths/history must be provided explicitly by the caller.

## Determinism

Same inputs must produce the same result.

Ordering of allowed paths must be canonical.

Output must be JSON serializable.

Inputs must not be mutated.

No timestamps or random values in deterministic classification output.

## Protected Core

Inspect repository protection rules read-only.

Do not modify:

agent/ai/mission_runner.py
agent/ai/autonomous_controller.py
agent/runtime/background_worker.py
agent/runtime/mission_queue.py
systemd configuration
repository guardrails

Do not weaken CORE_PATH_LOCKED.

## Operational Integration Analysis

Inspect the existing repair/validation architecture read-only.

Determine how this pure component could later be passed into the existing
repair loop so that a generated-path validation failure can produce useful
repair evidence.

Do NOT wire it operationally in this mission.

If operational wiring requires protected Core modification, report the exact
smallest target but do not perform it.

## Tests

Use Python standard-library unittest only.

Cover at minimum:

- declared path allowed
- undeclared path rejected
- mitigate/autonomy path rejected
- mitigate/self_healing path rejected
- absolute path rejected
- ../ traversal rejected
- protected Core target rejected
- empty path rejected
- malformed path rejected
- repeated invalid path detected
- deterministic fingerprint
- deterministic canonical allowed-path ordering
- input list not mutated
- output JSON serializable
- ordinary mismatch marked safely repairable
- ordinary mismatch does not require human approval
- protected Core requires human approval
- no implicit allowlist expansion
- no filesystem write APIs
- no subprocess
- no network behavior
- no Git mutation
- no MissionQueue mutation

Tests should explicitly verify that the production component imports none of:

tempfile
shutil
subprocess
requests
httpx
aiohttp

and does not call:

open(... write mode ...)
Path.write_text
Path.write_bytes
os.replace
os.rename
os.remove
os.unlink

## Validation

Run:

python -m py_compile     agent/repair/allowlist_recovery.py     agent/tests/test_allowlist_recovery.py

Run targeted tests.

Run the full repository suite:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Run:

git diff --check

No existing production file may be modified.

## Report

Create exactly:

docs/architecture/autonomous-self-healing-allowlist-recovery-v2.json

Required fields:

- mission_id
- root_cause
- implementation_status
- component_path
- component_is_pure
- filesystem_writes
- allowlist_mutation
- allowlist_expansion
- failure_classifications
- repeated_failure_detection
- deterministic_recovery_guidance
- core_protection_weakened
- production_runtime_data_changed
- provider_independence
- external_runtime_dependency
- full_test_result
- operational_extension_point_found
- operational_extension_point
- operational_wiring_completed
- core_change_required
- exact_core_change_target
- core_change_reason
- remaining_work

Required values:

component_is_pure = true
filesystem_writes = false
allowlist_mutation = false
allowlist_expansion = false
core_protection_weakened = false
production_runtime_data_changed = false
provider_independence = true
external_runtime_dependency = false
operational_wiring_completed = false

## Success Criteria

MITIGATE gains a pure allowlist-aware recovery decision contract capable of
telling autonomous repair attempts WHY a generated path was rejected and HOW
to regenerate within the existing mission deliverables.

The existing allowlist and Core protection remain completely unchanged.

## Deliverables

agent/repair/allowlist_recovery.py
agent/tests/test_allowlist_recovery.py
docs/architecture/autonomous-self-healing-allowlist-recovery-v2.json

## Git

Use the Mission Runner branch.

Commit only validated output.

Push the Agent branch.

Do not modify main directly.

Never force push.
