# MITIGATE Validation Evidence Core Wiring — Final V2

Mission ID: validation-evidence-core-wiring-final-v2-20260813071919
Request ID: validation-evidence-core-wiring-final-v2-20260813071919
Task Type: backend

CORE_MAINTENANCE_APPROVED

## Objective

Complete the minimum safe Core wiring connecting existing structured
validation-failure evidence to MITIGATE's existing bounded autonomous
Self-Healing lifecycle.

The Python package execution/bootstrap problem has already been fixed.

Do not redesign the runtime.
Do not replace existing architecture.
Do not rewrite mission_runner.py wholesale.

Inspect the current repository implementation first and implement only the
smallest missing integration.

## Existing Native Components

Reuse the existing implementation wherever applicable, including:

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

## Required Behaviour

When mission validation fails:

1. Capture structured validation failure evidence.
2. Classify whether the failure is eligible for autonomous repair.
3. Feed eligible evidence into the existing Self-Healing lifecycle.
4. Preserve the existing allowlist boundary.
5. Preserve RetryBudget.
6. Preserve bounded retry limits.
7. Preserve deterministic terminal failure.
8. Preserve Core Protection.
9. Preserve MissionQueue authority.
10. Preserve existing execution-report behaviour.

The implementation must use existing native components rather than create
parallel retry, repair, queue, or validation systems.

## Core Maintenance Authorization

Modification of:

agent/ai/mission_runner.py

is explicitly authorized for this mission.

This authorization applies only to the minimum integration required by this
mission.

Do not modify any other protected Core production file.

## Deliverables

agent/ai/mission_runner.py
agent/tests/test_mission_runner_self_healing.py
docs/architecture/validation-evidence-core-wiring-final-v2.json

## Implementation Constraints

Patch the smallest possible integration point.

Do not:

- rewrite mission_runner.py wholesale
- redesign MissionQueue
- redesign ProductionMissionController
- alter systemd
- alter Runtime API
- alter provider architecture
- alter queue schema
- alter Git workflow
- weaken Core Protection
- create unlimited retries
- create recursive unbounded repair loops
- modify files outside the exact Deliverables allowlist

Preserve existing successful mission execution behaviour.

## Required Tests

The focused test deliverable must prove at minimum:

- validation failure evidence reaches Self-Healing
- eligible validation failure can enter bounded repair
- ineligible failure does not enter repair
- RetryBudget remains enforced
- allowlist boundary remains enforced
- repeated repair failure terminates deterministically
- successful existing mission path remains unchanged

Preserve existing canonical tests.

Do not replace the existing test file wholesale merely to satisfy this mission.

## Required Evidence

Generate:

docs/architecture/validation-evidence-core-wiring-final-v2.json

as valid JSON.

It must contain at minimum:

- mission_id
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

The report must explicitly establish whether the required Core wiring is
complete.

## Validation

Run relevant focused tests including:

python -m unittest agent.tests.test_mission_runner_self_healing

Run relevant validation evidence tests.

Run relevant RetryBudget and Self-Healing tests.

Run:

git diff --check

All required validation must pass before commit.

## Git

Use the existing Agent mission branch workflow.

Commit the validated implementation.

Push the Agent branch.

Do not merge automatically.

Never force push.

## Final State

The final evidence must explicitly report:

VALIDATION_EVIDENCE_CORE_WIRING_COMPLETE
SELF_HEALING_CONNECTED
RETRY_BUDGET_PRESERVED
ALLOWLIST_PRESERVED
CORE_PROTECTION_PRESERVED
QUEUE_AUTHORITY_PRESERVED
REGRESSION_TESTS_PASSED
READY_FOR_HUMAN_FINAL_REVIEW
