Mission: Build Application Composition Root

Goal

Create a production-oriented application composition root that wires the existing multi-project agent services together through explicit dependency injection.

Scope

- Build composition and service wiring only.
- Do not build a web UI.
- Do not add CLI commands.
- Do not start background threads or worker loops.
- Do not call external AI providers.
- Do not execute Git or shell commands.
- Do not modify requirements.txt.
- Use Python standard library only.
- Fully typed and compatible with Python 3.12.

Existing Components

The composition root must wire existing public interfaces for:

- ProjectRegistry
- AI Chat Gateway
- Provider Model Registry
- Provider Budget Config Store
- Provider Budget Limit Evaluator
- Provider Rate Limiter
- Provider Usage Ledger
- RequestGateSelector
- PlanValidatorMissionBuilder
- QueueEnqueueCoordinator
- PlannerQueueFlowCoordinator
- UnifiedRequestFlowService
- ExecutionReportWriter
- ExecutionOutcomeCoordinator
- Mission Queue
- Background Worker
- Autonomous Controller
- Private Admin API

Do not reimplement these components.

Architecture

Create an ApplicationContainer that:

- owns initialized service instances
- exposes explicit typed attributes
- resolves project-scoped services safely
- supports dependency injection and test overrides
- avoids global mutable state
- does not create hidden singletons
- does not perform network access during construction
- does not start threads or processes during construction

Configuration

Support an ApplicationConfig containing:

- data_root
- repository_root
- default_project_id
- default_branch
- environment_name
- provider_registry_path
- project_registry_path
- usage_ledger_path
- budget_store_path
- rate_limiter_path
- execution_report_path
- queue_root
- event_root
- log_level

Validation

- All configured paths must be safe and normalized.
- Relative paths must resolve under data_root where applicable.
- Reject path traversal.
- Reject symbolic-link escape.
- Reject invalid project identifiers.
- Reject invalid environment names.
- Reject unknown configuration fields.
- Do not read credentials from configuration files in this module.
- Secrets must remain referenced externally.

Construction Order

Build services in this exact dependency-safe order:

1. ApplicationConfig
2. ProjectRegistry
3. Provider Model Registry
4. Provider Usage Ledger
5. Provider Budget Config Store
6. Provider Budget Limit Evaluator
7. Provider Rate Limiter
8. AI Chat Gateway
9. PlanValidatorMissionBuilder
10. QueueEnqueueCoordinator
11. PlannerQueueFlowCoordinator
12. RequestGateSelector
13. UnifiedRequestFlowService
14. ExecutionReportWriter
15. ExecutionOutcomeCoordinator
16. Background Worker
17. Autonomous Controller
18. Private Admin API

Requirements

- Every project-scoped service must resolve by project_id.
- No service may silently fall back to another project.
- Default project may be used only when explicitly requested.
- All service references must be deterministic.
- Construction must fail fast with a safe configuration error.
- Partial construction must not leave started threads, open files, or background processes.
- Construction must be idempotent for the same config and dependency overrides.
- Test overrides must replace only the specified dependency.
- Unrelated services must still be constructed normally.
- Do not mutate supplied config or overrides.

Public Interface

Provide:

- ApplicationConfig
- ApplicationContainer
- build_application(config, overrides=None)
- validate_application_config(config)
- application_status(container)

ApplicationContainer must expose:

- config
- project_registry
- provider_registry
- usage_ledger
- budget_store
- budget_evaluator
- rate_limiter
- chat_gateway
- plan_builder
- queue_coordinator
- planner_queue_flow
- request_gate
- request_flow
- execution_report_writer
- execution_outcome_coordinator
- background_worker
- autonomous_controller
- private_admin_api

Application Status

Return safe deterministic status containing:

- environment_name
- default_project_id
- configured_projects
- constructed_services
- service_count
- ready
- warnings

Never expose:

- credentials
- API keys
- authorization headers
- environment-variable values
- unrestricted filesystem paths
- provider secrets
- raw exceptions

Dependency Overrides

Support test overrides for any constructed service.

Rules:

- overrides must be a dictionary of documented service names.
- reject unknown override names.
- use injected override instances exactly as supplied.
- do not clone or mutate overrides.
- dependencies downstream must receive the overridden instance.
- preserve construction order.
- override usage must remain deterministic.

Failure Codes

Use safe exceptions or results for:

- invalid_application_config
- unsafe_path
- unknown_project
- unsupported_override
- service_construction_failed
- dependency_cycle
- dependency_failed

Lifecycle

- Construction must not start worker loops.
- Provide container.close() for future lifecycle integration.
- close() must be idempotent.
- close() must call documented close methods on constructed services when available.
- close() must not raise raw dependency exceptions.
- No service may be closed twice.
- Construction failure must close already-created closable services in reverse order.

Events

Emit safe deterministic events for:

- application_build_started
- service_constructed
- service_override_applied
- application_build_completed
- application_build_failed
- application_close_started
- service_closed
- application_close_completed

Events may contain only safe service names, project identifiers, environment name, counts, and status.

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake factories and fake service instances.
- Do not use network access.
- Do not call real providers.
- Do not execute Git, shell commands, Worker loops, or Controller loops.
- Every generated Python file must pass py_compile.
- Tests must run from repository root using unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use dynamic code execution, dynamic imports, subprocess, or shell execution.
- Generated files must not contain the forbidden function-call pattern checked by Mission Runner.

Testing Requirements

- Test valid configuration.
- Test unknown configuration field rejection.
- Test invalid project identifier rejection.
- Test path traversal rejection.
- Test symbolic-link escape rejection.
- Test deterministic construction order.
- Test all required services constructed.
- Test service count.
- Test project-scoped dependency wiring.
- Test no cross-project fallback.
- Test one dependency override.
- Test multiple dependency overrides.
- Test unknown override rejection.
- Test downstream dependencies receive override.
- Test supplied overrides are not mutated.
- Test configuration is not mutated.
- Test construction failure cleanup.
- Test reverse-order cleanup.
- Test close idempotency.
- Test service close exceptions are sanitized.
- Test no worker or controller loop starts during construction.
- Test deterministic application status.
- Test status redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/app/application.py
- agent/tests/test_application_composition_root.py
