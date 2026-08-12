# MITIGATE RetryBudget MissionQueue Adapter Integration V2

Mission ID: ruflo-retry-budget-queue-integration-v2-20260812195503
Request ID: ruflo-retry-budget-queue-integration-v2-20260812195503
Task Type: backend

## Objective

Implement a provider-independent adapter between the already validated
native RetryBudget foundation and the existing MissionQueue retry state.

This mission MUST NOT modify MissionQueue itself.

MissionQueue is inspected read-only and remains the authoritative owner of:

- attempts_done
- max_retries
- retry state transitions
- persisted retry state

The previous attempts showed that an adapter is the natural integration
boundary. This mission explicitly permits exactly one production adapter.

## Existing Native Components

Inspect read-only:

- agent/runtime/mission_queue.py
- agent/resilience/retry_budget.py
- agent/tests/test_mission_queue.py
- agent/tests/test_retry_budget.py

Already validated foundation:

- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py

Do not duplicate these components.

## Required Adapter

Create exactly:

agent/runtime/retry_budget_adapter.py

The adapter must provide a deterministic and side-effect-free projection
from existing MissionQueue mission retry fields into RetryBudget semantics.

MissionQueue fields remain authoritative.

Do not persist retry state in the adapter.

Do not mutate mission dictionaries.

Do not consume retry attempts.

Do not write queue files.

Do not perform network calls.

Do not add background threads.

Do not create global mutable state.

## Required Semantics

The adapter must correctly represent at minimum:

- attempts_done
- max_retries
- retries remaining
- exhausted state
- retry eligibility

Required behavior:

- max_retries=0 never grants an extra retry
- max_retries=1 grants at most one retry
- multiple retry budgets remain deterministic
- attempts_done remains MissionQueue-owned
- no independent retry consumption exists
- exhausted missions remain exhausted
- retrying missions project correctly
- completed missions do not gain retry authority
- blocked missions do not gain retry authority
- stale-running recovery does not alter budget projection
- legacy mission records remain compatible
- no queue schema migration is required

Fail closed on malformed retry fields.

Boolean values must not silently behave as integers where that would
corrupt retry accounting.

## MissionQueue Boundary

agent/runtime/mission_queue.py is READ ONLY for this mission.

Do not generate or modify:

agent/runtime/mission_queue.py

Do not modify queue persistence format.

Do not modify queue state transitions.

Do not introduce new queue fields.

## Tests

Create:

agent/tests/test_retry_budget_mission_queue_integration.py

Tests must cover at minimum:

- zero retry budget
- one retry
- multiple retries
- exhausted state
- remaining retry calculation
- malformed attempts_done
- malformed max_retries
- bool/int validation edge cases
- mission dictionary remains unchanged
- deterministic repeated projection
- legacy mission shape compatibility
- retrying state compatibility
- completed state compatibility
- blocked state compatibility
- no independent retry consumption

Use existing unittest conventions.

## Prohibited Changes

Do not modify:

- agent/runtime/mission_queue.py
- agent/runtime/background_worker.py
- agent/resilience/capability_kernel.py
- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py
- agent/runtime/checkpoint_store.py
- agent/runtime/idempotent_execution_contract.py
- agent/ai/mission_runner.py
- agent/runtime/production_mission_controller.py
- TechnologyRegistry
- production runtime data
- systemd

Do not:

- install dependencies
- import Ruflo
- copy Ruflo code
- weaken repository protections
- create additional adapter filenames
- create undeclared files

## Report

Create:

docs/technology/evaluations/ruflo/3.37.0-retry-budget-queue-integration.json

The JSON report must include:

- mission_id
- integration_scope
- adapter_created
- mission_queue_modified
- retry_budget_modified
- persistence_schema_changed
- migration_required
- retry_state_authority
- existing_retry_semantics_preserved
- tests_added
- full_test_result
- production_runtime_data_changed
- external_runtime_dependency
- provider_independence_preserved
- remaining_integration_work

Required values:

adapter_created = true
mission_queue_modified = false
retry_budget_modified = false
persistence_schema_changed = false
migration_required = false
retry_state_authority = "MissionQueue"
existing_retry_semantics_preserved = true
production_runtime_data_changed = false
external_runtime_dependency = false
provider_independence_preserved = true

remaining_integration_work must state that integration with
BackgroundWorker / RetryClassification / RetryMetrics remains for B2.2.

## Deliverables

agent/runtime/retry_budget_adapter.py
agent/tests/test_retry_budget_mission_queue_integration.py
docs/technology/evaluations/ruflo/3.37.0-retry-budget-queue-integration.json

## Validation

Run:

python -m unittest -v   agent.tests.test_retry_budget   agent.tests.test_mission_queue   agent.tests.test_retry_budget_mission_queue_integration

Then run:

python -m unittest discover -v agent/tests

Run:

git diff --check

All existing tests must pass.

No unrelated files may change.

## Git

Use the Mission Runner branch.

Commit validated output.

Push the mission branch.

Do not modify main directly.

## Success Criteria

The adapter provides one deterministic bridge between MissionQueue retry
state and RetryBudget without changing MissionQueue, persistence, or retry
authority.

Repository core-path protections remain intact.
