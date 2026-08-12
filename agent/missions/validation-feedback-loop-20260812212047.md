# MITIGATE Autonomous Validation Feedback Loop Hardening

Mission ID: validation-feedback-loop-20260812212047
Request ID: validation-feedback-loop-20260812212047
Task Type: backend

## Objective

Fix the bounded autonomous Self-Healing feedback loop so repair attempts
receive useful, sanitized, bounded evidence from actual generated-code
validation failures.

The current implementation classifies subprocess failures but replaces the
actual validation failure with a generic summary.

This causes blind regeneration and repeated ineffective repairs.

## Confirmed Current Behavior

Inspect:

agent/ai/mission_runner.py

Specifically:

- validate_with_self_healing(...)
- _validation_failure_category(...)
- validation_callback(...)
- generation_callback(...)

Current behavior:

1. validate_generated_files(...) raises subprocess.CalledProcessError.
2. Failure category is identified.
3. Actual stdout/stderr/test failure details are discarded.
4. A generic safe_summary is created.
5. Repair generation receives only that generic summary.
6. Repair attempts therefore lack the actual failing test/assertion/import
   evidence.

This mission must correct that feedback gap.

## Primary Goal

Make bounded Self-Healing receive useful validation evidence such as:

- failing test name
- assertion/error type
- relevant traceback tail
- syntax/compiler error
- import failure
- relevant unittest output

while remaining:

- bounded
- sanitized
- deterministic
- secret-safe
- provider-independent

## Required Architecture

Create a non-Core helper:

agent/repair/validation_failure_evidence.py

The helper must accept subprocess.CalledProcessError or equivalent captured
validation information and return a deterministic structured result.

At minimum include:

- failure_category
- safe_summary
- sanitized_output
- command_class
- output_truncated
- fingerprint

## Evidence Sources

Safely inspect, when present:

- exc.stdout
- exc.stderr
- exc.output
- command identity

Do NOT expose arbitrary environment variables.

Do NOT read unrelated files.

Do NOT include credentials or secrets.

## Sanitization

Bound output size.

Remove or redact patterns including:

- private key blocks
- bearer tokens
- authorization headers
- obvious API keys
- passwords
- secrets
- credentials
- long opaque tokens

The sanitizer must fail closed.

Do not include full environment dumps.

Do not include arbitrary binary data.

## Bounded Output

The repair evidence must have a hard maximum size.

Prefer useful tail/context from validation output.

The result must be deterministic for identical input.

## Core Wiring Approval

A MINIMAL modification to:

agent/ai/mission_runner.py

is explicitly approved ONLY for wiring this helper into
validate_with_self_healing(...).

Permitted Core change:

1. capture validation failure evidence from the existing
   subprocess.CalledProcessError;
2. replace the current generic safe_summary with the helper's sanitized,
   bounded summary/evidence;
3. pass that evidence through the EXISTING MissionRepairAdapter request.

Nothing else.

## Forbidden Core Changes

Do NOT change:

- validate_generated_file path authority
- write_generated_files authority
- deliverable allowlists
- CORE_PATH_LOCKED
- repository protection
- retry counts
- repair budgets
- MissionQueue authority
- checkpoint lifecycle
- execution identity
- idempotency
- Git workflow
- deployment
- systemd
- provider routing

Do not create a new retry loop.

Do not create a new execution authority.

## Existing Retry Authority

MissionRepairAdapter and the existing repair loop remain the only Self-Healing
retry authority.

This change supplies better evidence only.

## Required Behavior

For unittest failure, a repair attempt should receive enough sanitized
information to know, for example:

- which test failed
- whether failure was AssertionError / ImportError / TypeError / etc.
- the useful error message
- relevant traceback tail

For py_compile failure it should receive the syntax/compiler error.

The next attempt must still receive exact allowed deliverables.

## Tests

Create:

agent/tests/test_validation_failure_evidence.py

Update existing mission-runner Self-Healing tests only if required.

Test at minimum:

1. unittest failure output captured
2. compiler error captured
3. stdout captured when stderr absent
4. stderr preferred appropriately
5. output bounded
6. deterministic fingerprint
7. secret redaction
8. bearer token redaction
9. private-key redaction
10. authorization header redaction
11. very long output truncated
12. empty output handled safely
13. generic fallback preserved
14. allowed deliverables unchanged
15. repair budget unchanged
16. MissionRepairAdapter remains sole retry authority
17. validator authority unchanged
18. no allowlist expansion
19. no queue mutation
20. no checkpoint identity change
21. existing Self-Healing tests continue passing

## Regression Validation

Run targeted validation.

Then run:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Run:

git diff --check

Verify no unexpected file scope.

## Strict Scope

Permitted final changed production files:

agent/repair/validation_failure_evidence.py
agent/ai/mission_runner.py

Permitted test/report files:

agent/tests/test_validation_failure_evidence.py
agent/tests/test_mission_runner_self_healing.py
docs/architecture/validation-feedback-loop.json

No other production path may change.

## Report

Create exactly:

docs/architecture/validation-feedback-loop.json

Required fields:

- mission_id
- implementation_completed
- root_cause_confirmed
- actual_validation_evidence_propagated
- evidence_bounded
- evidence_sanitized
- deterministic_fingerprint
- secret_redaction
- mission_runner_modified
- exact_core_change
- validator_authority_preserved
- write_authority_preserved
- retry_authority_preserved
- repair_budget_preserved
- checkpoint_identity_preserved
- execution_identity_preserved
- allowlist_mutation
- allowlist_expansion
- core_protection_weakened
- provider_independence
- external_runtime_dependency
- production_runtime_data_changed
- targeted_tests_passed
- full_test_suite_passed
- diff_check_passed
- rollback_plan
- remaining_work

Successful result requires:

implementation_completed = true
root_cause_confirmed = true
actual_validation_evidence_propagated = true
evidence_bounded = true
evidence_sanitized = true
deterministic_fingerprint = true
secret_redaction = true
mission_runner_modified = true
validator_authority_preserved = true
write_authority_preserved = true
retry_authority_preserved = true
repair_budget_preserved = true
checkpoint_identity_preserved = true
execution_identity_preserved = true
allowlist_mutation = false
allowlist_expansion = false
core_protection_weakened = false
provider_independence = true
external_runtime_dependency = false
production_runtime_data_changed = false
targeted_tests_passed = true
full_test_suite_passed = true
diff_check_passed = true

## Deliverables

agent/repair/validation_failure_evidence.py
agent/ai/mission_runner.py
agent/tests/test_validation_failure_evidence.py
agent/tests/test_mission_runner_self_healing.py
docs/architecture/validation-feedback-loop.json

## Git

Use the Agent mission branch.

Commit only after all validation passes.

Push the Agent branch.

Do not merge automatically.

Never force push.
