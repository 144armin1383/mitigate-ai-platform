Mission: Build Planner Queue Flow Coordinator

Goal

Create a small multi-project coordinator that receives an approved request, invokes the AI Planner, validates and converts the resulting plan through PlanValidatorMissionBuilder, and submits the missions through QueueEnqueueCoordinator.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use dependency-injected public interfaces only.
- Fully typed and compatible with Python 3.12.
- Do not perform request gating.
- Do not execute missions.
- Do not invoke providers, Git, Background Worker, or Autonomous Controller.

Approved Request

The input must contain:

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

Validation

- accepted must be true.
- Reject unknown fields.
- Identifiers must be valid non-empty strings.
- user_message must be non-empty.
- upload_ids must be a list.
- project_context must belong to project_id.
- project_context must provide repository_root, default_branch, project_type, policy_profile, and queue_reference.
- Cross-project references must be rejected.
- Never execute or interpret user content as code or shell commands.

Dependencies

Inject public interfaces for:

- AI Planner
- PlanValidatorMissionBuilder
- QueueEnqueueCoordinator
- clock
- event sink

Do not instantiate real services in this module.

Processing Order

1. Validate the approved request.
2. Build deterministic Planner input.
3. Invoke AI Planner.
4. Convert Planner exceptions into planner_failed.
5. Validate Planner output through PlanValidatorMissionBuilder.
6. Build deterministic mission objects.
7. Resolve queue_reference only from approved project_context.
8. Enqueue through QueueEnqueueCoordinator.
9. Return a safe structured result.

Planner Input

Pass:

- request_id
- project_id
- conversation_id
- repository_root
- default_branch
- project_type
- policy_profile
- provider_id
- model_id
- task_type
- user_message
- upload_ids

Planner Rules

- Do not modify Planner output before validation.
- Do not accept empty plans.
- Do not silently repair invalid plans.
- Never expose raw Planner exceptions.
- Never retry Planner inside this coordinator.
- Retry behavior belongs to the injected Planner or execution layer.

Builder Integration

- Use only public methods of PlanValidatorMissionBuilder.
- Pass the approved request context required by the builder.
- Do not regenerate mission identifiers.
- Do not reorder missions after the builder returns them.
- Preserve converted dependencies exactly.
- Builder validation failure must return invalid_plan.
- Do not enqueue anything when builder validation fails.

Queue Integration

- Use only QueueEnqueueCoordinator.enqueue().
- Pass project_id, project_context queue_reference, and the complete mission list.
- Do not access another project's queue.
- Do not enqueue directly.
- Preserve mission ordering.
- Preserve mission identifiers.
- Return queue failure codes from the coordinator safely.
- Do not claim acceptance unless queue enqueue succeeds completely.

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

Failure Codes

- invalid_approved_request
- planner_failed
- invalid_plan
- queue_resolution_failed
- unsupported_queue_interface
- queue_failed
- partial_enqueue
- dependency_failed

Security and Privacy

- Never return API keys, credentials, or secret references.
- Never expose environment-variable values.
- Never expose unrestricted filesystem paths.
- Never return authorization headers.
- Never log full user messages.
- Never log uploaded content.
- Never return raw dependency exceptions.
- Never persist prompts or completions.
- Sanitize safe result metadata recursively.

Structured Events

Emit safe events for:

- planner_flow_started
- planner_started
- planner_failed
- plan_validated
- plan_rejected
- missions_built
- queue_submission_started
- queue_submission_failed
- planner_queue_flow_completed

Events may contain only safe identifiers, counts, task type, provider, model, and status.

Public Interface

Provide PlannerQueueFlowCoordinator with:

- process(approved_request)
- validate_approved_request(approved_request)
- status()
- latest_events(limit, project_id=None)

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake Planner, fake PlanValidatorMissionBuilder, fake QueueEnqueueCoordinator, fake clock, and fake event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git, Queue implementations, Worker, or Controller directly.
- Every Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, subprocess, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test successful end-to-end planner-to-queue flow.
- Test approved=false rejection.
- Test unknown-field rejection.
- Test missing project context rejection.
- Test project-context mismatch rejection.
- Test deterministic Planner input.
- Test Planner failure.
- Test empty Planner result.
- Test builder validation failure.
- Test builder receives correct approved request.
- Test mission ordering remains unchanged.
- Test mission identifiers remain unchanged.
- Test queue coordinator receives correct project_id.
- Test queue coordinator receives correct queue_reference.
- Test queue success.
- Test queue resolution failure.
- Test unsupported queue interface result.
- Test queue failure.
- Test partial enqueue result.
- Test no enqueue after Planner failure.
- Test no enqueue after builder failure.
- Test deterministic success result.
- Test result redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/planner_queue_flow_coordinator.py
- agent/tests/test_planner_queue_flow_coordinator.py
