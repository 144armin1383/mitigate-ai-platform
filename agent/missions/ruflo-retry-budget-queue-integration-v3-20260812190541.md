# MITIGATE RetryBudget Queue Adapter V3

Mission ID: ruflo-retry-budget-queue-integration-v3-20260812190541
Request ID: ruflo-retry-budget-queue-integration-v3-20260812190541
Task Type: backend

## Objective

Complete Phase B2.1 by implementing a MITIGATE-native, provider-independent
adapter between MissionQueue retry state and the validated RetryBudget
foundation.

Previous attempts established two important repository constraints:

1. MissionQueue must remain unchanged.
2. New files under agent/runtime are protected by CORE_PATH_LOCKED.

Therefore this mission MUST implement the integration through the existing
resilience extension layer.

Do not weaken or bypass CORE_PATH_LOCKED.

## Existing Components

Inspect read-only:

- agent/runtime/mission_queue.py
- agent/resilience/retry_budget.py
- agent/resilience/capability_kernel.py
- agent/tests/test_mission_queue.py
- agent/tests/test_retry_budget.py

Already validated:

- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py

MissionQueue remains the authoritative owner of retry state.

## Required Adapter

Create exactly:

agent/resilience/retry_budget_queue_adapter.py

Do not create any adapter under agent/runtime.

The adapter must provide a deterministic, side-effect-free projection from
existing MissionQueue mission retry fields to native RetryBudget semantics.

The adapter may consume a mission mapping / mission retry state as input.

It must not require MissionQueue source modification.

It must not persist anything.

It must not mutate the input mission.

## Retry Authority

These existing MissionQueue fields remain authoritative:

- attempts_done
- max_retries

The adapter must NOT introduce:

- a second retry counter
- independent retry consumption
- hidden retry authority
- a persistence format
- queue mutations
- background execution

RetryBudget is a policy/view only.

## Required Semantics

Support and validate at minimum:

- attempts_done
- max_retries
- retries remaining
- exhausted state
- retry eligibility

Required behavior:

- max_retries=0 grants no additional retry
- max_retries=1 grants at most one retry
- larger retry budgets remain deterministic
- attempts_done remains MissionQueue-owned
- exhausted state cannot gain retry authority
- retrying mission state projects correctly
- completed mission state does not gain retry authority
- blocked mission state does not gain retry authority
- failed mission state is represented consistently
- stale-running/recovery-shaped records remain projection-safe
- legacy queue records remain compatible
- no schema migration exists

Fail closed for malformed retry values.

Reject semantically invalid boolean-as-integer retry fields where necessary.

Do not silently normalize corrupt retry state into a permissive retry decision.

## Compatibility

Preserve compatibility with:

- MissionQueue existing persistence contract
- BackgroundWorker existing retry semantics
- durable checkpointing
- idempotent execution
- FlowSpec v1
- Python 3.12
- provider independence

No runtime production behavior is activated by this mission.

## Tests

Create:

agent/tests/test_retry_budget_queue_adapter.py

Cover at minimum:

- zero retries
- one retry
- multiple retries
- deterministic retries remaining
- exhaustion
- malformed attempts_done
- malformed max_retries
- negative values
- bool/int edge cases
- retrying state
- failed state
- completed state
- blocked state
- legacy record compatibility
- repeated projection determinism
- input mapping remains unchanged
- adapter has no independent consumption authority

Run existing RetryBudget and MissionQueue tests as regression coverage.

## Prohibited Changes

Do not modify:

- agent/runtime/mission_queue.py
- agent/runtime/background_worker.py
- agent/resilience/capability_kernel.py
- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py
- agent/ai/mission_runner.py
- agent/runtime/production_mission_controller.py
- agent/runtime/checkpoint_store.py
- agent/runtime/idempotent_execution_contract.py
- TechnologyRegistry
- systemd
- production runtime data

Do not:

- create files under agent/runtime
- weaken CORE_PATH_LOCKED
- weaken the allowlist
- install dependencies
- import Ruflo
- copy Ruflo code
- create external services
- create undeclared files

## Report

Create:

docs/technology/evaluations/ruflo/3.37.0-retry-budget-queue-integration.json

The report must be valid JSON and include:

- mission_id
- integration_scope
- adapter_created
- adapter_path
- mission_queue_modified
- retry_budget_modified
- persistence_schema_changed
- migration_required
- retry_state_authority
- existing_retry_semantics_preserved
- core_path_guard_preserved
- tests_added
- full_test_result
- production_runtime_data_changed
- external_runtime_dependency
- provider_independence_preserved
- remaining_integration_work

Required values:

adapter_created = true
adapter_path = "agent/resilience/retry_budget_queue_adapter.py"
mission_queue_modified = false
retry_budget_modified = false
persistence_schema_changed = false
migration_required = false
retry_state_authority = "MissionQueue"
existing_retry_semantics_preserved = true
core_path_guard_preserved = true
production_runtime_data_changed = false
external_runtime_dependency = false
provider_independence_preserved = true

remaining_integration_work must state that B2.2 still needs
BackgroundWorker / RetryClassification / RetryMetrics integration through
an approved core-safe integration mechanism.

## Deliverables

agent/resilience/retry_budget_queue_adapter.py
agent/tests/test_retry_budget_queue_adapter.py
docs/technology/evaluations/ruflo/3.37.0-retry-budget-queue-integration.json

## Validation

Run:

python -m unittest -v   agent.tests.test_retry_budget   agent.tests.test_mission_queue   agent.tests.test_retry_budget_queue_adapter

Then run:

python -m unittest discover -v agent/tests

Run:

git diff --check

Requirements:

- full test suite passes
- no unrelated files change
- no core files change
- no runtime data changes
- no external dependencies
- Python 3.12 compatibility

## Git

Use the Mission Runner branch.

Commit validated work.

Push the mission branch.

Do not modify main directly.

## Success Criteria

Phase B2.1 is complete when MissionQueue retry state can be projected into
RetryBudget semantics through the resilience extension layer without
modifying MissionQueue or weakening core repository protections.
