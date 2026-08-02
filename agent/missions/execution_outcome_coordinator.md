Mission: Build Execution Outcome Coordinator

Goal

Create a small reusable multi-project coordinator that accepts one mission execution outcome, updates mission status, records provider usage, and persists the safe execution report through ExecutionReportWriter.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use dependency-injected public interfaces only.
- Fully typed and compatible with Python 3.12.
- Do not execute missions.
- Do not call providers directly.
- Do not execute Git, shell commands, Background Worker, or Autonomous Controller.

Dependencies

Inject:

- project resolver
- mission status writer
- ProviderUsageLedger
- ExecutionReportWriter
- clock
- identifier generator
- event sink

Do not instantiate real services inside this module.

Execution Outcome Input

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
- Resolve project_id through the injected project resolver.
- Reject cross-project references.
- Timestamps must be timezone-aware UTC.
- completed_at must not be earlier than started_at.
- Token counts must be non-negative integers.
- total_tokens must equal input_tokens plus output_tokens.
- estimated_cost must be non-negative or null.
- Unknown cost must remain null.
- success, retryable, and fallback_used must be boolean.
- status and success must be logically consistent.
- changed_files must contain safe repository-relative paths.
- Reject absolute paths, path traversal, and control characters.
- metadata must be JSON-safe.
- Do not mutate the original input.

Processing Order

1. Validate the execution outcome.
2. Detect duplicate execution_id.
3. Update mission status through the injected public interface.
4. Record provider usage through ProviderUsageLedger.
5. Persist the safe report through ExecutionReportWriter.
6. Emit safe structured events.
7. Return a deterministic result.

Mission Status Rules

- Use only the injected mission status writer.
- Do not edit queue storage directly.
- Preserve existing Mission Queue transition rules.
- Support transitions from running to:
  - completed
  - failed
  - blocked
  - cancelled
  - retrying
- Unknown missions must return mission_not_found.
- Invalid transitions must return invalid_status_transition.
- Mission status failure must stop further processing.
- Do not record usage or persist a report after mission-status failure.

Usage Ledger Mapping

Create one usage record containing:

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

Usage Rules

- Generate usage_id through the injected identifier generator.
- Record usage exactly once per execution_id.
- Unknown cost must remain null.
- Do not fabricate tokens or cost.
- Usage failure must return usage_recording_failed.
- Do not persist the execution report when usage recording fails.
- Duplicate outcomes must not create duplicate usage.

ExecutionReportWriter Integration

- Pass the validated original outcome to ExecutionReportWriter.store_report().
- Preserve identifiers, status, tokens, cost, and metadata.
- Do not perform duplicate redaction logic here.
- Let ExecutionReportWriter sanitize and persist the report.
- Report-writer failure must return report_persistence_failed.
- Do not claim success if report persistence fails.

Duplicate Handling

- execution_id must be unique.
- Duplicate detection must be atomic.
- A duplicate outcome must not update mission status twice.
- A duplicate outcome must not record usage twice.
- A duplicate outcome must not persist a second report.
- Return the previously stored deterministic result or duplicate_execution.

Result

Return:

- accepted
- execution_id
- project_id
- request_id
- mission_id
- status
- usage_recorded
- report_persisted
- duplicate
- blocked_reason
- completed_at

Failure Codes

- invalid_execution_outcome
- cross_project_reference
- duplicate_execution
- mission_not_found
- invalid_status_transition
- mission_status_update_failed
- usage_recording_failed
- report_persistence_failed
- dependency_failed

Security and Privacy

- Never expose API keys, credentials, or secret references.
- Never expose environment-variable values.
- Never include authorization headers.
- Never return unrestricted filesystem paths.
- Never log full summary or metadata content.
- Never return raw dependency exceptions.
- Never persist prompts, completions, uploaded content, or raw provider responses.
- Convert raw exceptions into safe failure codes.

Structured Events

Emit safe events for:

- execution_outcome_received
- execution_outcome_rejected
- duplicate_execution_detected
- mission_status_updated
- mission_status_update_failed
- usage_recorded
- usage_recording_failed
- execution_report_persisted
- execution_report_persistence_failed
- execution_outcome_completed
- execution_outcome_failed

Public Interface

Provide ExecutionOutcomeCoordinator with:

- process(outcome)
- validate_outcome(outcome)
- get_result(execution_id)
- status(project_id=None)
- latest_events(limit, project_id=None)

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake project resolver, mission status writer, ProviderUsageLedger, ExecutionReportWriter, clock, identifier generator, and event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git, shell commands, Worker, or Controller.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use dynamic code execution, dynamic imports, subprocess, or shell execution.
- Generated files must not contain the forbidden function-call pattern checked by Mission Runner.

Testing Requirements

- Test successful completed outcome.
- Test failed outcome.
- Test blocked outcome.
- Test cancelled outcome.
- Test retrying outcome.
- Test invalid status.
- Test timestamp ordering rejection.
- Test negative token rejection.
- Test invalid total-token rejection.
- Test negative cost rejection.
- Test unknown-cost preservation.
- Test unknown project.
- Test cross-project rejection.
- Test mission status update mapping.
- Test mission-not-found result.
- Test invalid status transition.
- Test status update failure stops processing.
- Test exact usage mapping.
- Test Usage Ledger failure.
- Test report persistence.
- Test report-writer failure.
- Test duplicate execution handling.
- Test duplicate usage prevention.
- Test duplicate status-update prevention.
- Test original input not mutated.
- Test deterministic result.
- Test result redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/execution/execution_outcome_coordinator.py
- agent/tests/test_execution_outcome_coordinator.py
