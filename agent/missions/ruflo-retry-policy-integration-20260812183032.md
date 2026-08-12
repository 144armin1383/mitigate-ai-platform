# MITIGATE Native Retry Policy Production Integration

Mission ID: ruflo-retry-policy-integration-20260812183032
Request ID: ruflo-retry-policy-integration-20260812183032
Task Type: backend

## Objective

Integrate the already validated MITIGATE-native retry policy foundation
into the existing production execution architecture with the smallest
safe and backwards-compatible change.

The foundation already exists on main:

- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py

Architecture source:

docs/technology/evaluations/ruflo/3.37.0-deferred-capability-review.json

Foundation source:

docs/technology/evaluations/ruflo/3.37.0-retry-policy-foundation.json

The foundation review recommended integrating through:

- agent/resilience/capability_kernel.py
- agent/runtime/background_worker.py
- agent/runtime/mission_queue.py

Inspect the actual repository before modifying anything.

Do not assume all three files require large changes.

Keep modifications minimal.

## Core Integration Goals

Integrate:

1. RetryBudget
2. RetryClassification
3. RetryMetrics

with the existing runtime without creating a competing retry system.

MITIGATE already has:

- MissionQueue retry accounting
- BackgroundWorker retry transitions
- existing retry/backoff behavior
- CircuitBreaker
- durable checkpoints
- idempotent execution
- execution reporting
- retry-related tests

Reuse them.

Do not duplicate them.

==================================================
RETRY BUDGET INTEGRATION
==================================================

The native RetryBudget must complement existing MissionQueue retry
accounting rather than replace it.

Requirements:

- Existing max_retries and attempts_done semantics remain authoritative.
- Existing mission persistence format must remain backwards compatible.
- Existing queued missions must continue loading without migration.
- A retry budget must not consume an extra retry beyond existing semantics.
- Process interruption recovery must not accidentally consume retry budget.
- Existing retrying -> pending/running transitions must remain deterministic.
- No duplicate retry counters.
- No hidden retry authority.

If RetryBudget can be used as a decision/view over existing counters,
prefer that over adding new persisted queue fields.

Do not introduce a database migration.

==================================================
RETRY CLASSIFICATION INTEGRATION
==================================================

Integrate native RetryClassification at the narrowest existing execution
boundary where runtime/controller outcomes are mapped to queue transitions.

Requirements:

- Preserve all current controller status behavior.
- Do not change successful mission behavior.
- Do not classify arbitrary exceptions as retryable without evidence.
- Preserve current exhausted behavior.
- Preserve cancellation semantics where already present.
- Preserve deadline behavior where already present.
- Fail closed for unknown classifications.
- Keep provider-specific details outside the core classification contract.

Do not replace the existing controller.

==================================================
RETRY METRICS INTEGRATION
==================================================

Emit structured retry observability using the existing runtime event/log
mechanisms.

Do not create:

- a metrics server
- network calls
- Prometheus dependency
- external telemetry dependency
- global mutable metrics storage

Retry events should be useful for debugging and audit and should include
only safe structured metadata.

Do not emit secrets or arbitrary exception payloads.

Where available include:

- mission_id
- execution_id
- attempt
- classification
- retries remaining
- backoff delay
- jittered delay
- circuit state

==================================================
CAPABILITY KERNEL
==================================================

Review agent/resilience/capability_kernel.py.

Integrate the retry foundation only where it naturally belongs.

Do not replace:

- CircuitBreaker
- CapabilityRegistry
- FallbackRouter
- capability discovery

If existing retry/backoff abstractions overlap with the new foundation,
adapt or reuse rather than duplicate.

Maintain public compatibility with existing callers and tests.

==================================================
BACKGROUND WORKER
==================================================

Review agent/runtime/background_worker.py.

Requirements:

- Preserve durable checkpoint lifecycle.
- Preserve stable execution identity.
- Preserve execution reporter behavior.
- Preserve lifecycle hooks.
- Preserve queue transitions.
- Preserve controller semantics.
- Preserve retries after failure.
- Preserve SIGTERM/restart behavior.
- Preserve current CLI compatibility.
- Do not require a new CLI flag for normal operation.
- Do not change production systemd configuration.

Retry integration should be native and safe by default.

==================================================
MISSION QUEUE
==================================================

Review agent/runtime/mission_queue.py.

Requirements:

- Preserve persistence format compatibility.
- Preserve atomic writes and locks.
- Preserve duplicate mission protection.
- Preserve dependency scheduling.
- Preserve stale-running recovery.
- Preserve existing retry budget semantics.
- Do not introduce a new queue backend.
- Do not add external infrastructure.
- Do not change existing queue file data format unless absolutely necessary.

Prefer no persistence schema change.

==================================================
REQUIRED INTEGRATION TESTING
==================================================

Add comprehensive integration tests covering at minimum:

- existing retry semantics remain unchanged
- RetryBudget matches MissionQueue retry counters
- retry exhaustion is deterministic
- no extra retry is consumed
- successful missions remain unaffected
- non-retryable result transitions correctly
- retryable result transitions correctly
- exhausted result transitions correctly
- retry classification remains deterministic
- retry metrics are emitted once per retry decision
- retry metric content is structured and safe
- checkpoint execution identity remains unchanged
- retrying missions remain replay-safe
- idempotent execution remains compatible
- existing mission persistence still loads
- legacy queue records require no migration
- worker restart/recovery behavior remains valid
- no external dependency is required

Use repository unittest conventions.

==================================================
REGRESSION SAFETY
==================================================

Do not modify:

- FlowSpec behavior
- durable checkpoint format
- idempotent execution identity
- TechnologyRegistry
- production systemd
- runtime API contracts unrelated to retry
- provider contracts unless absolutely required

Do not install packages.

Do not import Ruflo.

Do not copy Ruflo code.

Do not add Redis, Kafka, SQS, Celery, or another runtime service.

==================================================
PRODUCTION ACTIVATION BOUNDARY
==================================================

This mission may wire the retry policy into the native runtime code,
but must NOT:

- modify live production queue data
- modify live technology registry
- mark retry_backoff_policy adopted
- restart production services
- alter systemd
- perform a live retry smoke mission

Those actions remain part of final human-controlled validation.

==================================================
REPORT
==================================================

Create:

docs/technology/evaluations/ruflo/3.37.0-retry-policy-integration.json

The report must include:

- mission_id
- foundation_source
- files_modified
- tests_added
- integration_points
- RetryBudget integration behavior
- RetryClassification integration behavior
- RetryMetrics integration behavior
- backwards_compatibility
- persistence_format_changed
- production_runtime_data_changed
- external_runtime_dependency
- provider_independence_preserved
- full_test_result
- remaining_risks
- final_live_validation_required

Required values:

production_runtime_data_changed = false

external_runtime_dependency = false

provider_independence_preserved = true

final_live_validation_required = true

==================================================
DELIVERABLES
==================================================

## Deliverables

agent/resilience/capability_kernel.py
agent/runtime/background_worker.py
agent/runtime/mission_queue.py
agent/tests/test_retry_policy_integration.py
agent/tests/test_background_worker_retry_policy.py
docs/technology/evaluations/ruflo/3.37.0-retry-policy-integration.json

## Validation

Run relevant targeted tests.

Run:

python -m unittest discover -v agent/tests

Run:

git diff --check

Inspect the complete diff.

Ensure all existing tests pass.

Ensure Python 3.12 compatibility.

Ensure no unrelated files change.

Ensure no Ruflo dependency exists.

## Git

Use the Mission Runner branch.

Commit validated changes.

Push the mission branch.

Do not manually merge main.

## Success Criteria

A successful result must demonstrate:

- retry policy foundation integrated
- existing queue retry semantics preserved
- durable checkpoints preserved
- idempotent execution preserved
- no migration required
- no external runtime dependency
- provider independence preserved
- full test suite passing
