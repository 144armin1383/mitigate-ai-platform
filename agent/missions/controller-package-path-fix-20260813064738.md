# MITIGATE Production Mission Controller Package Path Fix

Mission ID: controller-package-path-fix-20260813064738
Request ID: controller-package-path-fix-20260813064738
Task Type: backend

CORE_MAINTENANCE_APPROVED

## Root Cause

ProductionMissionController currently launches Mission Runner using:

python -m ai.mission_runner

with:

cwd = agent/

This conflicts with the production package model used by systemd and the
runtime, which imports modules as:

agent.*

Observed facts:

- systemd WorkingDirectory is repository root
- background worker runs as:
  python -m agent.runtime.background_worker
- ProductionMissionController imports agent.git.*
- from repository root:
  import agent.ai.mission_runner fails because mission_runner internally
  imports ai.*
- from agent/:
  import ai.mission_runner succeeds
- from agent/:
  importing ProductionMissionController fails because it imports agent.*

This mixed package execution model causes the controller subprocess to fail
before mission branch creation and is currently collapsed to:

status = exhausted
reason = mission_execution_failed

## Objective

Normalize ProductionMissionController subprocess execution to the canonical
repository package model.

The controller must launch Mission Runner from repository root using:

python -m agent.ai.mission_runner <mission>

The subprocess cwd must be repository root.

Do not change mission semantics.

Do not change retry authority.

Do not change Self-Healing logic.

Do not change Core protection.

Do not change MissionQueue.

Do not change provider selection.

Do not alter infrastructure or systemd.

## Authorized Core Scope

The only production file authorized for modification is:

agent/runtime/production_mission_controller.py

No other production Python file may change.

## Required Changes

Update the Mission Runner subprocess execution path so that:

1. module target is:
   agent.ai.mission_runner

2. cwd is:
   repository root

3. existing timeout behavior remains unchanged

4. stdout/stderr capture remains unchanged

5. repository restore behavior remains unchanged

6. return-code handling remains unchanged

7. status mapping remains unchanged

8. merge policy remains unchanged

9. manual-review behavior remains unchanged

10. Core protection remains unchanged

## Required Tests

Create or update:

agent/tests/test_production_mission_controller.py

Add tests proving:

1. controller uses module:
   agent.ai.mission_runner

2. controller uses repository root as cwd

3. existing successful execution behavior remains unchanged

4. general failure still maps to exhausted

5. timeout still maps correctly

6. blocked statuses remain unchanged

7. no retry authority moves into controller

8. no queue mutation is introduced

## Validation

Run targeted tests:

python -m unittest agent.tests.test_production_mission_controller -v

Then run:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Then run:

git diff --check

All must pass.

## Deliverables

agent/runtime/production_mission_controller.py
agent/tests/test_production_mission_controller.py
docs/architecture/controller-package-path-fix.json

## Report

Create:

docs/architecture/controller-package-path-fix.json

Required fields:

- mission_id
- implementation_completed
- root_cause_confirmed
- canonical_module_path
- canonical_cwd
- controller_runtime_semantics_preserved
- retry_authority_preserved
- queue_authority_preserved
- self_healing_semantics_preserved
- core_protection_preserved
- provider_independence_preserved
- targeted_tests_passed
- full_test_suite_passed
- diff_check_passed
- manual_merge_required
- rollback_plan
- remaining_work

Required values:

implementation_completed = true
root_cause_confirmed = true
canonical_module_path = "agent.ai.mission_runner"
canonical_cwd = "repository_root"
controller_runtime_semantics_preserved = true
retry_authority_preserved = true
queue_authority_preserved = true
self_healing_semantics_preserved = true
core_protection_preserved = true
provider_independence_preserved = true
targeted_tests_passed = true
full_test_suite_passed = true
diff_check_passed = true
manual_merge_required = true

## Git

Use Agent mission branch.

Commit only after validation passes.

Push the Agent branch.

Do not merge automatically.

Never force push.
