Mission: Build Provider Budget Configuration Store

Goal

Create a small reusable multi-project store for AI budget and token-limit configurations.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Support dependency injection for project resolver and clock.
- Compatible with Python 3.12.

Budget Configuration Fields

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

Supported unknown_pricing_policy values:

- allow
- warn
- block

Validation

- Every configuration belongs to one project_id.
- Reject unknown projects using the injected project resolver.
- Monetary values must be non-negative numbers or null.
- Token limits must be non-negative integers or null.
- soft_warning_percent must be between 0 and 100.
- currency must be a three-letter uppercase code.
- unknown_pricing_policy must be allow, warn, or block.
- Reject unknown fields.
- Project data must remain isolated.
- Cross-project access must be rejected.

Public Interface

Provide ProviderBudgetConfigStore with:

- configure_budget(project_id, config)
- update_budget(project_id, changes)
- get_budget(project_id)
- remove_budget(project_id)
- list_budgets()
- status(project_id=None)
- latest_events(limit, project_id=None)

Persistence

- Persist configuration and events as deterministic JSON.
- Use atomic writes and file locking.
- Recover safely after restart.
- Reject corrupted storage.
- Accept safe internally generated temporary filenames.
- Prevent path traversal and symbolic-link escape.
- Never store secrets, prompts, completions, images, or provider responses.
- Never modify unrelated files.
- Avoid nested non-reentrant locking.
- Lock tests must use bounded timeouts.

Events

Emit safe events for:

- budget_configured
- budget_updated
- budget_removed

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Use TemporaryDirectory and unittest.mock.
- Do not use network, real providers, Git commands, or Background Worker.
- Every Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.

Testing Requirements

- Test configuration creation.
- Test configuration update.
- Test configuration removal.
- Test duplicate configuration behavior.
- Test unknown project rejection.
- Test negative monetary value rejection.
- Test negative token limit rejection.
- Test invalid soft-warning percentage.
- Test invalid currency.
- Test invalid unknown-pricing policy.
- Test unknown-field rejection.
- Test project isolation.
- Test deterministic listing.
- Test atomic persistence.
- Test restart recovery.
- Test corrupted storage rejection.
- Test temporary filenames.
- Test deterministic serialization.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and new unittest tests must pass.

Deliverables

- agent/providers/provider_budget_config_store.py
- agent/providers/provider_budget_config.example.json
- agent/tests/test_provider_budget_config_store.py
