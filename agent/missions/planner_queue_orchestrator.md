Mission: Build Planner and Queue Orchestrator

Goal

Create a small reusable multi-project orchestrator that accepts an approved request context, invokes the AI Planner, validates the resulting plan, converts plan steps into project-scoped missions, and enqueues them deterministically.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Integrate only through dependency-injected public interfaces.
- Fully typed and compatible with Python 3.12.
- Do not perform request gating in this module.
- Do not execute missions directly.
- Do not run Background Worker or Autonomous Controller.

Approved Request Context

Input must contain:

- request_id
- project_id
- conversation_id
- provider_id
- model_id
- task_type
- user_message
- upload_ids
- created_at
- project_context
- warning

Validation

- Input must represent an already accepted request.
- request_id, project_id, and conversation_id must be strictly validated.
- project_context must belong to project_id.
- provider_id and model_id must be non-empty valid identifiers.
- task_type must be supported.
- user_message must be a non-empty string.
- upload_ids must be a list of valid identifiers.
- Unknown fields must be rejected.
- Cross-project references must be rejected.
- Never execute or interpret shell commands from user_message or payloads.

Dependencies

Inject public interfaces for:

- AI Planner
- Mission Queue resolver
- identifier generator
- clock
- event sink

Do not instantiate real services inside this module.

Planner Input

Pass a deterministic planner input containing:

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

Planner Output

Planner output must contain:

- plan_id
- request_id
- project_id
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

- plan_id must be valid and non-empty.
- request_id must equal the approved request_id.
- project_id must equal the approved project_id.
- steps must be a non-empty list.
- step_id values must be unique.
- Dependencies must refer only to steps in the same plan.
- Self-dependencies must be rejected.
- Circular dependencies must be rejected.
- Cross-project references must be rejected.
- Unknown fields must be rejected.
- priority must be an integer.
- task_type must be supported.
- payload must be a JSON-safe dictionary.
- Raw shell-command payloads must be rejected.
- Payloads containing executable command keys such as shell, command, cmd, bash, powershell, or subprocess must be rejected.
- Never use eval, exec, compile, dynamic imports, or shell execution.

Mission Conversion

Each validated plan step must become one queue mission containing:

- mission_id
- project_id
- request_id
- conversation_id
- plan_id
- step_id
- title
- description
- task_type
- provider_id
- model_id
- dependencies
- priority
- payload
- status
- created_at

Requirements

- Every mission must belong to exactly one project.
- mission_id values must be unique.
- Mission dependencies must reference generated mission_ids, not raw step_ids.
- Mission dependency conversion must remain within the same plan.
- Initial mission status must be pending.
- Mission generation must be deterministic.
- Generated mission order must be dependency-safe.

Queue Selection

- Resolve the Mission Queue using project_id and project_context.
- Never use another project's queue.
- Reject missing or mismatched queue resolution.
- Queue paths must originate from the approved project_context.
- Do not construct unrestricted filesystem paths from request content.

Queue Enqueue Behavior

- Prefer atomic batch enqueue when the queue supports it.
- If batch enqueue is unavailable, validate all missions before the first enqueue.
- Non-atomic enqueue must occur in deterministic topological order.
- Stable tie-breaking must use priority and step_id.
- Independent steps with equal priority must be ordered by step_id.
- Absence of batch support must not cause rejection.
- Successful enqueue of all missions must return accepted=true.
- Duplicate mission identifiers must be rejected before enqueue.
- If validation fails, enqueue nothing.
- If an actual enqueue operation fails, return queue_failed.
- Never execute missions after enqueue.

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
- queue_failed

Security and Privacy

- Never return secrets or credential references.
- Never expose environment-variable values.
- Never include authorization headers.
- Never return unrestricted filesystem paths.
- Never log full user messages.
- Never log uploaded content.
- Never return raw planner or queue exceptions.
- Convert dependency exceptions to safe error codes.
- Never persist prompts or completions in this module.

Structured Events

Emit safe deterministic events for:

- planner_started
- planner_failed
- plan_created
- plan_rejected
- missions_generated
- missions_enqueued
- queue_failed
- orchestration_completed

Events may contain safe identifiers, counts, task type, provider, model, and status only.

Public Interface

Provide PlannerQueueOrchestrator with:

- process_approved_request(approved_request)
- validate_approved_request(approved_request)
- validate_plan(plan, approved_request)
- status()
- latest_events(limit, project_id=None)

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake Planner, Queue resolver, atomic Queue, non-atomic Queue, clock, identifier generator, and event sink.
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

- Test successful planner and atomic queue flow.
- Test successful non-atomic queue flow.
- Test planner failure.
- Test empty plan rejection.
- Test duplicate step rejection.
- Test unknown dependency rejection.
- Test self-dependency rejection.
- Test circular dependency rejection.
- Test cross-project plan rejection.
- Test request_id mismatch rejection.
- Test project_id mismatch rejection.
- Test raw shell payload rejection.
- Test unknown payload command-key rejection.
- Test deterministic mission identifiers.
- Test deterministic dependency conversion.
- Test deterministic topological ordering.
- Test stable priority tie-breaking.
- Test duplicate mission rejection.
- Test queue resolution failure.
- Test queue enqueue failure.
- Test no partial enqueue after validation failure.
- Test project-scoped queue selection.
- Test result redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/planner_queue_orchestrator.py
- agent/tests/test_planner_queue_orchestrator.py
