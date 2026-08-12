# MITIGATE Native Retry Policy Final Runtime Wiring

Mission ID: ruflo-retry-final-runtime-wiring-20260812195123
Request ID: ruflo-retry-final-runtime-wiring-20260812195123
Task Type: backend

## Objective

Complete the final native production integration path for retry_backoff_policy.

Already completed and validated:

- durable_checkpointing
- flowspec_v1
- idempotent_execution
- RetryBudget
- RetryClassification
- RetryMetrics
- RetryBudget MissionQueue projection
- RetryExecutionAdapter

The previous B2.2 architecture decision established:

core_change_required = false

Use existing safe extension architecture.

Do not modify protected runtime Core.

## Existing Components

Inspect and reuse:

- agent/resilience/retry_budget.py
- agent/resilience/retry_classification.py
- agent/resilience/retry_budget_queue_adapter.py
- agent/resilience/retry_execution_adapter.py
- agent/observability/retry_metrics.py

Inspect read-only:

- agent/runtime/background_worker.py
- agent/runtime/mission_queue.py
- agent/runtime/production_lifecycle_dispatcher.py
- agent/runtime/production_execution_reporter.py
- agent/runtime/production_mission_controller.py
- agent/resilience/capability_kernel.py

## Architecture Requirements

MissionQueue remains the sole retry-state authority.

The existing runtime/controller remains the sole retry execution authority.

The final integration MUST NOT:

- create another retry loop
- call sleep
- consume retry attempts
- increment attempts_done
- decrement retry budgets
- execute missions
- mutate MissionQueue
- bypass controller decisions
- duplicate execution reports
- mutate checkpoint identity
- mutate execution identity
- add network dependencies
- add external runtime dependencies

The integration is subordinate to existing runtime execution.

## Core Protection

Do NOT modify:

- agent/runtime/background_worker.py
- agent/runtime/mission_queue.py
- agent/runtime/production_mission_controller.py
- agent/ai/mission_runner.py
- agent/ai/autonomous_controller.py
- systemd configuration

Do not weaken CORE_PATH_LOCKED.

If actual final wiring cannot be completed without protected Core modification:

DO NOT modify Core.

Produce the report with:

wiring_completed = false
core_change_required = true

and identify the exact minimal target.

## Required Implementation

Create exactly:

agent/resilience/retry_runtime_integration.py

This component must provide the final provider-independent integration layer
using existing read-only runtime/lifecycle inputs.

Create tests:

agent/tests/test_retry_runtime_integration.py

Create report:

docs/technology/evaluations/ruflo/3.37.0-retry-final-runtime-wiring.json

Do not create other production files.

## Functional Requirements

The integration must demonstrate compatibility with:

- RetryClassifier
- RetryBudget queue projection
- RetryExecutionAdapter
- RetryMetrics
- MissionQueue retry state
- execution_id
- mission_id
- attempt identity
- checkpoint correlation
- idempotent execution

It must produce deterministic, JSON-serializable integration output.

It must fail closed.

Integration/observability failure must never:

- grant retry authority
- consume retry authority
- change mission state
- crash the runtime
- corrupt queue state
- corrupt checkpoints

## Tests

Use standard-library unittest only.

Cover at minimum:

- retryable lifecycle projection
- non-retryable lifecycle projection
- exhausted lifecycle projection
- cancelled projection
- deadline-exceeded projection
- MissionQueue authority preservation
- execution identity preservation
- checkpoint identity preservation
- deterministic output
- JSON serialization
- no mutation
- fail-closed behavior
- no retry consumption
- no extra retry authority
- provider independence
- no sleep
- no network behavior

## Report

The report must contain:

- mission_id
- integration_scope
- extension_point_found
- extension_point_used
- wiring_completed
- core_change_required
- core_change_reason
- exact_core_change_target
- runtime_file_modified
- retry_state_authority
- retry_execution_authority
- retry_classification_integrated
- retry_metrics_integrated
- retry_budget_projection_integrated
- retry_execution_adapter_integrated
- checkpoint_identity_preserved
- execution_identity_preserved
- provider_independence_preserved
- external_runtime_dependency
- production_runtime_data_changed
- full_test_result
- production_smoke_result
- remaining_work

Required invariants:

retry_state_authority = "MissionQueue"
retry_execution_authority = "existing_runtime_controller"
checkpoint_identity_preserved = true
execution_identity_preserved = true
provider_independence_preserved = true
external_runtime_dependency = false
production_runtime_data_changed = false

If successful:

wiring_completed = true
core_change_required = false
remaining_work = "final native availability validation and registry adoption only"

If protected Core modification is truly required:

wiring_completed = false
core_change_required = true

and provide the exact minimal target.

## Deliverables

agent/resilience/retry_runtime_integration.py
agent/tests/test_retry_runtime_integration.py
docs/technology/evaluations/ruflo/3.37.0-retry-final-runtime-wiring.json

## Validation

Run:

python -m py_compile   agent/resilience/retry_runtime_integration.py   agent/tests/test_retry_runtime_integration.py

Run targeted unittest coverage.

Then run:

python -m unittest discover -s agent/tests -p 'test_*.py' -v

Run:

git diff --check

No protected Core runtime files may change.

No external dependency may be introduced.

## Git

Use the Mission Runner branch.

Commit validated work.

Push the mission branch.

Do not modify main directly.

## Success Criteria

retry_backoff_policy has a validated MITIGATE-native final integration path,
without Ruflo runtime dependency and without duplicate retry authority.
