Mission: Build Execution Report Writer Core

Goal

Create a production-only multi-project component that validates, sanitizes, and atomically persists safe mission execution reports.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Fully typed and compatible with Python 3.12.
- Generate production code only.
- Do not generate tests in this mission.
- Existing repository tests must continue to pass.

Execution Report Fields

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

Supported Statuses

- completed
- failed
- blocked
- cancelled
- retrying

Validation

- Reject unknown fields.
- Required identifiers must be valid non-empty strings.
- Resolve project_id through the injected project resolver.
- Reject cross-project references.
- Timestamps must be timezone-aware UTC.
- completed_at must not be earlier than started_at.
- Token counts must be non-negative integers.
- total_tokens must equal input_tokens plus output_tokens.
- estimated_cost must be non-negative or null.
- Unknown cost must remain null.
- success, retryable, and fallback_used must be boolean.
- Status and success must be logically consistent.
- changed_files must contain safe repository-relative paths.
- Reject absolute paths, path traversal, and control characters.
- Optional git_branch and git_commit must be syntax-validated.
- metadata must be JSON-safe.

Redaction

- Preserve sensitive keys with value "[redacted]".
- Match sensitive keys case-insensitively.
- Redact password, passwd, secret, token, api_key, api-key, authorization, bearer, credential, private_key, and access_key.
- Sanitize nested dictionaries and lists recursively.
- Do not mutate the original input.
- Never persist prompts, completions, full messages, uploaded content, credentials, raw provider responses, tracebacks, environment values, or unrestricted paths.

Duplicate Handling

- execution_id must be unique.
- Duplicate detection and persistence must be atomic.
- Duplicate reporting must not overwrite the original report.
- Duplicate reporting must not create another stored record.
- Return the existing safe report or a deterministic duplicate result.

Public Interface

Provide ExecutionReportWriter with:

- store_report(report)
- validate_report(report)
- get_report(execution_id)
- status(project_id=None)
- latest_events(limit, project_id=None)

Persistence

- Persist reports and events as deterministic JSON.
- Use atomic writes and file locking.
- Recover safely after restart.
- Reject corrupted storage.
- Accept safe internally generated temporary filenames.
- Prevent path traversal and symbolic-link escape.
- Avoid nested non-reentrant locking.
- Write events only after releasing the report-storage lock.
- Never modify unrelated files.

Events

Emit safe events for:

- execution_report_received
- execution_report_rejected
- duplicate_execution_detected
- execution_report_persisted
- execution_report_store_failed

Generated File Safety

- Do not use dynamic code execution.
- Do not import ast, importlib, or subprocess.
- Use only the json module for structured data.
- Generated code must not contain the forbidden function-call pattern checked by Mission Runner.
- The generated Python file must pass py_compile.
- All existing unittest tests must pass.

Deliverables

- agent/execution/execution_report_writer.py
