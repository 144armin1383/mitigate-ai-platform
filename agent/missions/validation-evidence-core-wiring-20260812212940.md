# MITIGATE Validation Evidence Core Wiring Continuation

Mission ID: validation-evidence-core-wiring-20260812212940
Request ID: validation-evidence-core-wiring-20260812212940
Task Type: implementation

## Background

The previous mission:

validation-feedback-loop-20260812212047

correctly identified that validate_with_self_healing(...) currently discards
useful subprocess.CalledProcessError validation evidence and replaces it with
a generic safe_summary.

That mission failed before validation because its AI generation omitted the
required Core deliverable:

agent/ai/mission_runner.py

The failure was:

AI did not generate all deliverables: ['agent/ai/mission_runner.py']

Do NOT treat the previous generated report as proof of implementation.

Do NOT resume or mutate the previous mission.

This is a clean continuation.

## Objective

Implement the minimum safe validation-feedback wiring so existing bounded
Self-Healing receives sanitized and bounded evidence from actual validation
failures.

## Core Approval

A MINIMAL modification to:

agent/ai/mission_runner.py

is explicitly approved for this mission.

The Core modification is limited to validate_with_self_healing(...) and
required imports.

Permitted behavior:

1. capture subprocess.CalledProcessError from existing validation;
2. pass that exception to the validation evidence helper;
3. use the helper's bounded sanitized safe_summary instead of the current
   generic summary;
4. propagate structured bounded evidence through the EXISTING repair request
   path where supported without creating new execution authority.

No other Core behavior may change.

## Required Helper

Create:

agent/repair/validation_failure_evidence.py

It must convert validation failure evidence into deterministic, bounded,
sanitized structured evidence.

At minimum return:

- failure_category
- safe_summary
- sanitized_output
- command_class
- output_truncated
- fingerprint

Evidence sources may include:

- exc.stdout
- exc.stderr
- exc.output
- safe command identity

Never inspect arbitrary environment variables.

Never read unrelated files.

## Sanitization

Redact at minimum:

- bearer tokens
- authorization headers
- API keys
- private-key material
- obvious secret/token/password assignments

Output must have a hard maximum size.

Identical input must produce identical fingerprint/output.

## Existing Authorities Must Remain Unchanged

Do NOT modify:

- validate_generated_file path authority
- write_generated_files authority
- deliverable completeness enforcement
- deliverable allowlists
- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- repository protection
- retry counts
- repair budgets
- MissionQueue
- checkpoint lifecycle
- execution identity
- Git workflow
- deployment
- systemd
- provider routing

Do NOT create another retry loop.

MissionRepairAdapter and the existing repair lifecycle remain the sole retry
authority.

## Required Tests

Create:

agent/tests/test_validation_failure_evidence.py

Create or update:

agent/tests/test_mission_runner_self_healing.py

Test at minimum:

1. unittest failure evidence
2. py_compile/compiler evidence
3. stdout fallback
4. stderr evidence
5. bounded output
6. deterministic fingerprint
7. bearer-token redaction
8. authorization-header redaction
9. API-key/secret redaction
10. private-key redaction
11. empty-output fallback
12. very-long-output truncation
13. validate_with_self_healing uses real sanitized evidence
14. allowed deliverables remain unchanged
15. retry authority remains unchanged
16. repair budget remains unchanged
17. validator authority remains unchanged
18. no allowlist expansion
19. no queue mutation
20. existing Self-Healing tests continue passing

## Validation

Run targeted tests.

Then run:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Then run:

git diff --check

All must pass before commit.

## Strict File Scope

Permitted production changes:

agent/repair/validation_failure_evidence.py
agent/ai/mission_runner.py

Permitted tests/report:

agent/tests/test_validation_failure_evidence.py
agent/tests/test_mission_runner_self_healing.py
docs/architecture/validation-evidence-core-wiring.json

No other production file may change.

## Critical Generation Requirement

The AI response MUST contain the COMPLETE deliverable set.

It MUST generate:

agent/repair/validation_failure_evidence.py
agent/ai/mission_runner.py
agent/tests/test_validation_failure_evidence.py
agent/tests/test_mission_runner_self_healing.py
docs/architecture/validation-evidence-core-wiring.json

Do not omit agent/ai/mission_runner.py.

Do not claim implementation_completed=true unless that file was actually
generated, written, validated, and included in the final Git diff.

## Report

Create exactly:

docs/architecture/validation-evidence-core-wiring.json

Include:

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
- complete_deliverable_set_generated
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

## Acceptance

Success requires:

implementation_completed = true
root_cause_confirmed = true
actual_validation_evidence_propagated = true
evidence_bounded = true
evidence_sanitized = true
deterministic_fingerprint = true
secret_redaction = true
mission_runner_modified = true
complete_deliverable_set_generated = true
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

## Git

Use the Agent mission branch.

Commit only after validation passes.

Push the Agent branch.

Do not merge automatically.

Never force push.
