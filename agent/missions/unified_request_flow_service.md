Mission: Build Unified Request Flow Service

Goal

Create a small reusable service that accepts one user request, processes it through RequestGateSelector, and when accepted passes the approved request to PlannerQueueFlowCoordinator.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use dependency-injected public interfaces only.
- Fully typed and compatible with Python 3.12.
- Do not call providers directly.
- Do not execute missions.
- Do not invoke Git, Background Worker, or Autonomous Controller.

Dependencies

Inject:

- RequestGateSelector
- PlannerQueueFlowCoordinator
- clock
- event sink

Do not instantiate real services inside this module.

Processing Flow

1. Accept one raw user request.
2. Pass it unchanged to RequestGateSelector.process_request().
3. If the gate rejects or blocks the request, return the gate result safely.
4. If the gate accepts the request, build the approved request required by PlannerQueueFlowCoordinator.
5. Pass the approved request to PlannerQueueFlowCoordinator.process().
6. Return the final safe result.
7. Never continue to PlannerQueueFlowCoordinator after a blocked gate result.

Approved Request Mapping

Map these fields from the gate result and original request:

- accepted
- request_id
- project_id
- conversation_id
- provider_id
- model_id
- task_type
- user_message
- upload_ids
- created_at
- warning
- project_context

Requirements

- Preserve request_id exactly.
- Preserve project_id exactly.
- Preserve conversation_id exactly.
- Preserve selected provider_id and model_id exactly.
- Preserve user_message only for the injected downstream coordinator.
- Do not include user_message in returned status, events, or logs.
- Preserve upload_ids without exposing uploaded content.
- Preserve gate warnings.
- Never allow cross-project field substitution.
- Do not silently repair malformed dependency results.

Success Result

Return:

- accepted
- request_id
- project_id
- conversation_id
- provider_id
- model_id
- task_type
- plan_id
- plan_summary
- mission_ids
- warning
- blocked_reason
- created_at

Blocked Results

Propagate documented gate failure codes unchanged:

- invalid_request
- unknown_project
- cross_project_reference
- no_model_available
- budget_blocked
- rate_limit_blocked
- dependency_failed

Planner and Queue Failures

Propagate documented PlannerQueueFlowCoordinator failure codes unchanged:

- invalid_approved_request
- planner_failed
- invalid_plan
- queue_resolution_failed
- unsupported_queue_interface
- queue_failed
- partial_enqueue
- dependency_failed

Error Boundaries

- A gate rejection must not be converted into planner_failed.
- A Planner failure must not be converted into invalid_request.
- A Queue failure must not be converted into invalid_plan.
- Preserve documented blocked_reason values from injected dependencies.
- Convert unexpected raw exceptions into dependency_failed.
- Never expose raw exceptions.

Security and Privacy

- Never return API keys or credentials.
- Never expose environment-variable values.
- Never include authorization headers.
- Never expose unrestricted filesystem paths.
- Never include full user_message in events or status.
- Never include uploaded file contents.
- Never persist prompts or completions.
- Sanitize all returned metadata recursively.
- Do not mutate the original request.

Structured Events

Emit safe deterministic events for:

- unified_request_started
- request_gate_blocked
- request_gate_accepted
- planner_queue_started
- planner_queue_failed
- unified_request_completed
- unified_request_failed

Events may contain safe identifiers, provider, model, task type, counts, warning, blocked reason, and status only.

Public Interface

Provide UnifiedRequestFlowService with:

- submit(request)
- status()
- latest_events(limit, project_id=None)

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake RequestGateSelector, fake PlannerQueueFlowCoordinator, fake clock, and fake event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git, Queue, Worker, or Controller.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, subprocess, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test successful complete request flow.
- Test gate rejection stops downstream processing.
- Test budget block propagation.
- Test rate-limit block propagation.
- Test unknown-project propagation.
- Test no-model-available propagation.
- Test approved-request field mapping.
- Test selected provider and model preservation.
- Test warning preservation.
- Test Planner failure propagation.
- Test invalid-plan propagation.
- Test queue-resolution failure propagation.
- Test queue failure propagation.
- Test partial-enqueue propagation.
- Test unexpected gate exception conversion.
- Test unexpected downstream exception conversion.
- Test original request is not mutated.
- Test deterministic success result.
- Test result redaction.
- Test event redaction.
- Test full user message is absent from events and status.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/unified_request_flow_service.py
- agent/tests/test_unified_request_flow_service.py
