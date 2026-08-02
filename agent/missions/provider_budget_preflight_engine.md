Mission: Build Provider Budget Preflight Engine

Goal

Create a small reusable multi-project engine that evaluates AI requests against budget and token limits before provider execution.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Read configuration through a dependency-injected Provider Budget Configuration Store.
- Read usage totals through a dependency-injected Provider Usage Ledger.
- Validate projects and models through dependency-injected resolvers.
- Support dependency injection for clock and unknown-pricing policy.
- Fully typed and compatible with Python 3.12.

Request Estimate

Each request estimate must contain:

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

Validation

- Reject unknown projects.
- Validate provider and model when a resolver is configured.
- Token estimates must be non-negative integers.
- estimated_cost must be non-negative or null.
- request_timestamp must be timezone-aware and normalized to UTC.
- Cross-project references must be rejected.
- Unknown fields must be rejected.

Decision Result

Return a deterministic dictionary containing:

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

Evaluate in this exact order:

1. Per-request input token limit
2. Per-request output token limit
3. Per-request budget
4. Daily token limit
5. Monthly token limit
6. Daily budget
7. Monthly budget
8. Unknown pricing policy
9. Soft warning thresholds

Rules

- Hard limits must block before provider execution.
- Soft warnings must not block.
- Preflight evaluation must never record or deduct usage.
- Daily and monthly totals must come from Provider Usage Ledger.
- Use UTC daily and monthly boundaries.
- Missing budget configuration returns an unrestricted allowed result.
- Missing individual limits must not block or warn.
- Return deterministic blocked_reason values.
- Never fabricate usage or cost.

Unknown Pricing

- estimated_cost=null means pricing_known=false.
- Unknown pricing must never be treated as zero.
- allow policy permits the request.
- warn policy permits the request and sets warning=true.
- block policy rejects the request.
- The policy comes from the saved project configuration unless an injected policy overrides it.

Soft Warning Thresholds

- Warn when current usage plus the request estimate reaches or exceeds soft_warning_percent of a configured daily or monthly limit.
- Soft warnings must never block.
- Warning results must remain deterministic.
- Missing limits must not create warnings.

Public Interface

Provide a ProviderBudgetPreflightEngine class with:

- check_request(project_id, request_estimate)
- remaining_limits(project_id, timestamp=None)
- status(project_id=None)
- latest_events(limit, project_id=None)

Integration

- Use only public interfaces of Provider Budget Configuration Store.
- Use only public interfaces of Provider Usage Ledger.
- Do not duplicate budget persistence.
- Do not duplicate usage persistence or aggregation.
- Do not call AI providers.
- Do not record requests.
- Do not execute Background Worker or Git commands.
- Data must remain isolated by project_id.

Events

Emit safe deterministic events for:

- budget_warning
- budget_blocked
- token_limit_warning
- token_limit_blocked
- pricing_unknown

Events may contain only safe identifiers, limits, and decision status.

Persistence

- Persist only safe events as deterministic JSON.
- Use atomic writes and file locking.
- Accept safe internally generated temporary filenames.
- Recover safely after restart.
- Reject corrupted event storage.
- Prevent path traversal and symbolic-link escape.
- Never store prompts, completions, files, images, credentials, or raw provider responses.
- Avoid nested non-reentrant locks.
- Tests involving locks must use bounded timeouts.

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Use TemporaryDirectory and unittest.mock.
- Use fake configuration store, usage ledger, project resolver, model resolver, clock, and policy resolver.
- Do not use network access, real providers, Git commands, or Background Worker.
- Every generated Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.

Testing Requirements

- Test missing configuration unrestricted behavior.
- Test per-request input-token blocking.
- Test per-request output-token blocking.
- Test per-request budget blocking.
- Test daily token blocking.
- Test monthly token blocking.
- Test daily budget blocking.
- Test monthly budget blocking.
- Test unknown-pricing allow.
- Test unknown-pricing warn.
- Test unknown-pricing block.
- Test exact evaluation order.
- Test deterministic blocked reasons.
- Test soft-warning thresholds.
- Test preflight does not record usage.
- Test UTC daily boundary.
- Test UTC monthly boundary.
- Test project isolation.
- Test provider and model validation.
- Test negative estimate rejection.
- Test unknown-field rejection.
- Test deterministic result serialization.
- Test event redaction.
- Test restart recovery.
- Test corrupted event storage rejection.
- Test temporary filenames.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_budget_preflight_engine.py
- agent/tests/test_provider_budget_preflight_engine.py
