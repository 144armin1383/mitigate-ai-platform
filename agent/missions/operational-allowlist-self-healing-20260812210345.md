# MITIGATE Operational Allowlist Self-Healing

Mission ID: operational-allowlist-self-healing-20260812210345
Request ID: operational-allowlist-self-healing-20260812210345
Task Type: backend

## Objective

Implement the approved non-Core operational Self-Healing architecture for
generated-path allowlist failures.

The purpose is to allow autonomous engineering missions to diagnose and
repair safely recoverable generated-path mistakes without routine human
intervention.

This implementation MUST preserve all existing infrastructure protection.

## Approved Architecture

The approved architecture report is:

docs/architecture/allowlist-self-healing-core-change-proposal.json

Its conclusions are authoritative for this mission.

Confirmed:

- architecture_observation_confirmed = true
- gap_confirmed = true
- core_change_required = false
- allowlist_mutation = false
- allowlist_expansion = false
- core_protection_weakened = false
- provider_independence = true
- external_runtime_dependency = false
- production_runtime_data_changed = false

## Existing Components

Inspect and reuse:

- agent/repair/integration.py
- agent/repair/failure_capture.py
- agent/repair/mission_adapter.py
- agent/repair/repair_loop.py
- agent/repair/allowlist_recovery.py
- agent/ai/mission_runner.py

The existing validator remains authoritative.

Do not replace it.

## Required Operational Behavior

When generated output proposes a repository path rejected by the existing
generated-file validator:

1. Preserve the original rejection.
2. Capture only the precise path-policy failure.
3. Extract the rejected path safely.
4. Classify it using the existing allowlist recovery classifier.
5. Produce bounded structured repair evidence.
6. Feed that evidence into the EXISTING MissionRepairAdapter lifecycle.
7. Preserve the existing repair budget.
8. Preserve retry state.
9. Preserve checkpoint identity.
10. Preserve execution identity.
11. Regenerate the complete deliverable set.
12. Validate the regenerated output again using the existing validator.
13. Continue only when the existing validator accepts the output.
14. Fail closed when recovery is unsafe or budget is exhausted.

## Structured Evidence

The bounded repair context should include, where available:

- rejected_path
- classification
- allowed_paths
- safely_repairable
- human_approval_required
- repeated_invalid_path
- fingerprint
- recovery_instruction

Do not expose secrets.

Do not add the rejected path to allowed_paths.

## Safely Recoverable Case

For an ordinary generated path outside declared deliverables:

- classify deterministically
- provide exact declared deliverables
- provide rejected path as diagnostic evidence only
- instruct the next generation to regenerate using ONLY declared deliverables
- consume the existing bounded repair attempt
- validate again

Human intervention should NOT be required merely because the model proposed
an undeclared but otherwise non-protected repository-relative path.

## Unsafe Cases

Fail closed for unsafe cases including:

- protected Core target
- repository escape
- absolute path
- traversal
- malformed path
- unsafe repeated ineffective repair
- any case classified as human approval required

Do not silently repair these.

## Repeated Invalid Path

Use the deterministic fingerprint from allowlist recovery.

If equivalent invalid output repeats:

- mark repeated_invalid_path
- do not reset repair budget
- do not create another retry authority
- consume the existing bounded budget
- fail closed when exhausted

## Existing Authority Must Remain

Path validation authority:

existing generated-file validator

File writing authority:

existing write_generated_files path

Retry authority:

existing MissionRepairAdapter / repair_loop

Repair budget authority:

existing MissionRepairAdapter / repair_loop

Checkpoint authority:

existing checkpoint lifecycle

Execution authority:

existing mission execution lifecycle

Audit authority:

existing mission logging / failure capture

No duplicate authority is permitted.

## Self-Diagnosis Requirement

During implementation and validation, if a test or generated implementation
fails for a safely repairable non-Core reason:

- diagnose the failure
- repair within the declared deliverables
- rerun targeted validation
- rerun required regression validation

Do not stop merely because the first implementation attempt fails.

However:

- do not bypass guardrails
- do not broaden deliverables
- do not modify protected Core
- do not mutate infrastructure policy
- do not disable tests
- do not weaken assertions
- do not hide failures
- do not reset retry budgets

If safe autonomous repair is impossible, fail closed with a precise report.

## Core Protection

The following are FORBIDDEN modifications:

- agent/ai/mission_runner.py
- protected Core policy files
- generated-file validator authority
- Core path locks
- infrastructure safety policy
- production secrets
- production credentials

Do not modify protected Core.

If implementation unexpectedly requires Core modification:

STOP.

Report:

CORE_CHANGE_REQUIRED=true

and identify the exact target.

Do not perform the Core modification.

## Allowlist Protection

The implementation MUST NOT:

- mutate allowlists
- expand allowlists
- automatically add rejected paths
- broaden mission deliverables
- rewrite an invalid path into a valid path silently
- bypass validate_generated_file
- bypass write_generated_files validation

## Provider Independence

No provider-specific behavior.

No mandatory external runtime.

No Ruflo runtime dependency.

The implementation must remain native and provider-independent.

## Implementation Scope

Prefer minimal changes within existing non-Core repair components.

Expected implementation areas from the approved proposal:

- agent/repair/integration.py
- agent/repair/failure_capture.py
- agent/repair/mission_adapter.py
- agent/repair/repair_loop.py
- agent/repair/allowlist_recovery.py

Modify only files actually required.

## Required Tests

Add or update tests proving:

1. outside-allowlist generated path enters bounded recovery
2. next attempt receives exact original deliverables
3. rejected path is diagnostic only
4. allowlist is not expanded
5. deliverables are not mutated
6. valid generated path follows existing behavior unchanged
7. protected Core path fails closed
8. traversal fails closed
9. repository escape fails closed
10. absolute path fails closed
11. repeated invalid path produces stable fingerprint
12. repeated ineffective repair consumes existing budget
13. repair budget never resets
14. no duplicate retry counter is introduced
15. validator remains authoritative
16. file writing remains validator-gated
17. existing unittest Self-Healing still works
18. existing compilation Self-Healing still works
19. checkpoint identity is preserved
20. idempotent execution is preserved
21. provider independence is preserved
22. no external runtime dependency is introduced
23. no production runtime data changes
24. structured evidence is JSON serializable
25. full existing test suite passes

## Validation

Run targeted tests first.

Then run:

python -m unittest discover -s agent/tests -v

Run:

git diff --check

Strictly parse all created JSON using standard json.loads.

Do not treat test success alone as sufficient.

Verify final changed-file scope.

Verify protected Core unchanged.

Verify validator authority unchanged.

Verify allowlist mutation absent.

Verify allowlist expansion absent.

## Report

Create exactly:

docs/architecture/operational-allowlist-self-healing.json

The report must include:

- mission_id
- implementation_completed
- architecture_proposal_followed
- intercepted_failure_type
- exact_interception_location
- classifier_reused
- structured_evidence_operational
- bounded_retry_operational
- repeated_failure_detection_operational
- validator_authority_preserved
- file_write_authority_preserved
- retry_authority_preserved
- repair_budget_preserved
- checkpoint_identity_preserved
- execution_identity_preserved
- idempotent_execution_preserved
- allowlist_mutation
- allowlist_expansion
- deliverables_mutation
- silent_path_remapping
- core_modified
- core_protection_weakened
- provider_independence
- external_runtime_dependency
- production_runtime_data_changed
- targeted_tests_passed
- full_test_suite_passed
- diff_check_passed
- rollback_plan
- remaining_work

Required final values for successful implementation:

implementation_completed = true
architecture_proposal_followed = true
structured_evidence_operational = true
bounded_retry_operational = true
repeated_failure_detection_operational = true
validator_authority_preserved = true
file_write_authority_preserved = true
retry_authority_preserved = true
repair_budget_preserved = true
checkpoint_identity_preserved = true
execution_identity_preserved = true
idempotent_execution_preserved = true
allowlist_mutation = false
allowlist_expansion = false
deliverables_mutation = false
silent_path_remapping = false
core_modified = false
core_protection_weakened = false
provider_independence = true
external_runtime_dependency = false
production_runtime_data_changed = false
targeted_tests_passed = true
full_test_suite_passed = true
diff_check_passed = true

## Deliverables

agent/repair/integration.py
agent/repair/failure_capture.py
agent/repair/mission_adapter.py
agent/repair/repair_loop.py
agent/repair/allowlist_recovery.py
agent/tests/test_operational_allowlist_self_healing.py
docs/architecture/operational-allowlist-self-healing.json

## Deliverable Discipline

Not every listed implementation file must change.

The final branch may contain only the subset actually required.

Do not create additional production paths.

Do not create alternate repair engines.

Do not create duplicate controllers.

Do not create new infrastructure services.

## Git

Use the Agent mission branch.

Commit only validated implementation and report.

Push Agent branch.

Do not force push.

Do not merge to main automatically.

Human role after completion is supervision and final merge approval only.
