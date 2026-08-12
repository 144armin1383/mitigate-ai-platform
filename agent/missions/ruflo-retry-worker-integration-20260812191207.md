# MITIGATE Retry Classification and Metrics Integration

Mission ID: ruflo-retry-worker-integration-20260812191207
Request ID: ruflo-retry-worker-integration-20260812191207
Task Type: backend

## Objective

Complete Phase B2.2 by integrating the already validated native retry
classification and retry metrics components with the existing execution
lifecycle using the safest available extension mechanism.

Already completed:

- RetryBudget foundation
- RetryClassification foundation
- RetryMetrics foundation
- RetryBudget Queue Adapter
- MissionQueue remains retry-state authority

Existing components:

- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py
- agent/resilience/retry_budget_queue_adapter.py

Inspect the repository before implementation.

## Core Safety Rule

agent/runtime/background_worker.py is protected core architecture.

Do NOT modify it unless no existing extension/hook/lifecycle mechanism can
safely satisfy the integration.

First inspect for existing extension points including:

- lifecycle hooks
- execution reporter hooks
- event emitters
- controller result adapters
- observability adapters
- post-controller callbacks
- queue transition hooks

Prefer a new extension-layer adapter over core modification.

Do not weaken CORE_PATH_LOCKED.

## Required Functional Goal

Provide a native integration path that can:

- classify retry outcomes
- produce RetryClassification
- build structured RetryMetrics events
- preserve execution identity
- preserve checkpoint identity
- preserve MissionQueue retry authority
- preserve existing worker transition semantics
- avoid duplicate retry decisions
- avoid duplicate retry events

Required classifications include:

- retryable
- non_retryable
- cancelled
- deadline_exceeded
- exhausted

## Metrics

Retry metrics must be structured and safe.

Where available include:

- mission_id
- execution_id
- attempt
- classification
- retries_remaining
- backoff_delay
- jittered_delay
- circuit_state

Do not include secrets.

Do not persist arbitrary exception payloads.

Do not add an external telemetry dependency.

## Existing Runtime Inspection

Inspect read-only initially:

- agent/runtime/background_worker.py
- agent/runtime/production_execution_reporter.py
- agent/runtime/production_lifecycle_dispatcher.py
- agent/runtime/production_mission_controller.py
- agent/resilience/capability_kernel.py
- agent/resilience/retry_classification.py
- agent/observability/retry_metrics.py
- agent/resilience/retry_budget_queue_adapter.py

Inspect relevant tests.

## Preferred Architecture

If an existing extension point is sufficient, implement through a new
provider-independent adapter under one of these non-core extension areas:

- agent/resilience/
- agent/observability/

Do not create files under agent/runtime unless explicitly unavoidable and
human-approved.

## If Core Modification Is Unavoidable

Do NOT modify core in this mission.

Instead:

- produce the architecture/integration report
- set core_change_required = true
- identify the exact core file
- identify the exact minimal method/function needing modification
- explain why no extension path is sufficient
- propose exact test coverage
- do not weaken any guardrail

The mission may still complete successfully as an architecture decision.

## Deliverable Implementation

Create exactly:

agent/resilience/retry_execution_adapter.py
agent/tests/test_retry_execution_adapter.py
docs/technology/evaluations/ruflo/3.37.0-retry-worker-integration.json

If an extension-only implementation is safe, implement it.

If extension-only implementation is not sufficient, the adapter may remain
a safe reusable integration component while the report marks
core_change_required = true.

Do not generate any other production file.

## Adapter Requirements

The adapter must be:

- deterministic
- provider-independent
- side-effect controlled
- independently testable
- compatible with RetryClassification
- compatible with RetryMetrics
- compatible with RetryBudget queue adapter
- compatible with execution/checkpoint identity

It must not:

- mutate MissionQueue
- own retry state
- perform retry loops
- sleep
- call network services
- install dependencies
- alter production runtime data
- create threads
- bypass existing controller decisions

## Tests

Create:

agent/tests/test_retry_execution_adapter.py

Cover at minimum:

- retryable classification
- non-retryable classification
- exhausted classification
- cancelled classification
- deadline-exceeded classification
- deterministic event generation
- mission identity preservation
- execution identity preservation
- retry budget metadata compatibility
- no mutation of inputs
- safe optional metadata
- no duplicate retry authority
- structured serializable metrics
- no secret arbitrary payload storage

Run existing RetryClassification, RetryMetrics, RetryBudget adapter and
checkpoint/idempotency tests as regression coverage.

## Report

Create:

docs/technology/evaluations/ruflo/3.37.0-retry-worker-integration.json

The report must include:

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
checkpoint_identity_preserved = true
idempotent_execution_preserved = true
production_runtime_data_changed = false
external_runtime_dependency = false
provider_independence_preserved = true

If no core change is needed:

core_change_required = false
remaining_work must state only final live validation/adoption remains.

If core change is needed:

core_change_required = true
remaining_work must identify the minimal human-approved core integration
step required before final validation.

## Deliverables

agent/resilience/retry_execution_adapter.py
agent/tests/test_retry_execution_adapter.py
docs/technology/evaluations/ruflo/3.37.0-retry-worker-integration.json

## Validation

Run:

python -m unittest -v   agent.tests.test_retry_classification   agent.tests.test_retry_metrics   agent.tests.test_retry_budget_queue_adapter   agent.tests.test_retry_execution_adapter   agent.tests.test_checkpoint_store   agent.tests.test_idempotent_execution_contract

Then run:

python -m unittest discover -v agent/tests

Run:

git diff --check

No unrelated files may change.

Do not weaken core protection.

## Git

Use the Mission Runner branch.

Commit validated output.

Push the mission branch.

Do not modify main directly.

## Success Criteria

Phase B2.2 produces a validated native execution adapter and a definitive
answer on whether any human-approved core wiring remains necessary.
