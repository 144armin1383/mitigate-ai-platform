Mission: Build Execution Result Reporter

Goal

Create a reusable multi-project service that receives one completed mission execution result, validates and sanitizes it, records safe provider usage metadata, and creates deterministic status reports for the Admin API and Dashboard.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Use dependency-injected public interfaces only.
- Fully typed and compatible with Python 3.12.
- Do not execute missions.
- Do not call AI providers directly.
- Do not execute Git commands, shell commands, Background Worker, or Autonomous Controller.

Execution Result Input

Each execution result must support:

- execution_id
- project_id
- request_id
- conversation_id
- plan_id
- mission_id
- step_id
- task_type
- provider_id
- model_id
- worker_id
- started_at
- completed_at
- status
- success
- retryable
- fallback_used
- input_tokens
- output_tokens
- total_tokens
- estimated_cost
- cost_currency
- safe_error_code
- summary
- changed_files
- git_branch
- git_commit
- validation_status
- metadata

Supported execution statuses:

- completed
- failed
- blocked
- cancelled
- retrying

Validation

- Reject unknown fields.
- All identifiers must be valid non-empty strings when required.
- project_id must resolve through the injected project resolver.
- Mission, request, plan, and conversation references must belong to the same project.
- started_at and completed_at must be timezone-aware UTC timestamps.
- completed_at must not be earlier than started_at.
- input_tokens and output_tokens must be non-negative integers.
- total_tokens must equal input_tokens plus output_tokens.
- estimated_cost must be non-negative or null.
- Unknown cost must remain null.
- fallback_used, success, and retryable must be boolean.
- status and success must be logically consistent.
- Cross-project references must be rejected.
- changed_files must contain safe repository-relative paths only.
- Absolute paths and path traversal must be rejected.
- git_branch and git_commit are optional and must be syntax-validated.
- metadata must be JSON-safe.

Privacy and Security

Never persist or return:

- prompts
- completions
- full user messages
- uploaded image contents
- uploaded file contents
- API keys
- credentials
- authorization headers
- environment-variable values
- raw provider responses
- unrestricted filesystem paths
- raw exception tracebacks

Sensitive metadata keys must remain present with value "[redacted]".

At minimum redact case-insensitive keys:

- password
- passwd
- secret
- token
- api_key
- api-key
- authorization
- bearer
- credential
- private_key
- access_key

Usage Ledger Integration

Inject ProviderUsageLedger.

For each execution result, create one safe usage record containing:

- usage_id
- project_id
- request_id
- mission_id
- conversation_id
- task_type
- provider_id
- model_id
- started_at
- completed_at
- input_tokens
- output_tokens
- total_tokens
- estimated_cost
- cost_currency
- fallback_used
- success
- safe_error_code

Requirements

- Record usage exactly once per execution_id.
- Duplicate execution reporting must not create duplicate usage.
- Use deterministic or injected usage identifier generation.
- Unknown cost must remain null.
- Do not fabricate token counts or cost.
- Usage Ledger failure must return usage_recording_failed.
- Never partially claim success when usage recording fails.
- Do not mutate the original execution result.

Mission Status Integration

Inject a mission status writer or Mission Queue adapter.

Supported status transitions:

- running to completed
- running to failed
- running to blocked
- running to cancelled
- running to retrying

Requirements

- Update mission status only after execution-result validation succeeds.
- Preserve existing Mission Queue state-transition rules.
- Unknown missions must return mission_not_found.
- Invalid transitions must return invalid_status_transition.
- Do not bypass queue locking or persistence.
- Do not directly edit queue storage files.
- Use only the injected public interface.

Processing Order

1. Validate the execution result.
2. Sanitize metadata and summary.
3. Check duplicate execution_id.
4. Update mission status through the injected status writer.
5. Record safe usage through ProviderUsageLedger.
6. Persist the safe execution report.
7. Emit structured events.
8. Return a deterministic result.

Duplicate Reporting

- execution_id must be unique.
- Re-reporting the same execution_id must not update mission status twice.
- Re-reporting the same execution_id must not create duplicate usage.
- Duplicate reporting must return the existing safe report or a deterministic duplicate result.
- Duplicate detection and report persistence must be atomic.

Safe Execution Report

Persist and return:

- execution_id
- project_id
- request_id
- conversation_id
- plan_id
- mission_id
- step_id
- task_type
- provider_id
- model_id
- worker_id
- started_at
- completed_at
- status
- success
- retryable
- fallback_used
- input_tokens
- output_tokens
- total_tokens
- estimated_cost
- cost_currency
- safe_error_code
- safe_summary
- changed_files
- git_branch
- git_commit
- validation_status
- safe_metadata
- recorded_at

Public Interface

Provide an ExecutionResultReporter class with:

- report_execution(result)
- validate_execution_result(result)
- get_report(execution_id)
- list_reports(project_id, filters=None)
- get_mission_report(project_id, mission_id)
- request_summary(project_id, request_id)
- status(project_id=None)
- latest_events(limit, project_id=None)

Reporting

Support filters for:

- request_id
- conversation_id
- plan_id
- mission_id
- provider_id
- model_id
- task_type
- status
- success
- fallback_used
- date range

Request summaries must include:

- request_id
- project_id
- mission_count
- completed_count
- failed_count
- blocked_count
- cancelled_count
- retrying_count
- input_tokens
- output_tokens
- total_tokens
- estimated_cost
- unknown_cost_count
- fallback_count
- overall_status

Rules

- Do not combine incompatible currencies into one fake total.
- Unknown costs must increment unknown_cost_count.
- Summary ordering must be deterministic.
- Use UTC boundaries.
- Never fabricate missing data.

Persistence

- Persist safe execution reports and events as deterministic JSON.
- Use atomic writes.
- Use file locking.
- Recover safely after restart.
- Reject corrupted storage instead of silently overwriting it.
- Accept safe internally generated temporary filenames.
- Prevent path traversal and symbolic-link escape.
- Avoid nested non-reentrant locks.
- Event writing must occur after releasing the report storage lock.
- Never modify unrelated files.
- Lock-related tests must use bounded timeouts and must never hang.

Structured Events

Emit safe deterministic events for:

- execution_result_received
- execution_result_rejected
- duplicate_execution_detected
- mission_status_updated
- mission_status_update_failed
- usage_recorded
- usage_recording_failed
- execution_report_persisted
- execution_reporting_completed
- execution_reporting_failed

Events may contain safe identifiers, status, provider, model, token counts, cost status, and timestamps only.

Failure Codes

- invalid_execution_result
- cross_project_reference
- duplicate_execution
- mission_not_found
- invalid_status_transition
- mission_status_update_failed
- usage_recording_failed
- persistence_failed
- dependency_failed

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake project resolver, mission status writer, ProviderUsageLedger, clock, identifier generator, and event sink.
- Do not use network access.
- Do not call real AI providers.
- Do not execute Git, shell commands, Worker, or Controller.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, subprocess, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test successful completed execution reporting.
- Test failed execution reporting.
- Test blocked execution reporting.
- Test retrying execution reporting.
- Test cancelled execution reporting.
- Test invalid status rejection.
- Test timestamp ordering rejection.
- Test negative token rejection.
- Test invalid total token rejection.
- Test negative cost rejection.
- Test unknown cost preservation.
- Test project isolation.
- Test cross-project reference rejection.
- Test safe changed-file validation.
- Test absolute path rejection.
- Test path traversal rejection.
- Test mission status update.
- Test mission-not-found handling.
- Test invalid transition handling.
- Test usage record mapping.
- Test Usage Ledger failure.
- Test duplicate execution reporting.
- Test duplicate usage prevention.
- Test sensitive metadata redaction.
- Test summary redaction.
- Test original input is not mutated.
- Test report retrieval.
- Test deterministic report listing.
- Test mission report retrieval.
- Test request summary.
- Test mixed-currency reporting.
- Test unknown-cost counting.
- Test fallback counting.
- Test restart recovery.
- Test atomic persistence.
- Test safe temporary filenames.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/execution/execution_result_reporter.py
- agent/tests/test_execution_result_reporter.py
