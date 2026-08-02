Mission: Build Provider Usage and Budget Manager

Goal

Create a reusable multi-project usage, cost, budget, rate-limit, and reporting layer for AI provider activity.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Keep usage and budget management independent from provider credentials.
- Integrate with the existing Provider and Model Registry through public interfaces.
- Remain project-neutral and provider-neutral.
- Support dependency injection for project resolver, model registry, clock, pricing resolver, identifier generation, and persistence paths.
- Fully typed and compatible with Python 3.12.

Budget Configuration

Support per-project budget configuration with:

- project_id
- enabled
- monthly_budget
- daily_budget
- per_request_budget
- monthly_token_limit
- daily_token_limit
- per_request_input_token_limit
- per_request_output_token_limit
- request_rate_limit
- soft_warning_percent
- hard_limit_enabled
- currency
- created_at
- updated_at

Requirements

- Every budget belongs to exactly one project_id.
- Budgets must remain isolated per project.
- Monetary values must be non-negative.
- Token and rate limits must be non-negative integers.
- soft_warning_percent must be between 0 and 100.
- Unknown pricing must be represented as null, never zero.
- Missing budget configuration must produce a safe unrestricted result unless policy explicitly requires blocking.
- Hard limits must block requests before provider execution.
- Soft limits must emit warnings without blocking.
- Budget evaluation must be deterministic.
- Budget state must recover safely after restart.

Usage Records

Each usage record must support:

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

- Never store prompts, completions, screenshots, file contents, message text, API keys, credentials, authorization headers, or raw provider responses.
- Usage records must remain isolated per project.
- Negative tokens or costs must be rejected.
- total_tokens must equal input_tokens plus output_tokens.
- Unknown estimated_cost must remain null.
- Usage identifiers must be unique.
- Duplicate usage identifiers must be rejected.
- Usage writes must be atomic.
- Usage records must recover after restart.
- Provider and model identifiers must be preserved exactly.
- fallback_used must be recorded accurately.

Pricing

Support dependency-injected pricing metadata.

Pricing records may contain:

- provider_id
- model_id
- input_cost_per_million_tokens
- output_cost_per_million_tokens
- currency
- effective_from
- effective_to

Requirements

- Do not hardcode provider prices in core logic.
- Missing pricing must return estimated_cost=null.
- Never claim exact cost when pricing data is unavailable.
- Cost estimation must be deterministic.
- Currency mismatches must be reported safely.
- Historical usage must not be recalculated silently when pricing changes.

Budget Checks

Provide a request estimate model with:

- project_id
- task_type
- provider_id
- model_id
- estimated_input_tokens
- requested_output_tokens
- estimated_cost
- request_timestamp

Budget check results must include:

- allowed
- warning
- blocked_reason
- remaining_daily_budget
- remaining_monthly_budget
- remaining_daily_tokens
- remaining_monthly_tokens
- remaining_rate_limit
- pricing_known

Requirements

- Budget checks must occur before provider execution.
- Check per-request limits first.
- Then check daily limits.
- Then check monthly limits.
- Then check rate limit.
- Return deterministic blocked reasons.
- Never partially deduct usage during a preflight check.
- Actual usage must be recorded only after provider completion or safe failure handling.
- Failed provider requests may record actual consumed tokens when known.
- Unknown usage must not be fabricated.

Rate Limiting

- Support per-project request-rate limits.
- Use a deterministic sliding-window or fixed-window implementation.
- Persist enough state to recover safely after restart.
- Concurrent checks must not permit over-limit execution.
- Tests must use bounded timeouts and must never hang.

Reporting

Support deterministic summaries for:

- daily usage
- monthly usage
- custom date ranges
- provider
- model
- task type
- project
- success and failure
- fallback usage

Each summary may include:

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

Requirements

- Do not combine incompatible currencies into a fake total.
- Report currency-separated totals when multiple currencies exist.
- Unknown cost records must increment unknown_cost_count.
- Summary ordering must be deterministic.
- Date boundaries must use UTC.
- Empty summaries must return zero counts and no fabricated cost.

Public Interface

Provide a ProviderUsageBudgetManager class with:

- configure_budget(project_id, config)
- update_budget(project_id, changes)
- get_budget(project_id)
- remove_budget(project_id)
- check_budget(project_id, request_estimate)
- record_usage(record)
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

Project and Model Integration

- Use project_id through a dependency-injected project resolver.
- Reject unknown projects.
- Validate provider and model identifiers through the existing Provider and Model Registry when configured.
- Never access another project's budget or usage data.
- The same provider and model may have different budget rules in different projects.
- Mitigate must remain one project profile, not hardcoded behavior.

Persistence

- Persist budgets, usage metadata, rate-limit state, and events as deterministic JSON.
- Use atomic writes.
- Use file locking.
- Reject corrupted storage rather than silently overwriting it.
- Prevent path traversal and symbolic-link escape.
- Never persist secrets.
- Never modify unrelated files.
- Public methods must not acquire the same non-reentrant lock twice.
- Use private lock-free helpers for nested operations.
- All lock-related tests must use bounded timeouts.

Structured Events

Emit safe deterministic events for:

- budget_configured
- budget_updated
- budget_removed
- budget_warning
- budget_blocked
- usage_recorded
- usage_rejected
- rate_limit_warning
- rate_limit_blocked
- pricing_unknown

Each event may include:

- event
- project_id
- provider_id
- model_id
- task_type
- request_id
- mission_id
- timestamp
- safe status information

Never include:

- prompts
- completions
- images
- files
- message content
- credentials
- authorization headers
- raw provider responses
- unrestricted filesystem paths

Admin Panel Integration Contract

The future panel must be able to:

- view daily and monthly spend
- view token usage
- view request counts
- filter by project, provider, model, and task
- view fallback usage
- configure daily, monthly, and per-request budgets
- configure token limits
- configure request rate limits
- view warnings and blocked requests
- distinguish known and unknown pricing
- view which model handled each mission

Do not build the web interface in this mission.
Create only the reusable service layer.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use tempfile and TemporaryDirectory.
- Tests must not perform real network access.
- Tests must not call real AI providers.
- Tests must not run Git commands.
- Tests must not execute Background Worker.
- Use fake project resolver, fake model registry, fake pricing resolver, fake clock, and deterministic identifier generation.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports such as agent.providers.provider_usage_budget_manager.
- Do not modify sys.path inside tests.
- Tests involving locks or concurrency must use bounded timeouts and must never hang.

Testing Requirements

- Test budget creation and update.
- Test budget removal.
- Test invalid negative values.
- Test soft-warning threshold.
- Test per-request budget blocking.
- Test daily budget blocking.
- Test monthly budget blocking.
- Test per-request token blocking.
- Test daily token blocking.
- Test monthly token blocking.
- Test rate-limit blocking.
- Test unknown pricing handling.
- Test deterministic cost estimation.
- Test usage recording.
- Test duplicate usage rejection.
- Test invalid token totals.
- Test negative usage rejection.
- Test fallback recording.
- Test project isolation.
- Test provider and model validation.
- Test daily summary.
- Test monthly summary.
- Test date-range summary.
- Test summary by provider.
- Test summary by model.
- Test summary by task.
- Test mixed-currency reporting.
- Test unknown-cost counting.
- Test empty summary.
- Test UTC date boundaries.
- Test atomic persistence.
- Test restart recovery.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test event redaction.
- Test concurrent rate-limit checks.
- Test two independent projects with different budgets.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_usage_budget_manager.py
- agent/providers/provider_budget.example.json
- agent/tests/test_provider_usage_budget_manager.py
