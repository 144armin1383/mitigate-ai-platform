Mission: Build Provider Budget Manager

Goal

Create a reusable multi-project service that manages AI provider budgets, token limits, preflight request checks, and deterministic warnings or blocking decisions.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Integrate with Provider Usage Ledger and Provider Model Registry through dependency injection.
- Support dependency injection for project resolver, usage reader, model resolver, pricing resolver, policy resolver, and clock.
- Fully typed and compatible with Python 3.12.

Budget Configuration

Each project budget must support:

- project_id
- enabled
- daily_budget
- monthly_budget
- per_request_budget
- daily_token_limit
- monthly_token_limit
- per_request_input_token_limit
- per_request_output_token_limit
- soft_warning_percent
- hard_limit_enabled
- currency
- unknown_pricing_policy
- created_at
- updated_at

Supported unknown pricing policies:

- allow
- warn
- block

Validation

- Every budget belongs to exactly one project_id.
- Unknown projects must be rejected.
- Monetary values must be non-negative numbers or null.
- Token limits must be non-negative integers or null.
- soft_warning_percent must be between 0 and 100.
- currency must be a validated uppercase currency code.
- unknown_pricing_policy must be allow, warn, or block.
- Project configurations must remain isolated.
- Cross-project access must be rejected.
- Missing configuration must produce a safe unrestricted result unless injected policy requires blocking.

Request Estimate

Each preflight request must support:

- project_id
- request_id
- task_type
- provider_id
- model_id
- estimated_input_tokens
- requested_output_tokens
- estimated_cost
- cost_currency
- request_timestamp

Validation Requirements

- Token estimates must be non-negative integers.
- estimated_cost must be non-negative or null.
- request_id must be validated.
- Provider and model must be validated through the injected resolver when configured.
- request_timestamp must use UTC.
- Cross-project references must be rejected.

Budget Check Result

Return:

- allowed
- warning
- blocked_reason
- pricing_known
- remaining_daily_budget
- remaining_monthly_budget
- remaining_daily_tokens
- remaining_monthly_tokens
- evaluated_at
- project_id
- request_id

Evaluation Order

1. Per-request input token limit
2. Per-request output token limit
3. Per-request budget
4. Daily token limit
5. Monthly token limit
6. Daily budget
7. Monthly budget
8. Unknown pricing policy

Requirements

- Return deterministic blocked reasons.
- Hard limits must block before provider execution.
- Soft thresholds must warn without blocking.
- Preflight checks must never deduct usage.
- Usage totals must be read through the injected Provider Usage Ledger.
- Do not duplicate usage aggregation logic.
- Use UTC daily and monthly boundaries.
- Unknown usage must never be fabricated.

Unknown Pricing

- Unknown pricing must never be treated as zero.
- pricing_known must be false when estimated_cost is null.
- allow permits the request.
- warn permits the request and sets warning=true.
- block rejects the request.
- Never claim an exact cost when pricing is unavailable.

Soft Warnings

- Warn when consumption reaches or exceeds soft_warning_percent of a configured daily or monthly limit.
- Warnings must not block.
- Missing limits must not produce warnings.
- Warning calculation must be deterministic.

Public Interface

Provide a ProviderBudgetManager class with:

- configure_budget(project_id, config)
- update_budget(project_id, changes)
- get_budget(project_id)
- remove_budget(project_id)
- check_request(project_id, request_estimate)
- remaining_limits(project_id, timestamp=None)
- status(project_id=None)
- latest_events(limit, project_id=None)

Persistence

- Persist budgets and events as deterministic JSON.
- Use atomic writes.
- Use file locking.
- Recover safely after restart.
- Reject corrupted storage instead of overwriting it.
- Prevent path traversal and symbolic-link escape.
- Accept safe internally generated atomic temporary filenames.
- Never store secrets, prompts, completions, images, files, or raw provider responses.
- Never modify unrelated files.
- Public methods must not reacquire the same non-reentrant lock.
- Use private lock-free helpers for nested operations.
- Lock-related tests must use bounded timeouts.

Structured Events

Emit:

- budget_configured
- budget_updated
- budget_removed
- budget_warning
- budget_blocked
- token_limit_warning
- token_limit_blocked
- pricing_unknown

Events must contain safe identifiers and status only.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add dependencies.
- Never modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Tests must not use network access, real providers, Git commands, or Background Worker.
- Use fake project resolver, usage reader, model resolver, pricing resolver, policy resolver, and clock.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Do not modify sys.path.
- Concurrency tests must use bounded timeouts.

Testing Requirements

- Test budget creation and update.
- Test budget removal.
- Test missing configuration behavior.
- Test negative-value rejection.
- Test invalid currency.
- Test invalid unknown-pricing policy.
- Test soft warnings.
- Test per-request budget blocking.
- Test per-request input-token blocking.
- Test per-request output-token blocking.
- Test daily token blocking.
- Test monthly token blocking.
- Test daily budget blocking.
- Test monthly budget blocking.
- Test unknown-pricing allow.
- Test unknown-pricing warn.
- Test unknown-pricing block.
- Test deterministic evaluation order.
- Test deterministic blocked reasons.
- Test preflight does not deduct usage.
- Test project isolation.
- Test provider and model validation.
- Test two projects with different budgets.
- Test UTC boundaries.
- Test atomic persistence.
- Test temporary filenames.
- Test restart recovery.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_budget_manager.py
- agent/providers/provider_budget.example.json
- agent/tests/test_provider_budget_manager.py
