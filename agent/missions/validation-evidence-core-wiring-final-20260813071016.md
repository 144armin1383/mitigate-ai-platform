# MITIGATE Validation Evidence Core Wiring — Final Approved Mission

Mission ID: validation-evidence-core-wiring-final-20260813071016
Request ID: validation-evidence-core-wiring-final-20260813071016
Task Type: backend

CORE_MAINTENANCE_APPROVED

## Objective

Complete the minimum safe Core wiring that connects existing validation
failure evidence to MITIGATE's existing bounded autonomous Self-Healing
lifecycle.

The Python package execution-path/bootstrap issue that prevented previous
Core missions from executing has already been repaired and validated.

Do not redesign the runtime.

Do not replace existing architecture.

Implement only the missing integration.

## Existing Components

Reuse the existing native components wherever applicable:

- MissionQueue
- BackgroundWorker
- ProductionMissionController
- mission_runner
- validation failure evidence
- Self-Healing
- retry classification
- RetryBudget
- bounded retry lifecycle
- allowlist recovery
- structured repair evidence
- Core Protection
- Git review
- execution reports

## Authorized Core Scope

The only protected Core production file authorized for modification is:

agent/ai/mission_runner.py

Do not modify any other protected Core production file.

## Additional Allowed Files

Tests may be added or minimally modified under:

agent/tests/

Architecture evidence may be written under:

docs/architecture/

## Required Behaviour

When mission validation fails:

1. Capture structured validation failure evidence.

2. Classify whether the failure is eligible for autonomous repair.

3. Feed eligible evidence into the existing Self-Healing lifecycle.

4. Respect existing allowlist boundaries.

5. Respect RetryBudget.

6. Respect bounded retry limits.

7. Preserve deterministic terminal states.

8. Preserve existing Core Protection.

9. Preserve existing MissionQueue authority.

10. Preserve existing execution-report behaviour.

## Mandatory Constraints

Do not:

- rewrite mission_runner.py
- replace existing functions wholesale
- redesign MissionQueue
- redesign ProductionMissionController
- alter systemd
- alter runtime API
- alter provider architecture
- alter queue schema
- alter Git workflow
- weaken Core Protection
- create unlimited retries
- create recursive unbounded repair loops

Patch the smallest possible integration point.

## Regression Protection

Existing behaviour must remain intact.

Run existing mission-runner and Self-Healing tests before and after changes.

The Agent must reject its own implementation if unrelated canonical tests
regress.

## Required Tests

Add or update focused tests proving:

- validation failure evidence reaches Self-Healing
- eligible failure can enter bounded repair
- ineligible failure does not enter repair
- RetryBudget is respected
- allowlist boundary is respected
- repeated failure terminates deterministically
- existing successful mission path remains unchanged

## Required Evidence

Create:

docs/architecture/validation-evidence-core-wiring-final.json

The report must contain:

- integration_point
- files_changed
- tests_run
- tests_passed
- regression_status
- retry_budget_preserved
- allowlist_preserved
- core_protection_preserved
- queue_authority_preserved
- self_healing_path
- terminal_failure_behavior

## Validation

Run:

python -m unittest agent.tests.test_mission_runner_self_healing

Run relevant validation evidence tests.

Run relevant retry / Self-Healing tests.

Run:

git diff --check

All tests must pass before committing.

## Git

Use Agent mission branch.

Commit validated implementation.

Push Agent branch.

Do not merge automatically.

Never force push.

## Final State

The final report must explicitly state:

VALIDATION_EVIDENCE_CORE_WIRING_COMPLETE

SELF_HEALING_CONNECTED

RETRY_BUDGET_PRESERVED

ALLOWLIST_PRESERVED

CORE_PROTECTION_PRESERVED

QUEUE_AUTHORITY_PRESERVED

REGRESSION_TESTS_PASSED

READY_FOR_HUMAN_FINAL_REVIEW
