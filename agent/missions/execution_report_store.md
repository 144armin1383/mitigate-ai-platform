Mission: Build Execution Report Store

Goal

Create a reusable multi-project store that validates, sanitizes, persists, retrieves, and summarizes safe mission execution reports.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Support dependency injection for project resolver, clock, identifier generator, and event sink.
- Fully typed and compatible with Python 3.12.
- Do not update Mission Queue status.
- Do not record Provider Usage Ledger entries.
- Do not execute missions, providers, Git, Worker, Controller, shell commands, or external processes.

Execution Report Input

Support:

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

Supported statuses:

- completed
- failed
- blocked
- cancelled
- retrying

Validation

- Reject unknown fields.
- Required identifiers must be valid non-empty strings.
- project_id must resolve through the injected project resolver.
- All report references must belong to the same project.
- Reject cross-project references.
- started_at and completed_at must be timezone-aware UTC timestamps.
- completed_at must not be earlier than started_at.
- Token counts must be non-negative integers.
- total_tokens must equal input_tokens plus output_tokens.
- estimated_cost must be non-negative or null.
- Unknown cost must remain null.
- success, retryable, and fallback_used must be boolean.
- status and success must be logically consistent.
- changed_files must contain safe repository-relative paths only.
- Reject absolute paths, path traversal, control characters, and symbolic-link escape.
- git_branch and git_commit are optional and syntax-validated.
- metadata must be JSON-safe.

Redaction

Never persist or return:

- prompts
- completions
- full user messages
- uploaded content
- credentials
- authorization headers
- environment-variable values
- raw provider responses
- raw tracebacks
- unrestricted filesystem paths

Preserve sensitive keys with value "[redacted]".

Redact case-insensitive keys including:

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

- Sanitize nested dictionaries and lists recursively.
- Do not mutate the original input.
- Non-sensitive fields must remain unchanged.

Duplicate Reporting

- execution_id must be unique.
- Duplicate detection and persistence must be atomic.
- Duplicate reporting must not overwrite the existing report.
- Return the existing safe report or a deterministic duplicate result.
- Duplicate reporting must not create a second stored report.

Safe Stored Report

Persist:

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

Provide ExecutionReportStore with:

- store_report(report)
- validate_report(report)
- get_report(execution_id)
- list_reports(project_id, filters=None)
- get_mission_report(project_id, mission_id)
- request_summary(project_id, request_id)
- status(project_id=None)
- latest_events(limit, project_id=None)

Filters

Support:

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

Request Summary

Return:

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

Summary Rules

- Do not combine incompatible currencies into one fabricated total.
- Unknown costs must increment unknown_cost_count.
- Empty summaries must use deterministic zero counts.
- Use UTC date boundaries.
- Ordering must be deterministic.
- Never fabricate missing data.

Persistence

- Persist reports and events as deterministic JSON.
- Use atomic writes and file locking.
- Recover safely after restart.
- Reject corrupted storage rather than overwriting it.
- Accept safe internally generated temporary filenames.
- Prevent path traversal and symbolic-link escape.
- Avoid nested non-reentrant locks.
- Event writing must occur after releasing the report-storage lock.
- Never modify unrelated files.
- Lock tests must use bounded timeouts.

Events

Emit safe events for:

- execution_report_received
- execution_report_rejected
- duplicate_execution_detected
- execution_report_persisted
- execution_report_store_failed

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake project resolver, clock, identifier generator, and event sink.
- Do not use network, providers, Git, Worker, Controller, subprocess, or shell execution.
- Every Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.
- Do not use eval, exec, compile, or dynamic imports.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test completed report storage.
- Test failed, blocked, retrying, and cancelled reports.
- Test invalid status.
- Test timestamp ordering.
- Test negative tokens.
- Test invalid token total.
- Test negative cost.
- Test unknown-cost preservation.
- Test project isolation.
- Test cross-project rejection.
- Test safe changed-file paths.
- Test absolute-path rejection.
- Test traversal rejection.
- Test duplicate execution reporting.
- Test sensitive metadata redaction.
- Test summary redaction.
- Test original input not mutated.
- Test report retrieval.
- Test deterministic listing.
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

- agent/execution/execution_report_store.py
- agent/tests/test_execution_report_store.py
