Mission: Build Request Gate and Model Selector

Goal

Create a small multi-project request gate that validates one AI request, resolves its project, verifies conversation and upload ownership, selects a provider and model, and applies budget and rate-limit controls.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Use dependency-injected public interfaces only.
- Fully typed and compatible with Python 3.12.
- Do not invoke the Planner.
- Do not enqueue missions.
- Do not execute the Worker or Controller.

Request Fields

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

- Reject unknown fields.
- request_id must be valid and unique.
- project_id must resolve through Project Registry.
- conversation_id must belong to the same project.
- Every upload_id must belong to the same project.
- Reject cross-project conversation and upload references.
- user_message must be a non-empty string.
- requested_task_type must be supported.
- Provider and model requests are optional.
- Reject control characters in identifiers.
- Never execute or interpret raw shell commands from message content.

Dependencies

Inject interfaces for:

- Project Registry
- AI Chat Gateway
- Provider Model Registry
- Provider Budget Limit Evaluator
- Provider Rate Limiter
- clock
- event sink

Processing Order

1. Validate request schema.
2. Resolve ProjectContext.
3. Validate conversation ownership.
4. Validate upload ownership.
5. Resolve task type.
6. Select provider and model.
7. Apply budget preflight.
8. Apply atomic rate-limit check and registration.
9. Return a safe accepted or blocked result.

Model Selection

- Explicit provider and model may be used only when allowed for the project and task.
- Otherwise use Provider Model Registry selection.
- Reject disabled, unavailable, deprecated, or incompatible models.
- Requests with uploads must use a vision-capable model.
- Tool-required tasks must use a tool-capable model.
- Never select a model from another project.
- Return no_model_available when selection fails.

Budget and Rate Controls

- Budget check must occur before rate-limit registration.
- Budget block must stop processing.
- Soft budget warning must allow processing.
- Rate-limit block must stop processing.
- Do not record provider usage.
- Do not call Planner when blocked.
- Do not enqueue anything.

Accepted Result

Return:

- accepted
- request_id
- project_id
- conversation_id
- provider_id
- model_id
- task_type
- warning
- blocked_reason
- created_at
- project_context

project_context must contain only safe fields needed by the next orchestrator stage.

Failure Codes

- invalid_request
- unknown_project
- cross_project_reference
- no_model_available
- budget_blocked
- rate_limit_blocked
- dependency_failed

Security

- Never expose secrets.
- Never expose environment-variable values.
- Never return unrestricted filesystem paths.
- Never log complete user messages.
- Never log uploaded content.
- Never return raw dependency exceptions.
- Convert exceptions to safe error codes.

Events

Emit safe events for:

- request_received
- request_rejected
- model_selected
- budget_warning
- budget_blocked
- rate_limit_blocked
- request_gate_accepted

Public Interface

Provide RequestGateSelector with:

- process_request(request)
- validate_request(request)
- status()
- latest_events(limit, project_id=None)

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Use unittest.mock and TemporaryDirectory.
- Use fake Project Registry, Chat Gateway, Provider Registry, Budget Evaluator, Rate Limiter, clock, and event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git, Planner, Queue, Worker, or Controller.
- Every Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test successful request acceptance.
- Test explicit model selection.
- Test default model selection.
- Test unknown project rejection.
- Test cross-project conversation rejection.
- Test cross-project upload rejection.
- Test empty message rejection.
- Test invalid task type rejection.
- Test no-model-available result.
- Test vision capability enforcement.
- Test budget block.
- Test soft budget warning.
- Test rate-limit block.
- Test blocked requests do not continue.
- Test deterministic safe result.
- Test result redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/request_gate_selector.py
- agent/tests/test_request_gate_selector.py
