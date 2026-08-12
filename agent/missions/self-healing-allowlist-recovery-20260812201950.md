# MITIGATE Autonomous Self-Healing Allowlist Recovery Foundation

Mission ID: self-healing-allowlist-recovery-20260812201950
Request ID: self-healing-allowlist-recovery-20260812201950
Task Type: backend

## Objective

Implement a native, deterministic, provider-independent foundation for
recovering autonomous engineering missions from generated-path allowlist
violations.

This mission exists because the previous autonomous self-healing hardening
mission failed three times before validation because generated paths were
outside the mission allowlist.

Observed rejected examples included:

- mitigate/autonomous/self_heal/__init__.py
- mitigate/autonomy/__init__.py
- mitigate/self_healing/__init__.py

The repository guardrail correctly rejected those paths.

DO NOT weaken the guardrail.

## Critical Rule

The Agent MUST generate exactly and only these three deliverables:

1. agent/repair/allowlist_recovery.py
2. agent/tests/test_allowlist_recovery.py
3. docs/architecture/autonomous-self-healing-allowlist-recovery.json

No other generated path is permitted.

Do NOT generate:

- mitigate/
- mitigate/autonomy/
- mitigate/self_healing/
- mitigate/autonomous/
- new package roots
- agent/runtime/
- agent/ai/mission_runner.py
- agent/ai/autonomous_controller.py
- systemd files

Do not invent alternative file locations.

## Existing Architecture To Inspect Read-Only

Inspect the existing implementation and contracts, especially:

- agent/ai/mission_runner.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py
- existing Self-Healing audit components
- existing mission repair adapter
- existing validation engine
- existing retry engine
- MissionQueue semantics
- durable checkpointing
- existing repository protection / Core protection

Read these files to understand contracts.

Do not modify protected Core in this mission.

## Required Native Component

Create:

agent/repair/allowlist_recovery.py

It must provide deterministic provider-neutral primitives for handling a
generated-path policy rejection.

The component must support at minimum:

- exact allowed-path normalization
- generated-path comparison against allowed deliverables
- deterministic classification of path violations
- safe structured diagnostics
- recovery recommendations
- detection of repeated equivalent invalid-path proposals
- bounded history representation
- JSON-serializable outputs
- safe redaction / no secrets
- immutable or non-mutating input behavior

## Required Failure Classification

At minimum distinguish:

- exact_allowed_path
- generated_path_outside_allowlist
- repository_escape_attempt
- protected_core_target
- undeclared_new_deliverable
- repeated_invalid_path
- malformed_generated_path

Do not automatically convert an unsafe path into a different production path.

Do not silently broaden the allowlist.

## Recovery Guidance Contract

For a normal generated-path-outside-allowlist failure, the recovery result
must explicitly tell the next repair/generation attempt:

- the rejected path
- the exact original allowed paths
- that no new path may be added
- that the complete corrected response must use only declared deliverables
- whether the failure is safely repairable
- whether human approval is required

Routine path mismatch should normally be marked safely repairable.

Protected Core or repository escape attempts must fail closed.

## Repeated Failure Detection

If multiple repair attempts propose equivalent invalid paths, the component
must recognize repeated ineffective repair.

It must not permit an infinite loop.

Provide deterministic fingerprinting or equivalent stable comparison.

## Security Rules

Never:

- weaken allowlist checks
- modify allowlists automatically
- permit repository traversal
- permit absolute paths
- permit protected Core through normalization
- suppress the original rejected path
- treat unknown paths as safe
- expose secrets
- execute generated code
- perform network calls
- mutate Git
- mutate MissionQueue
- change production runtime data

## Operational Integration Analysis

Inspect whether the existing repository already exposes a NON-PROTECTED
extension point where this recovery component can later be connected to the
generation/repair lifecycle.

Document the answer in the report.

If safe operational wiring can be achieved without modifying any protected
Core file, describe the exact extension point.

Do NOT modify that extension point in this foundation mission.

If actual operational wiring requires a protected Core change, report:

core_change_required = true

and identify:

- exact file
- exact function/class
- smallest required behavioral change
- why an external helper alone cannot make path-recovery operational
- rollback approach
- safety impact

Do not perform that Core change.

## Tests

Create:

agent/tests/test_allowlist_recovery.py

Use Python standard-library unittest only.

Cover at minimum:

- exact declared path accepted
- undeclared path rejected
- mitigate/autonomy path rejected
- mitigate/self_healing path rejected
- absolute path rejected
- parent traversal rejected
- protected Core target classified safely
- repeated invalid path detected
- deterministic result
- deterministic fingerprint
- allowed-path ordering deterministic
- original inputs not mutated
- output JSON serializable
- no implicit allowlist expansion
- unknown path fails closed
- bounded diagnostic data
- safe repair recommendation for ordinary mismatch
- human escalation for protected Core
- no network behavior
- no Git mutation
- no queue mutation

## Validation

Run:

python -m py_compile   agent/repair/allowlist_recovery.py   agent/tests/test_allowlist_recovery.py

Run targeted unittest coverage.

Then run the entire repository suite:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Run:

git diff --check

No existing production file may be modified.

## Report

Create exactly:

docs/architecture/autonomous-self-healing-allowlist-recovery.json

Required fields:

- mission_id
- root_cause
- implementation_status
- component_path
- test_path
- failure_classifications
- repeated_failure_detection
- deterministic_recovery_guidance
- allowlist_weakened
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
- rollback_plan
- remaining_work

Required invariants:

allowlist_weakened = false
core_protection_weakened = false
production_runtime_data_changed = false
provider_independence = true
external_runtime_dependency = false
operational_wiring_completed = false

## Success Condition

This mission succeeds when MITIGATE has a tested native allowlist-recovery
contract that can diagnose the exact failure class which caused the previous
three autonomous self-healing attempts to fail, without weakening any
repository or Core protection.

The report must then tell the next autonomous mission exactly how this
component can be safely wired into live Self-Healing.

## Deliverables

agent/repair/allowlist_recovery.py
agent/tests/test_allowlist_recovery.py
docs/architecture/autonomous-self-healing-allowlist-recovery.json

## Git

Use the Mission Runner branch.

Commit only validated output.

Push the Agent mission branch.

Do not modify main directly.

Do not force push.
