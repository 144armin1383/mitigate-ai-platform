# MITIGATE Production Mission Controller Package Path Fix V2

Mission ID: controller-package-path-fix-v2-20260813065907
Request ID: controller-package-path-fix-v2-20260813065907
Task Type: backend

CORE_MAINTENANCE_APPROVED

## Objective

Apply a MINIMAL surgical correction to the existing
ProductionMissionController subprocess execution path.

The previous mission branch was rejected because it replaced most of
ProductionMissionController and most of its canonical tests.

That approach is forbidden.

## Confirmed Root Cause

ProductionMissionController currently executes Mission Runner using:

- module: ai.mission_runner
- cwd: agent root

The production runtime itself uses the repository-root package model:

- python -m agent.runtime.background_worker

The correction must normalize only the Mission Runner subprocess launch to:

- module: agent.ai.mission_runner
- cwd: repository root

## Mandatory Preservation Rule

Do NOT rewrite ProductionMissionController.

Do NOT replace the class.

Do NOT redesign the module.

Do NOT remove existing imports unless directly required by the two-line
execution-path correction.

Do NOT remove existing methods.

Do NOT remove review logic.

Do NOT remove merge logic.

Do NOT remove restore logic.

Do NOT remove status mapping.

Do NOT remove timeout handling.

Do NOT remove safe-output handling.

Do NOT remove GitReviewEngine integration.

Do NOT replace the controller with project-path or architecture-loading helpers.

The existing file structure and behaviour must remain intact.

## Maximum Production Change Scope

In:

agent/runtime/production_mission_controller.py

the intended production modification is limited to the existing execute()
subprocess launch area.

Expected semantic change:

Before:

python -m ai.mission_runner
cwd = agent root

After:

python -m agent.ai.mission_runner
cwd = repository root

Only directly necessary adjacent code may change.

## Existing Test Preservation

The existing canonical test file:

agent/tests/test_production_mission_controller.py

must be preserved.

Do NOT replace it.

Do NOT substantially shorten it.

Do NOT delete existing test classes.

Do NOT delete existing test methods.

Only ADD or minimally adjust tests required to verify:

1. module target is agent.ai.mission_runner
2. subprocess cwd is repository root
3. existing success semantics remain unchanged
4. existing blocked semantics remain unchanged
5. existing exhausted semantics remain unchanged
6. timeout semantics remain unchanged
7. repository restore semantics remain unchanged
8. merge/review semantics remain unchanged

## Quantitative Guardrails

Production controller line-count reduction greater than 10% is forbidden.

Canonical controller test line-count reduction greater than 2% is forbidden.

Existing public methods must remain present.

Existing ProductionMissionController.execute() must remain present.

## Authorized Deliverables

agent/runtime/production_mission_controller.py
agent/tests/test_production_mission_controller.py
docs/architecture/controller-package-path-fix-v2.json

No other file may change.

## Forbidden Changes

Do NOT modify:

- MissionQueue
- background_worker.py
- mission_runner.py
- retry logic
- Self-Healing
- Core protection
- provider configuration
- systemd
- deployment files
- runtime data
- Git policies

## Validation

Run:

python -m unittest agent.tests.test_production_mission_controller -v

Then:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Then:

git diff --check

All must pass.

## Structural Validation

Before commit, verify:

- ProductionMissionController class still exists
- execute() still exists
- GitReviewEngine integration still exists
- subprocess execution still exists
- repository restore logic still exists
- review and merge logic still exists
- existing status mapping remains present
- test file retains substantially all previous tests

## Required Report

Create exactly:

docs/architecture/controller-package-path-fix-v2.json

Required fields:

{
  "mission_id": "controller-package-path-fix-v2-20260813065907",
  "implementation_completed": true,
  "root_cause_confirmed": true,
  "canonical_module_path": "agent.ai.mission_runner",
  "canonical_cwd": "repository_root",
  "minimal_patch": true,
  "controller_class_preserved": true,
  "execute_method_preserved": true,
  "review_logic_preserved": true,
  "merge_logic_preserved": true,
  "restore_logic_preserved": true,
  "status_mapping_preserved": true,
  "retry_authority_preserved": true,
  "queue_authority_preserved": true,
  "self_healing_semantics_preserved": true,
  "core_protection_preserved": true,
  "provider_independence_preserved": true,
  "canonical_tests_preserved": true,
  "targeted_tests_passed": true,
  "full_test_suite_passed": true,
  "diff_check_passed": true,
  "manual_merge_required": true,
  "rollback_plan": "",
  "remaining_work": ""
}

## Git Rules

Use an Agent mission branch.

Commit only after all validation passes.

Push the Agent branch.

Do not merge into main.

Never force push.
