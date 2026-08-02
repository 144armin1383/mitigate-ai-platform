Mission: Build Provider Usage Ledger

Goal

Create a reusable multi-project ledger for recording AI provider token usage, estimated costs, fallback usage, and deterministic usage reports.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Integrate with the existing Provider and Model Registry through dependency injection.
- Support dependency injection for project resolver, model resolver, pricing resolver, clock, and identifier generation.
- Fully typed and compatible with Python 3.12.

Usage Record

Each usage record must contain:

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

Validation

- usage_id must be unique.
- Duplicate usage identifiers must be rejected.
- Every record must belong to exactly one project_id.
- Unknown projects must be rejected through the injected project resolver.
- Provider and model identifiers must be validated when a model resolver is configured.
- input_tokens and output_tokens must be non-negative integers.
- total_tokens must equal input_tokens plus output_tokens.
- estimated_cost must be non-negative or null.
- Unknown cost must remain null and must never be converted to zero.
- completed_at must not be earlier than started_at.
- fallback_used must be boolean.
- Cross-project access must be rejected.

Privacy and Security

- Never store prompts.
- Never store completions.
- Never store chat message text.
- Never store images or uploaded file contents.
- Never store API keys, bearer tokens, passwords, authorization headers, or provider credentials.
- Never store raw provider responses.
- Never expose unrestricted filesystem paths.
- Events and reports must contain safe metadata only.

Pricing

- Pricing must be supplied through a dependency-injected pricing resolver.
- Do not hardcode provider prices.
- Pricing may include separate input and output token rates.
- Missing pricing must return estimated_cost=null.
- Historical records must preserve their originally recorded estimated cost.
- Pricing changes must not silently recalculate historical usage.
- Currency mismatches must be reported safely.
- Never claim exact cost when pricing is unknown.

Public Interface

Provide a ProviderUsageLedger class with:

- record_usage(record)
- estimate_cost(provider_id, model_id, input_tokens, output_tokens)
- get_usage(usage_id)
- list_usage(project_id, filters=None)
- daily_summary(project_id, date)
- monthly_summary(project_id, year, month)
- range_summary(project_id, start, end)
- summary_by_provider(project_id, start=None, end=None)
- summary_by_model(project_id, start=None, end=None)
- summary_by_task(project_id, start=None, end=None)
- status(project_id=None)
- latest_events(limit, project_id=None)

Reporting

Reports must support:

- request_count
- successful_requests
- failed_requests
- input_tokens
- output_tokens
- total_tokens
- estimated_cost
- unknown_cost_count
- fallback_count
- currency

Reporting Rules

- Use UTC date boundaries.
- Summary ordering must be deterministic.
- Empty summaries must return zero counts.
- Never fabricate cost.
- Unknown costs must increment unknown_cost_count.
- Different currencies must be reported separately.
- Do not combine incompatible currencies into one total.
- Reports must remain isolated per project.
- Filters must support provider_id, model_id, task_type, success, and fallback_used.

Persistence

- Persist usage records and events as deterministic JSON.
- Use atomic writes.
- Use file locking.
- Recover safely after restart.
- Reject corrupted storage instead of silently overwriting it.
- Prevent path traversal and symbolic-link escape.
- Never modify unrelated files.
- Public methods must not acquire the same non-reentrant lock twice.
- Use private lock-free helpers for nested operations.
- Tests involving locks must use bounded timeouts and must never hang.

Structured Events

Emit safe deterministic events for:

- usage_recorded
- usage_rejected
- pricing_unknown
- usage_summary_created

Events may contain safe identifiers, token counts, known cost, currency, success, and fallback status.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use tempfile and TemporaryDirectory.
- Tests must not perform network access.
- Tests must not call real providers.
- Tests must not execute Git commands or Background Worker.
- Use fake project resolver, model resolver, pricing resolver, clock, and identifier generator.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.

Testing Requirements

- Test usage recording.
- Test duplicate usage rejection.
- Test invalid negative token values.
- Test invalid token totals.
- Test invalid negative cost.
- Test project isolation.
- Test provider and model validation.
- Test fallback recording.
- Test known pricing calculation.
- Test unknown pricing.
- Test historical cost preservation.
- Test daily summary.
- Test monthly summary.
- Test range summary.
- Test summary by provider.
- Test summary by model.
- Test summary by task.
- Test mixed-currency reporting.
- Test unknown-cost counting.
- Test empty summary.
- Test UTC boundaries.
- Test atomic persistence.
- Test restart recovery.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test secret and content redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_usage_ledger.py
- agent/providers/provider_usage.example.json
- agent/tests/test_provider_usage_ledger.py

Provider Usage Ledger Locking and Timestamp Contract

- record_usage() may acquire the ledger storage lock exactly once.
- Public methods may acquire the ledger lock.
- Internal helper methods must assume the caller already owns the lock.
- Nested locking is forbidden.
- Nested file locking is forbidden.
- Usage persistence and event persistence must use separate critical sections.
- Event logging must occur only after the usage storage lock has been released.
- _emit_event() must never acquire the active usage storage lock.
- Duplicate usage detection and persistence must remain atomic.
- File locks must always be released before writing structured events.
- Usage recording must always terminate in bounded time.
- Lock-related unittest tests must never hang.

- completed_at must not be earlier than started_at.
- Production validation must reject invalid timestamp ordering.
- Normal unittest fixtures must always use chronologically valid timestamps.
- Only the dedicated invalid-timestamp test may intentionally violate timestamp ordering.
- All existing and newly generated unittest tests must pass.

Provider Usage Ledger Identity, Validation, and Summary Contract

Duplicate Usage Identity

- usage_id is the unique immutable identifier of a usage record.
- record_usage() must reject any usage_id that already exists.
- Duplicate detection and persistence must occur within one atomic critical section.
- A duplicate attempt must raise a dedicated exception derived from Exception.
- A duplicate attempt must not overwrite or append another record.
- Persisted state must remain unchanged after duplicate rejection.

Provider and Model Validation

- Provider and model validation must use the injected model resolver only when one is configured.
- Unknown providers or models must raise a dedicated safe ledger validation exception.
- Raw resolver exceptions must be converted into safe ledger validation exceptions.
- Validation failures must not partially persist usage records.
- Normal unittest fixtures must use provider and model identifiers accepted by the fake resolver.
- Dedicated invalid-provider and invalid-model tests must explicitly assert that validation raises an exception.

Range Summary and Unknown Cost

- range_summary() must include every matching usage record.
- Records with a known estimated_cost and currency must contribute to that currency bucket.
- Records with estimated_cost=null must increment unknown_cost_count.
- Unknown-cost records must never be omitted or converted to zero.
- If a range contains both known and unknown costs, known currency totals and unknown_cost_count must both be preserved.
- Date-range filtering must use UTC and the inclusive range behavior expected by unittest fixtures.
- Summary ordering must remain deterministic.
- Empty ranges must return deterministic zero-count output.

Testing Consistency

- Generated implementation and tests must follow the same duplicate, validation, UTC range, currency, and unknown-cost contracts.
- All existing and newly generated unittest tests must pass.
