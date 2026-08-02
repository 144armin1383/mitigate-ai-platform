Mission: Build End-to-End Runtime Integration Tests

Goal

Create an end-to-end integration test suite that verifies the complete in-process request and execution lifecycle across the existing Mitigate AI platform components.

Scope

- Generate integration tests only.
- Do not modify production modules.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use Python standard library unittest only.
- Fully compatible with Python 3.12.
- Do not use real network access.
- Do not call real AI providers.
- Do not execute Git or shell commands.
- Do not start real worker, controller, or API threads.

Existing Components Under Test

Exercise the existing public interfaces for:

- ApplicationConfig
- ApplicationContainer
- build_application
- RuntimeConfig
- RuntimeService
- RequestGateSelector
- UnifiedRequestFlowService
- PlannerQueueFlowCoordinator
- PlanValidatorMissionBuilder
- QueueEnqueueCoordinator
- ExecutionOutcomeCoordinator
- ExecutionReportWriter
- ProviderUsageLedger
- ProviderRateLimiter
- ProviderBudgetLimitEvaluator
- ProjectRegistry

Do not reimplement these components.

Integration Architecture

Use deterministic in-memory or temporary-directory test doubles for:

- Project Registry data
- Provider Model Registry
- Budget Config Store
- Budget Evaluator
- Rate Limiter
- Planner
- Mission Queue
- Mission Status Writer
- Provider Usage Ledger
- Execution Report Writer
- Background Worker
- Autonomous Controller
- Private Admin API
- Clock
- Identifier generators
- Event sinks

Use real existing orchestration and runtime service classes wherever possible.

Primary Request Flow

Verify:

1. RuntimeService starts successfully.
2. ApplicationContainer is built.
3. A valid request enters RequestGateSelector.
4. Project, conversation, upload, provider, model, budget, and rate-limit validation succeed.
5. Planner receives deterministic input.
6. Planner returns a valid plan.
7. PlanValidatorMissionBuilder validates the plan.
8. Plan steps become deterministic mission objects.
9. QueueEnqueueCoordinator enqueues missions in dependency-safe order.
10. Unified request result reports accepted=true.
11. mission_ids match the actual queue order.
12. No request or mission crosses project boundaries.

Primary Execution Flow

Verify:

1. A queued mission is marked running by the fake mission status writer.
2. ExecutionOutcomeCoordinator receives a completed execution outcome.
3. Mission status changes to completed.
4. Provider usage is recorded exactly once.
5. ExecutionReportWriter persists one safe report.
6. Duplicate execution submission does not create duplicate status updates, usage records, or reports.
7. Runtime result remains deterministic.
8. Sensitive metadata remains redacted.

Failure Flow Coverage

Test:

- unknown project request
- cross-project conversation
- cross-project upload
- no compatible model
- budget block
- rate-limit block
- planner failure
- invalid plan
- circular dependency
- queue resolution failure
- queue enqueue failure
- runtime not running
- mission not found
- invalid mission status transition
- usage recording failure
- report persistence failure
- duplicate execution
- invalid execution outcome
- startup failure
- application-not-ready failure

Project Isolation

- Configure at least two independent projects.
- Give each project its own queue reference.
- Give each project distinct provider/model assignment.
- Give each project distinct budget and rate-limit state.
- Requests for one project must never use another project's queue, provider assignment, budget, usage, reports, or events.
- Cross-project references must be rejected before side effects occur.

Determinism

- Use fixed UTC timestamps.
- Use deterministic request, plan, mission, usage, and execution identifiers.
- Repeated equivalent runs must produce equivalent safe results.
- Queue ordering must remain stable.
- JSON serialization checks must be deterministic.

Security and Privacy

Never expose in results or events:

- API keys
- credentials
- authorization headers
- environment-variable values
- full user messages
- uploaded content
- raw provider responses
- raw exceptions
- unrestricted filesystem paths

Sensitive keys must remain present with value "[redacted]" where applicable.

Runtime Lifecycle

Test:

- start
- repeated start
- request processing while running
- execution outcome processing while running
- explicit component activation
- reverse-order shutdown
- repeated stop
- close idempotency
- context-manager lifecycle
- no automatic worker/controller/API startup by default
- no leaked threads or processes

Concurrency

- Test concurrent equivalent request submissions safely.
- Test concurrent duplicate execution outcomes.
- Test only one runtime container build occurs.
- Test only one duplicate execution is persisted.
- Use bounded joins and timeouts.
- Tests must never hang.

Repository Safety

- Use TemporaryDirectory for test data.
- Do not modify production data.
- Do not create persistent temporary directories in repository root.
- Clean up all temporary files.
- Do not modify unrelated files.
- Tests must leave git working tree clean when run from a clean checkout.

Test Policy

- Use unittest only.
- Never use pytest.
- Use unittest.mock.
- Do not modify sys.path.
- Use repository-root imports.
- Do not use dynamic code execution, dynamic imports, subprocess, os.system, or shell execution.
- Generated test code must not contain the forbidden function-call pattern checked by Mission Runner.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Testing Requirements

- Test full successful request-to-queue flow.
- Test full successful execution-outcome flow.
- Test duplicate execution idempotency.
- Test two-project isolation.
- Test deterministic queue ordering.
- Test deterministic mission identifiers.
- Test exact usage mapping.
- Test safe execution report persistence.
- Test runtime lifecycle.
- Test request failure propagation.
- Test execution failure propagation.
- Test startup failure cleanup.
- Test sensitive result redaction.
- Test sensitive event redaction.
- Test no persistent temporary files.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/tests/test_end_to_end_runtime_integration.py
