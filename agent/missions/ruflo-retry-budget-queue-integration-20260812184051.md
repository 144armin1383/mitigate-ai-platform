# MITIGATE RetryBudget MissionQueue Integration

Mission ID: ruflo-retry-budget-queue-integration-20260812184051
Request ID: ruflo-retry-budget-queue-integration-20260812184051
Task Type: backend

## Objective

Integrate the already validated native RetryBudget foundation with the
existing MissionQueue retry semantics.

This is a narrowly scoped production-code integration mission.

Do not modify BackgroundWorker in this mission.

Do not modify CapabilityKernel in this mission.

Do not modify RetryClassification or RetryMetrics.

The purpose is only to make RetryBudget a native policy/view compatible
with MissionQueue retry accounting without duplicating retry state.

## Existing Foundation

Already present on main:

- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py

Architecture reports:

- docs/technology/evaluations/ruflo/3.37.0-deferred-capability-review.json
- docs/technology/evaluations/ruflo/3.37.0-retry-policy-foundation.json

Inspect these files before changing anything.

## Existing MissionQueue Contract

Inspect:

agent/runtime/mission_queue.py

Preserve all existing behavior including:

- persistent JSON queue format
- atomic persistence
- file locking
- deterministic ordering
- duplicate mission ID protection
- dependency scheduling
- claim semantics
- retrying state
- retry budget behavior
- attempts_done
- max_retries
- stale running recovery
- blocked/completed/failed transitions
- legacy queue compatibility

Do not change the persisted queue schema unless absolutely unavoidable.

Strong preference: NO persistence schema change.

## Required RetryBudget Integration

Use RetryBudget as a policy/view over existing MissionQueue counters.

Existing queue fields remain authoritative:

- attempts_done
- max_retries

Do NOT add a second persisted retry counter.

Do NOT add hidden retry authority.

Do NOT increment retries in RetryBudget independently of MissionQueue.

The integration should make it possible for queue/runtime callers to derive
a RetryBudget-compatible view from existing mission retry state.

Preferred design characteristics:

- deterministic
- side-effect free where possible
- backward compatible
- explicit
- independently testable
- no migration
- no external dependencies

If a helper or method is added to MissionQueue, keep it minimal and clearly
documented.

If direct coupling to RetryBudget would unnecessarily complicate
MissionQueue, use the smallest safe adapter/helper inside the allowed scope.

## Required Semantics

Verify at minimum:

- max_retries=0 means no retry remains after first failed attempt
- retry budget never grants an extra retry
- retry budget never consumes retries independently
- attempts_done remains MissionQueue-owned
- retry exhaustion remains deterministic
- existing retry transition semantics remain unchanged
- stale-running recovery does not consume retry budget unexpectedly
- completed missions are unaffected
- blocked missions are unaffected
- existing persisted queue records remain loadable
- no migration is required

## Test Requirements

Create focused integration tests covering:

- RetryBudget projection from MissionQueue retry state
- zero retry budget
- one retry budget
- multiple retries
- exhausted mission
- retrying mission
- successful mission behavior unchanged
- stale running recovery compatibility
- legacy queue persistence compatibility
- no extra retry consumption
- deterministic remaining retry calculation
- existing MissionQueue retry tests remain valid

Use unittest conventions from agent/tests.

## Prohibited Changes

Do not modify:

- agent/runtime/background_worker.py
- agent/resilience/capability_kernel.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py
- agent/runtime/checkpoint_store.py
- agent/runtime/flowspec.py
- agent/runtime/flowspec_materializer.py
- agent/runtime/idempotent_execution_contract.py
- TechnologyRegistry
- systemd
- production runtime data

Do not:

- install dependencies
- import Ruflo
- copy Ruflo code
- add Redis
- add Kafka
- add SQS
- add Celery
- add database migrations
- change production queue data

## Report

Create:

docs/technology/evaluations/ruflo/3.37.0-retry-budget-queue-integration.json

The JSON report must include:

- mission_id
- integration_scope
- mission_queue_changes
- retry_budget_integration
- persistence_schema_changed
- migration_required
- existing_retry_semantics_preserved
- tests_added
- targeted_test_result
- full_test_result
- production_runtime_data_changed
- external_runtime_dependency
- provider_independence_preserved
- remaining_integration_work

Required values:

persistence_schema_changed = false
migration_required = false
existing_retry_semantics_preserved = true
production_runtime_data_changed = false
external_runtime_dependency = false
provider_independence_preserved = true

remaining_integration_work must explicitly state that BackgroundWorker /
RetryClassification / RetryMetrics integration remains for Phase B2.2.

## Deliverables

agent/runtime/mission_queue.py
agent/tests/test_retry_budget_mission_queue_integration.py
docs/technology/evaluations/ruflo/3.37.0-retry-budget-queue-integration.json

## Validation

Run focused tests including:

python -m unittest -v   agent.tests.test_retry_budget   agent.tests.test_mission_queue   agent.tests.test_retry_budget_mission_queue_integration

Then run:

python -m unittest discover -v agent/tests

Run:

git diff --check

Verify all existing tests pass.

Verify no unrelated files change.

Verify Python 3.12 compatibility.

## Git

Use the Mission Runner branch.

Commit validated output.

Push the mission branch.

Do not manually merge main.

## Success Criteria

The result must demonstrate that RetryBudget and MissionQueue now share a
single coherent retry accounting model without duplicate state or changed
persistence format.
