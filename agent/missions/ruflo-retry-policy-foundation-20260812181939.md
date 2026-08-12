# MITIGATE Native Retry Policy Foundation

Mission ID: ruflo-retry-policy-foundation-20260812181939
Request ID: ruflo-retry-policy-foundation-20260812181939
Task Type: backend

## Objective

Implement the native foundation required to complete the
retry_backoff_policy extension identified by the Ruflo deferred
capability architecture review.

This is autonomous engineering work.

Inspect the repository before implementation.

Reuse existing MITIGATE resilience architecture.

Do not create a parallel retry subsystem.

Do not modify production wiring in this mission.

## Architecture Review Source

Use:

docs/technology/evaluations/ruflo/3.37.0-deferred-capability-review.json

That review concluded:

retry_backoff_policy = extend_existing
task_registry = already_native
queue_abstraction = already_native

Do not implement task_registry.

Do not implement queue_abstraction.

## Existing Architecture To Preserve

Inspect and preserve at minimum:

- agent/resilience/capability_kernel.py
- existing CircuitBreaker
- existing retry/backoff behavior
- agent/runtime/background_worker.py
- agent/runtime/mission_queue.py
- provider retry behavior
- durable checkpointing
- FlowSpec v1
- idempotent execution
- existing observability architecture
- existing unittest conventions

Do not modify those existing runtime/core files in this foundation mission.

They will be wired in a later dedicated integration mission after this
foundation passes full regression.

## Required Native Foundation

Implement three focused provider-independent components.

### RetryBudget

Create a native retry budget abstraction supporting deterministic and
bounded retry accounting.

At minimum support:

- configurable maximum attempt/retry consumption
- optional time/deadline budget where appropriate
- deterministic remaining-budget calculation
- explicit consume/check semantics
- no hidden retry authority
- no sleeping
- no network calls
- no queue mutation
- no background threads
- fail-closed validation
- safe unlimited/no-op compatibility mode if required to preserve
  existing behavior later

The class must be independently testable.

Do not duplicate MissionQueue retry counters.

The budget is a policy/decision component only.

### RetryClassification

Create a deterministic native retry classification contract.

It must distinguish at minimum:

- retryable
- non_retryable
- cancelled
- deadline_exceeded
- exhausted

It should allow existing execution/provider layers to map failures into
a common native classification later.

Do not introduce provider-specific dependencies.

Do not hard-code a new network client.

Do not execute retries.

This component classifies only.

### RetryMetrics

Create a lightweight structured retry observability component.

It must provide deterministic structured records/events suitable for
existing MITIGATE observability integration later.

Capture at minimum:

- attempt number
- classification
- budget remaining where known
- backoff delay where known
- jittered delay where known
- circuit state where known
- mission/execution identity where provided

It must:

- avoid secrets
- avoid network I/O
- avoid external metrics dependencies
- avoid global mutable state
- remain safe for unit testing
- support provider-independent structured output

## Compatibility Requirements

The foundation must remain compatible with:

- existing CircuitBreaker
- existing retry engines
- MissionQueue retry semantics
- BackgroundWorker retry semantics
- durable checkpointing
- FlowSpec v1
- idempotent execution
- Python 3.12
- unittest discovery
- provider independence
- GitHub portability

Do not change current production retry behavior in this mission.

## Security / Safety

Do not:

- install packages
- modify requirements
- access secrets
- access .env files
- make network calls
- create external services
- import Ruflo
- copy Ruflo code
- add Redis
- add Kafka
- add SQS
- add Celery
- modify systemd
- modify TechnologyRegistry
- modify production runtime data

## Tests

Provide comprehensive unittest coverage.

Test RetryBudget at minimum for:

- valid bounded budget
- deterministic remaining count
- consumption
- exhaustion
- invalid negative values
- boolean/integer edge cases
- unlimited compatibility mode if implemented
- deadline/time budget behavior if implemented
- deterministic behavior

Test RetryClassification at minimum for:

- all supported classifications
- invalid inputs
- deterministic classification
- provider-neutral metadata
- cancellation/deadline distinction
- retryable/non-retryable distinction

Test RetryMetrics at minimum for:

- deterministic structured event generation
- optional fields
- identity preservation
- no mutation of inputs
- safe handling of missing optional values
- serialization-safe output
- no secret-bearing arbitrary payload storage

## Foundation Report

Generate a machine-readable implementation report containing:

- mission_id
- architecture_source
- components_created
- existing_components_reused
- production_wiring_performed
- tests_added
- compatibility_validation
- risks_remaining
- phase_b2_integration_required
- recommended_phase_b2_files
- external_runtime_dependency
- provider_independence_preserved

Set:

production_wiring_performed = false

Set:

phase_b2_integration_required = true

recommended_phase_b2_files must identify the smallest exact existing
runtime files that should be modified in the later integration mission.

Do not speculate broadly.

Inspect the repository and make that recommendation based on actual
interfaces created here.

## Deliverables

agent/resilience/retry_budget.py
agent/resilience/retry_classification.py
agent/observability/retry_metrics.py
agent/tests/test_retry_budget.py
agent/tests/test_retry_classification.py
agent/tests/test_retry_metrics.py
docs/technology/evaluations/ruflo/3.37.0-retry-policy-foundation.json

## Validation

The Mission Runner will perform full repository unittest validation.

Additionally ensure:

- all new Python modules compile
- all new unit tests pass
- existing tests remain passing
- no production wiring has changed
- no external dependency was introduced
- no Ruflo runtime dependency exists
- all files remain deterministic and provider-independent

## Git Requirements

Use the Mission Runner branch.

After validation:

- stage only the allowed deliverables and mission file
- commit
- push the mission branch

Do not manually modify main.

Allow the existing production Mission Controller / GitReviewEngine to
apply its normal review policy.

## Success

The completed work must establish a safe native retry-policy foundation
that can be integrated later without creating a competing retry system.
