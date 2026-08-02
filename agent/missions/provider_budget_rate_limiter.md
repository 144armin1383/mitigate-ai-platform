Mission: Build Provider Budget and Rate Limiter

Goal

Create a reusable multi-project budget, token-limit, and request-rate-limit service that performs deterministic preflight checks before AI provider execution.

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
- request_rate_limit
- rate_limit_window_seconds
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

- Every budget configuration belongs to exactly one project_id.
- Unknown projects must be rejected through the injected project resolver.
- Monetary values must be non-negative numbers or null.
- Token and request limits must be non-negative integers or null.
- soft_warning_percent must be between 0 and 100.
- rate_limit_window_seconds must be a positive integer.
- currency must be a validated uppercase currency code.
- unknown_pricing_policy must be allow, warn, or block.
- Project configurations must remain fully isolated.
- Cross-project access must be rejected.
- Missing configuration must return a safe unrestricted result unless an injected policy explicitly requires blocking.

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

- estimated_input_tokens and requested_output_tokens must be non-negative integers.
- estimated_cost must be non-negative or null.
- request_id must be validated.
- provider_id and model_id must be validated through the injected model resolver when configured.
- request_timestamp must be timezone-aware UTC or safely normalized to UTC.
- Cross-project model or usage references must be rejected.

Budget Check Result

Return a deterministic structured result containing:

- allowed
- warning
- blocked_reason
- pricing_known
- remaining_daily_budget
- remaining_monthly_budget
- remaining_daily_tokens
- remaining_monthly_tokens
- remaining_rate_limit
- evaluated_at
- project_id
- request_id

Evaluation Order

Evaluate limits in this exact order:

1. Per-request input token limit
2. Per-request output token limit
3. Per-request budget
4. Daily token limit
5. Monthly token limit
6. Daily budget
7. Monthly budget
8. Request rate limit
9. Unknown pricing policy

Requirements

- Return deterministic blocked reasons.
- Hard limits must block before provider execution.
- Soft thresholds must warn without blocking.
- Preflight checks must never deduct usage.
- Actual usage must be recorded only by Provider Usage Ledger.
- Failed provider requests may still be counted by the Usage Ledger when actual usage is known.
- Unknown usage must never be fabricated.
- Budget evaluation must use UTC boundaries.
- Daily and monthly usage must be read through the injected Usage Ledger interface.
- Do not duplicate usage aggregation logic already provided by Provider Usage Ledger.

Unknown Pricing

- Unknown pricing must never be treated as zero.
- pricing_known must be false when estimated_cost is null.
- allow policy permits the request without a warning unless another threshold is exceeded.
- warn policy permits the request and sets warning=true.
- block policy rejects the request with a deterministic blocked_reason.
- Never claim an exact cost when pricing is unavailable.

Soft Warning Thresholds

- Emit warnings when usage reaches or exceeds soft_warning_percent of any configured daily or monthly hard limit.
- Soft warning evaluation must not block.
- Warning behavior must be deterministic.
- Missing limits must not produce warnings.
- Warning events must not contain secrets or request content.

Rate Limiting

- Apply rate limits independently per project.
- Use a deterministic fixed-window or sliding-window implementation.
- Persist sufficient rate-limit state for restart recovery.
- register_request() must atomically record one accepted request.
- Duplicate request identifiers must not count twice.
- Concurrent checks and registrations must not permit execution above the configured limit.
- Expired entries must be cleaned deterministically.
- Rate-limit state must remain isolated per project.
- Tests involving concurrency must use bounded timeouts and must never hang.

Public Interface

Provide a ProviderBudgetRateLimiter class with:

- configure_budget(project_id, config)
- update_budget(project_id, changes)
- get_budget(project_id)
- remove_budget(project_id)
- check_request(project_id, request_estimate)
- register_request(project_id, request_id, timestamp=None)
- remaining_limits(project_id, timestamp=None)
- status(project_id=None)
- latest_events(limit, project_id=None)

Integration Contract

- Use Provider Usage Ledger through a dependency-injected usage reader.
- Use Provider Model Registry through a dependency-injected model resolver.
- Use project_id through a dependency-injected project resolver.
- Never access another project's budget, rate-limit state, or usage summaries.
- The same provider and model may have different limits in different projects.
- Mitigate must remain a project profile, not hardcoded behavior.

Persistence

- Persist budget configuration, rate-limit state, and events as deterministic JSON.
- Use atomic writes.
- Use file locking.
- Recover safely after restart.
- Reject corrupted storage rather than silently overwriting it.
- Prevent path traversal and symbolic-link escape.
- Never store prompts, completions, images, uploaded files, credentials, authorization headers, or raw provider responses.
- Never modify unrelated files.
- Public methods must not acquire the same non-reentrant lock twice.
- Use private lock-free helpers for nested operations.
- Atomic temporary filenames must be accepted when internally generated.
- Temporary files must remain inside the configured storage directory.
- Tests involving locking must use bounded timeouts.

Structured Events

Emit safe deterministic events for:

- budget_configured
- budget_updated
- budget_removed
- budget_warning
- budget_blocked
- token_limit_warning
- token_limit_blocked
- rate_limit_warning
- rate_limit_blocked
- pricing_unknown
- request_registered

Events may contain:

- event
- project_id
- request_id
- provider_id
- model_id
- task_type
- timestamp
- safe limit status

Never include:

- prompts
- completions
- images
- uploaded files
- message text
- credentials
- authorization headers
- raw provider responses
- unrestricted filesystem paths

Admin Panel Integration Contract

The future panel must be able to:

- configure daily and monthly budgets
- configure per-request budget
- configure daily and monthly token limits
- configure input and output token limits
- configure request rate limits
- configure unknown pricing policy
- view current remaining limits
- view warnings and blocked requests
- distinguish pricing-known and pricing-unknown decisions
- filter status by project

Do not build the web UI in this mission.
Create only the reusable service layer.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use tempfile and TemporaryDirectory.
- Tests must not perform network access.
- Tests must not call real providers.
- Tests must not execute Git commands.
- Tests must not execute Background Worker.
- Use fake project resolver, fake usage reader, fake model resolver, fake pricing resolver, fake policy resolver, and fake clock.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports such as agent.providers.provider_budget_rate_limiter.
- Do not modify sys.path inside tests.
- Locking and concurrency tests must use bounded timeouts.

Testing Requirements

- Test budget creation and update.
- Test budget removal.
- Test missing configuration unrestricted behavior.
- Test negative-value rejection.
- Test invalid currency rejection.
- Test invalid unknown-pricing policy rejection.
- Test soft-warning threshold.
- Test per-request budget blocking.
- Test per-request input-token blocking.
- Test per-request output-token blocking.
- Test daily token blocking.
- Test monthly token blocking.
- Test daily budget blocking.
- Test monthly budget blocking.
- Test rate-limit blocking.
- Test unknown-pricing allow policy.
- Test unknown-pricing warning policy.
- Test unknown-pricing block policy.
- Test deterministic evaluation order.
- Test deterministic blocked reasons.
- Test preflight does not deduct usage.
- Test request registration.
- Test duplicate request registration.
- Test concurrent rate-limit checks.
- Test rate-limit expiration.
- Test restart recovery.
- Test project isolation.
- Test provider and model validation.
- Test two projects with different budgets.
- Test UTC daily and monthly boundaries.
- Test atomic persistence.
- Test internally generated temporary filenames.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test structured event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_budget_rate_limiter.py
- agent/providers/provider_budget.example.json
- agent/tests/test_provider_budget_rate_limiter.py
