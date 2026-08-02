Mission: Build Provider Budget Limit Evaluator

Goal

Create a small reusable engine that evaluates one AI request against project budget and token limits before provider execution.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Read configuration through dependency injection.
- Read usage summaries through dependency injection.
- Validate projects and models through dependency injection.
- Fully typed and compatible with Python 3.12.

Request Estimate

Fields:

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
- request_timestamp must be timezone-aware UTC.
- Reject unknown fields.
- Reject cross-project references.

Decision Result

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
9. Soft warning threshold

Rules

- Hard limits block before provider execution.
- Soft warnings do not block.
- Evaluation must never record or deduct usage.
- Missing budget configuration returns allowed=true.
- Missing individual limits do not block.
- Use UTC daily and monthly boundaries.
- Return deterministic blocked reasons.
- Unknown usage or cost must never be fabricated.

Unknown Pricing

- estimated_cost=null means pricing_known=false.
- allow permits the request.
- warn permits the request and sets warning=true.
- block rejects the request.
- Unknown pricing must never be treated as zero.

Public Interface

Provide a ProviderBudgetLimitEvaluator class with:

- check_request(project_id, request_estimate)
- remaining_limits(project_id, timestamp=None)

Integration

- Use only public interfaces of the injected budget store and usage ledger.
- Do not persist budgets.
- Do not persist usage.
- Do not emit events.
- Do not call AI providers.
- Do not execute Git or Background Worker.

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Use TemporaryDirectory and unittest.mock.
- Use fake budget store, usage ledger, project resolver, model resolver, and clock.
- Do not use network, providers, Git, or Background Worker.
- Every Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.

Testing Requirements

- Test missing configuration allowed result.
- Test per-request input-token block.
- Test per-request output-token block.
- Test per-request budget block.
- Test daily token block.
- Test monthly token block.
- Test daily budget block.
- Test monthly budget block.
- Test unknown-pricing allow.
- Test unknown-pricing warn.
- Test unknown-pricing block.
- Test exact evaluation order.
- Test deterministic blocked reasons.
- Test soft warning behavior.
- Test preflight does not record usage.
- Test UTC daily and monthly boundaries.
- Test project isolation.
- Test provider and model validation.
- Test negative estimate rejection.
- Test unknown-field rejection.
- Test deterministic result serialization.
- Test unrelated files remain unchanged.
- All existing and new unittest tests must pass.

Deliverables

- agent/providers/provider_budget_limit_evaluator.py
- agent/tests/test_provider_budget_limit_evaluator.py

Generated Test Safety Contract

- Generated source and test files must not contain the substring "eval(" anywhere.
- Do not call Python eval().
- Do not mention "eval(" inside comments, docstrings, strings, test names, fixture names, or assertions.
- Use explicit comparisons, dictionary lookups, helper functions, dataclass construction, and normal unittest assertions instead.
- Do not use exec(), compile(), __import__(), subprocess shell execution, or dynamic code evaluation.
- Test names should use words such as evaluation, decision, ordering, or result without forming the forbidden substring.
- Every generated deliverable must pass Mission Runner forbidden-content validation before py_compile and unittest execution.
- All existing and newly generated unittest tests must pass.

Soft Warning Non-Blocking Contract

- A soft warning threshold must never block a request by itself.
- When projected usage reaches or exceeds soft_warning_percent but remains within the configured hard limit:
  - allowed must be true.
  - warning must be true.
  - blocked_reason must be null.
- A request may be blocked only when an actual configured hard limit is exceeded or an explicit block policy applies.
- Soft warning evaluation must occur only after all hard-limit checks pass.
- Reaching the warning threshold is not equivalent to exceeding the hard limit.
- The test_soft_warning_behavior unittest must verify allowed=true and warning=true.
- All existing and newly generated unittest tests must pass.
