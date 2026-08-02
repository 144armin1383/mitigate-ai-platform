Mission: Build Execution Report Writer Tests

Goal

Create a comprehensive unittest suite for the existing ExecutionReportWriter production module.

Scope

- Generate test code only.
- Do not modify agent/execution/execution_report_writer.py.
- Do not modify requirements.txt.
- Do not add dependencies.
- Use Python standard library unittest only.
- Tests must be compatible with Python 3.12.
- Tests must run from repository root using unittest discovery.

Module Under Test

- agent.execution.execution_report_writer.ExecutionReportWriter

Testing Environment

- Use unittest.
- Use unittest.mock.
- Use tempfile.TemporaryDirectory.
- Use deterministic fake project resolver.
- Use deterministic fake clock.
- Use safe fake event sink.
- Do not use network access.
- Do not execute Git commands.
- Do not execute shell commands.
- Do not execute Worker, Controller, or AI providers.
- Do not modify sys.path.
- Use repository-root imports.

Generated Test Safety

- Do not import ast.
- Do not use Python expression interpretation.
- Do not use dynamic code execution.
- Do not use exec, compile, importlib, __import__, subprocess, os.system, or shell execution.
- Read persisted data only with json.load() or json.loads().
- Serialize expected JSON only with json.dumps().
- Generated test code must not contain the forbidden function-call pattern checked by Mission Runner anywhere, including comments, strings, names, or documentation.

Base Valid Report

Create a deterministic valid report fixture containing:

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

Testing Requirements

Validation

- Test successful completed report storage.
- Test successful failed report storage.
- Test successful blocked report storage.
- Test successful retrying report storage.
- Test successful cancelled report storage.
- Test invalid status rejection.
- Test completed_at earlier than started_at rejection.
- Test naive timestamp rejection.
- Test negative input_tokens rejection.
- Test negative output_tokens rejection.
- Test invalid total_tokens rejection.
- Test negative estimated_cost rejection.
- Test null estimated_cost preservation.
- Test non-boolean success rejection.
- Test non-boolean retryable rejection.
- Test non-boolean fallback_used rejection.
- Test unknown field rejection.
- Test unknown project rejection.
- Test cross-project reference rejection.

Path Safety

- Test safe repository-relative changed file.
- Test multiple safe changed files.
- Test absolute path rejection.
- Test parent traversal rejection.
- Test control-character path rejection.
- Test unsafe symbolic-link escape behavior where supported without creating external side effects.

Redaction

- Test password redaction.
- Test token redaction.
- Test api_key redaction.
- Test authorization redaction.
- Test nested dictionary redaction.
- Test nested list redaction.
- Test case-insensitive sensitive-key redaction.
- Test sensitive keys remain present with value "[redacted]".
- Test non-sensitive metadata remains unchanged.
- Test summary sanitization.
- Test original input object is not mutated.

Duplicate Handling

- Test duplicate execution_id detection.
- Test duplicate report does not overwrite original.
- Test duplicate report does not create a second stored record.
- Test duplicate result is deterministic.

Persistence and Recovery

- Test report retrieval by execution_id.
- Test missing report behavior.
- Test deterministic JSON serialization.
- Test atomic persistence.
- Test safe temporary filename handling.
- Test restart recovery using a second writer instance.
- Test corrupted storage rejection.
- Test storage directory isolation.
- Test unrelated files remain unchanged.

Events and Status

- Test execution_report_received event.
- Test execution_report_rejected event.
- Test duplicate_execution_detected event.
- Test execution_report_persisted event.
- Test event redaction.
- Test latest_events limit.
- Test project-scoped status.
- Test status does not expose secrets or report content.

Concurrency and Locking

- Test duplicate detection remains atomic under concurrent attempts.
- Test only one concurrent duplicate report is persisted.
- Use bounded thread joins and timeouts.
- Tests must never hang.
- Do not acquire the same non-reentrant lock twice in fake helpers.

Compatibility

- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.
- Do not change unrelated files.

Deliverables

- agent/tests/test_execution_report_writer.py
