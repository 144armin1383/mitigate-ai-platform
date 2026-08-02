Mission: Build Plan Validator and Mission Builder

Goal

Create a small reusable component that validates planner output and converts valid plan steps into deterministic project-scoped queue mission objects.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Fully typed and compatible with Python 3.12.
- Do not resolve queues.
- Do not enqueue missions.
- Do not execute missions.
- Do not call providers, Git, Worker, or Controller.

Approved Request Context

Input must contain:

- request_id
- project_id
- conversation_id
- provider_id
- model_id
- task_type
- created_at

Validation

- request_id, project_id, conversation_id, provider_id, and model_id must be valid non-empty identifiers.
- task_type must be supported.
- Unknown fields must be rejected.
- Cross-project references must be rejected.

Planner Output

Plan must contain:

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
- request_id must equal the approved request request_id.
- project_id must equal the approved request project_id.
- summary must be a string.
- steps must be a non-empty list.
- step identifiers must be unique.
- dependencies must be a list of step identifiers.
- dependencies may refer only to steps in the same plan.
- self-dependencies must be rejected.
- circular dependencies must be rejected.
- priority must be an integer.
- task_type must be supported.
- payload must be a JSON-safe dictionary.
- Unknown fields must be rejected.
- Raw shell-command payloads must be rejected.
- Payload keys named shell, command, cmd, bash, powershell, subprocess, executable, or script must be rejected.
- Plain descriptive strings must not be rejected merely because they mention development or command-line concepts.
- Never use dynamic code execution.

Mission Conversion

Each valid step becomes one mission containing:

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

Rules

- Generate all mission identifiers before dependency conversion.
- Convert step dependencies to generated mission identifiers.
- Every mission must remain within the approved project and plan.
- Initial status must be pending.
- Mission identifiers must be unique.
- Mission generation must be deterministic for injected identifier generation.
- No mission may contain unrestricted filesystem paths or secret values.

Ordering

Provide deterministic topological ordering of generated missions.

- Dependencies must always appear before dependants.
- Among dependency-ready missions, use priority as the first tie-breaker.
- Use step_id lexicographically as the second tie-breaker.
- The priority direction must be explicitly documented and used consistently.
- Returned mission_ids must match the deterministic order.

Public Interface

Provide a PlanValidatorMissionBuilder class with:

- validate_approved_request(approved_request)
- validate_plan(plan, approved_request)
- build_missions(plan, approved_request)
- order_missions(missions)
- status()

Failure Codes

Use safe structured exceptions or results for:

- invalid_approved_request
- invalid_plan
- duplicate_step
- unknown_dependency
- self_dependency
- circular_dependency
- unsafe_payload

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Use unittest.mock.
- Use fake clock and identifier generator.
- Do not use network, providers, Git, queues, Worker, or Controller.
- Every Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test valid plan acceptance.
- Test empty plan rejection.
- Test duplicate step rejection.
- Test unknown dependency rejection.
- Test self-dependency rejection.
- Test circular dependency rejection.
- Test request mismatch rejection.
- Test project mismatch rejection.
- Test unknown-field rejection.
- Test unsafe payload-key rejection.
- Test descriptive payload strings remain allowed.
- Test deterministic mission identifiers.
- Test deterministic dependency conversion.
- Test deterministic topological ordering.
- Test priority tie-breaking.
- Test step_id tie-breaking.
- Test dependency-before-dependant ordering.
- Test result redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/plan_validator_mission_builder.py
- agent/tests/test_plan_validator_mission_builder.py

Deterministic Dependency and Redaction Contract

Dependency Conversion

- Generate the complete step_id to mission_id mapping before converting any dependencies.
- Convert each step dependency to its corresponding mission_id.
- Converted dependency lists must be deterministic.
- After conversion, sort dependency mission identifiers lexicographically.
- Dependency ordering must not depend on input dictionary order, set iteration, hash order, or mission-generation timing.
- For step dependencies that convert to m1 and m2, the resulting list must be ["m1", "m2"].
- For injected mission identifiers X1 and X2, the resulting list must be ["X1", "X2"].
- Sorting dependencies must not change dependency meaning.
- Topological mission ordering and per-mission dependency-list ordering are separate requirements.
- The test_valid_plan_acceptance and test_deterministic_dependency_conversion unittests must pass.

Sensitive Payload Redaction

- Sensitive payload keys must be preserved in the sanitized payload with the value "[redacted]".
- Do not silently remove sensitive keys.
- At minimum, redact keys named password, passwd, secret, token, api_key, api-key, authorization, bearer, credential, and private_key.
- Sensitive-key matching must be case-insensitive.
- Nested dictionaries and lists must be sanitized recursively.
- The original input payload must not be mutated.
- Non-sensitive payload fields must remain unchanged.
- Redacted payloads must remain JSON-safe and deterministic.
- The test_result_redaction unittest must find payload["password"] equal to "[redacted]".
- All existing and newly generated unittest tests must pass.
