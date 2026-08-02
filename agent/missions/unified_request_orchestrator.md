Mission: Build Unified Request Orchestrator

Goal

Create a small reusable multi-project request orchestrator that accepts one project-scoped AI request, validates it, selects the configured provider and model, applies budget and rate-limit checks, invokes the planner, and enqueues the resulting missions.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Integrate only through dependency-injected public interfaces.
- Fully typed and compatible with Python 3.12.
- Do not build a web UI in this mission.
- Do not execute missions directly in this mission.

Request Input

Each request must contain:

- request_id
- project_id
- conversation_id
- user_message
- upload_ids
- requested_task_type
- requested_provider_id
- requested_model_id
- created_at
- metadata

Validation

- request_id must be unique and strictly validated.
- project_id must resolve through the injected Project Registry.
- conversation_id must belong to the same project.
- upload_ids must belong to the same project.
- Cross-project conversation or upload references must be rejected.
- user_message must be a non-empty string.
- requested_task_type must be supported.
- requested_provider_id and requested_model_id are optional.
- Unknown fields must be rejected.
- Reject control characters in identifiers.
- Never execute raw shell commands from user input.
- Never treat message content as trusted code.

Dependencies

Inject public interfaces for:

- Project Registry
- AI Chat Gateway
- Provider Model Registry
- Provider Budget Limit Evaluator
- Provider Rate Limiter
- AI Planner
- Mission Queue
- clock
- identifier generation
- event sink

Do not instantiate real services inside this module.

Processing Flow

The orchestrator must process a request in this exact order:

1. Validate the request schema.
2. Resolve ProjectContext.
3. Validate conversation ownership.
4. Validate upload ownership.
5. Resolve task type.
6. Select provider and model.
7. Apply budget preflight.
8. Apply rate-limit check and atomic registration.
9. Invoke AI Planner.
10. Validate the generated plan.
11. Convert plan steps into project-scoped queue missions.
12. Enqueue all missions atomically where supported.
13. Return a safe structured result.

Provider and Model Selection

- Use an explicitly requested provider and model only when allowed for the selected project and task.
- Otherwise use Provider Model Registry selection.
- Disabled, unavailable, deprecated, or incompatible models must not be selected.
- Vision requests with uploads must use a vision-capable model.
- Tool-requiring tasks must use a tool-capable model when required.
- Return a safe no-model-available result when selection fails.
- Never silently select a model from another project.

Budget and Rate Controls

- Budget check must occur before planner execution.
- Rate-limit registration must occur before planner execution.
- A blocked budget result must stop processing.
- A blocked rate-limit result must stop processing.
- Soft budget warnings must not block.
- Preflight must not record provider usage.
- Do not invoke Planner when the request is blocked.
- Do not enqueue missions when the request is blocked.

Planner Integration

The planner input must contain:

- project_id
- repository_root
- default_branch
- request_id
- conversation_id
- user_message
- upload_ids
- task_type
- provider_id
- model_id
- policy_profile
- project_type

Planner output must contain:

- plan_id
- project_id
- request_id
- summary
- steps

Each step must contain:

- step_id
- title
- description
- dependencies
- priority
- task_type
- payload

Plan Validation

- plan project_id must equal request project_id.
- plan request_id must equal request request_id.
- step identifiers must be unique.
- Dependencies must refer only to steps in the same plan.
- Self-dependencies and circular dependencies must be rejected.
- Empty plans must be rejected.
- Raw shell-command payloads must be rejected.
- Cross-project references must be rejected.

Queue Integration

Each queued mission must include:

- mission_id
- project_id
- request_id
- conversation_id
- plan_id
- step_id
- task_type
- provider_id
- model_id
- dependencies
- priority
- payload
- status

Requirements

- Every mission must belong to exactly one project.
- Mission dependencies must remain within the same project and plan.
- Queue paths must come from ProjectContext.
- Enqueue ordering must be deterministic.
- Partial enqueue must be avoided.
- If atomic batch enqueue is unavailable, validate every mission before the first enqueue.
- Duplicate mission identifiers must be rejected.
- The orchestrator must never execute Background Worker or Autonomous Controller directly.

Result

Return a deterministic structured result containing:

- accepted
- request_id
- project_id
- conversation_id
- provider_id
- model_id
- task_type
- plan_id
- mission_ids
- warning
- blocked_reason
- created_at

Failure Results

Return safe structured failures for:

- invalid_request
- unknown_project
- cross_project_reference
- no_model_available
- budget_blocked
- rate_limit_blocked
- planner_failed
- invalid_plan
- queue_failed

Security and Privacy

- Never return API keys or secret references.
- Never include environment variable values.
- Never include authorization headers.
- Never log full message content.
- Never log uploaded file contents.
- Never expose unrestricted filesystem paths.
- Never persist prompts or completions in this module.
- Never include raw provider exceptions.
- Convert dependency exceptions to safe error codes.

Structured Events

Emit deterministic safe events for:

- request_received
- request_rejected
- model_selected
- budget_warning
- budget_blocked
- rate_limit_blocked
- plan_created
- missions_enqueued
- orchestration_failed

Events may include safe identifiers, task type, provider, model, counts, and status only.

Public Interface

Provide a UnifiedRequestOrchestrator class with:

- submit_request(request)
- validate_request(request)
- status()
- latest_events(limit, project_id=None)

No CLI is required in this mission.

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake Project Registry, Chat Gateway, Provider Registry, Budget Evaluator, Rate Limiter, Planner, Mission Queue, clock, identifier generator, and event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git commands.
- Do not execute Background Worker or Autonomous Controller.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test successful request orchestration.
- Test explicit model selection.
- Test default model selection.
- Test unknown project rejection.
- Test cross-project conversation rejection.
- Test cross-project upload rejection.
- Test empty message rejection.
- Test invalid task type rejection.
- Test no-model-available result.
- Test vision capability enforcement.
- Test budget blocking prevents planner execution.
- Test soft budget warning allows execution.
- Test rate-limit blocking prevents planner execution.
- Test planner failure.
- Test empty plan rejection.
- Test duplicate step rejection.
- Test unknown dependency rejection.
- Test self-dependency rejection.
- Test circular dependency rejection.
- Test cross-project plan rejection.
- Test raw shell payload rejection.
- Test deterministic mission generation.
- Test deterministic enqueue ordering.
- Test queue failure.
- Test no partial enqueue after validation failure.
- Test project-scoped queue selection.
- Test result redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/request_orchestrator.py
- agent/tests/test_request_orchestrator.py
