# MITIGATE Retry Worker Integration V2

Mission ID: ruflo-retry-worker-integration-v2-20260812193401
Request ID: ruflo-retry-worker-integration-v2-20260812193401
Task Type: backend

## Objective

Create a deterministic, provider-independent, side-effect-free execution
projection adapter connecting the already validated native retry foundations.

This is Phase B2.2 V2.

The adapter is NOT a retry engine.

MissionQueue and the existing runtime/controller remain the sole authorities
for retry execution and retry state.

## Existing Components

Inspect and reuse:

- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py
- agent/resilience/retry_budget.py
- agent/resilience/retry_budget_queue_adapter.py
- existing checkpoint and idempotent execution contracts

Do not duplicate these capabilities.

## Critical Architecture Rule

The new adapter MUST NOT:

- perform retry loops
- call sleep
- implement backoff waiting
- retry functions or callbacks
- execute arbitrary user functions
- mutate MissionQueue
- mutate mission records
- increment attempts_done
- decrement retry budgets
- own retry state
- create threads
- perform network calls
- write runtime state
- modify background_worker.py
- modify mission_queue.py
- modify autonomous_controller.py
- modify mission_runner.py
- modify any protected Core file

The adapter is a pure deterministic projection / event-construction layer.

## Required Behavior

The adapter must accept explicit provider-neutral inputs describing:

- mission identity
- execution identity
- classification input/result
- RetryBudget/MissionQueue projection information
- safe optional metadata

It must produce deterministic structured data suitable for:

- retry observability
- retry metrics compatibility
- runtime integration
- checkpoint correlation

It must preserve mission and execution identity.

It must never make the authoritative retry decision itself.

MissionQueue remains retry_state_authority.

Retry eligibility/budget information must be consumed as a read-only
projection from the existing retry_budget_queue_adapter.

Retry classification must reuse the existing RetryClassifier contract.

Do not create another classifier.

## Security / Data Rules

Do not store:

- arbitrary exception repr
- traceback payloads
- secrets
- credentials
- tokens
- arbitrary request/response bodies

Only bounded provider-neutral structured metadata is permitted.

Inputs must not be mutated.

Output must be JSON serializable.

## Deliverable Implementation

Create exactly:

agent/resilience/retry_execution_adapter.py
agent/tests/test_retry_execution_adapter.py
docs/technology/evaluations/ruflo/3.37.0-retry-worker-integration-v2.json

Do not create any other file.

## Tests

Create unittest-compatible tests covering at minimum:

- retryable classification projection
- non-retryable classification projection
- exhausted classification projection
- cancelled classification projection
- deadline-exceeded classification projection
- deterministic output
- mission identity preservation
- execution identity preservation
- RetryBudget projection compatibility
- MissionQueue remains retry authority
- no mutation of input mappings
- JSON serializable output
- safe optional metadata
- rejection or sanitization of unsafe arbitrary metadata
- no retry loop
- no sleep
- no queue mutation
- no retry counter mutation
- no network behavior

Tests MUST use Python standard-library unittest only.

Do not use pytest.

Do not add dependencies.

## Report

Create:

docs/technology/evaluations/ruflo/3.37.0-retry-worker-integration-v2.json

Required fields:

- mission_id
- integration_scope
- adapter_created
- adapter_path
- extension_point_found
- extension_point_used
- background_worker_modified
- core_change_required
- core_change_reason
- exact_core_change_target
- retry_classification_integrated
- retry_metrics_integrated
- retry_state_authority
- retry_budget_projection_integrated
- checkpoint_identity_preserved
- idempotent_execution_preserved
- production_runtime_data_changed
- external_runtime_dependency
- provider_independence_preserved
- tests_added
- full_test_result
- remaining_work

Required values:

adapter_created = true
adapter_path = "agent/resilience/retry_execution_adapter.py"
background_worker_modified = false
retry_state_authority = "MissionQueue"
retry_classification_integrated = true
retry_budget_projection_integrated = true
checkpoint_identity_preserved = true
idempotent_execution_preserved = true
production_runtime_data_changed = false
external_runtime_dependency = false
provider_independence_preserved = true

If actual production wiring would require modifying a protected runtime file:

core_change_required = true

and identify the exact minimal file/function in:

exact_core_change_target

Do NOT perform that core modification in this mission.

If no core modification is required:

core_change_required = false

## Validation

The repository Mission Runner will execute the complete unittest suite.

The generated implementation must therefore remain compatible with all
existing agent/tests.

Also ensure:

python -m py_compile   agent/resilience/retry_execution_adapter.py   agent/tests/test_retry_execution_adapter.py

python -m unittest discover -s agent/tests -p 'test_*.py' -v

git diff --check

No unrelated files may change.

## Git

Use the Mission Runner branch.

Commit validated output.

Push the mission branch.

Do not modify main directly.

## Success Criteria

B2.2 V2 produces a validated pure retry execution projection adapter without
introducing duplicate retry authority or changing protected production
runtime behavior.

The report gives a definitive answer on whether a final human-approved
production wiring step remains necessary.

## Deliverables

agent/resilience/retry_execution_adapter.py
agent/tests/test_retry_execution_adapter.py
docs/technology/evaluations/ruflo/3.37.0-retry-worker-integration-v2.json
