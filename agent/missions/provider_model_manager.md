Mission: Build Provider and Model Manager

Goal

Create a reusable multi-project provider and model management layer for the autonomous agent platform.

The manager must allow the future admin panel to configure AI providers, available models, task-specific model assignments, fallback order, budgets, limits, and provider health without storing secrets in GitHub.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Keep provider configuration separate from provider credentials.
- Core modules must remain provider-neutral and project-neutral.
- Support dependency injection for provider clients, clocks, identifier generation, usage readers, and health checks.
- Fully typed and compatible with Python 3.12.

Supported Providers

Support configurable provider identifiers including:

- openai
- anthropic
- google
- openrouter
- azure_openai
- ollama
- local

The architecture must allow additional providers without changing existing core logic.

Provider Configuration

Each provider configuration must support:

- provider_id
- display_name
- enabled
- credential_reference
- base_url_reference
- organization_reference
- project_reference
- default_timeout_seconds
- maximum_retries
- created_at
- updated_at
- status

Supported provider states:

- active
- disabled
- degraded
- unavailable

Security

- Never store API keys, bearer tokens, passwords, or secret values in registry JSON.
- Never store secrets in GitHub.
- Store only environment-variable names or external secret references.
- Never return complete secret values through public methods.
- Never include authorization headers or credentials in logs.
- Never expose environment-variable values.
- Credential updates must replace the secret through a dependency-injected secret-store interface.
- Public responses may show only whether credentials are configured.
- Secret references must be validated.
- Reject suspicious secret references containing path traversal or control characters.
- Provider exceptions must be converted to safe structured errors.
- Raw provider responses must not be stored unless explicitly sanitized.

Model Registry

Each model configuration must support:

- model_id
- provider_id
- display_name
- enabled
- capabilities
- context_window
- maximum_output_tokens
- supports_text
- supports_vision
- supports_tools
- supports_json
- supports_reasoning
- supports_streaming
- input_cost_reference
- output_cost_reference
- created_at
- updated_at
- status

Supported model states:

- available
- disabled
- unavailable
- deprecated

Model identifiers and provider identifiers must be strictly validated.

Task-Specific Model Assignments

Support independent model assignments for:

- planning
- coding
- code_review
- validation
- vision
- chat
- summarization
- fast_tasks
- fallback

Each assignment must include:

- project_id
- task_type
- primary_provider_id
- primary_model_id
- fallback_chain
- maximum_input_tokens
- maximum_output_tokens
- timeout_seconds
- maximum_cost_per_request
- reasoning_level
- temperature
- enabled

Requirements

- Every model assignment must belong to exactly one project_id.
- Provider and model assignments must remain isolated per project.
- A model must belong to its configured provider.
- Disabled or unavailable models cannot be selected as primary models.
- Vision assignments must use a vision-capable model.
- Tool-use assignments must use a tool-capable model when required.
- Fallback chains must not contain duplicates.
- Fallback chains must not contain the primary model.
- Fallback chains must preserve deterministic ordering.
- Circular fallback references must be rejected.
- Invalid task types must be rejected.
- Adding a new project must not require core source-code changes.

Provider and Model Discovery

Provide interfaces suitable for:

- listing provider-supported models
- refreshing available models
- validating model availability
- testing provider connectivity
- reading provider capability metadata

Requirements

- Real provider calls must be behind dependency-injected provider adapters.
- Tests must use fake provider adapters only.
- Discovery failure must not delete the last known valid model registry.
- Refresh must be atomic.
- Unknown provider models may be added only after validation.
- Deprecated models must be marked deprecated, not silently deleted.
- Model discovery must never expose credentials.

Selection Logic

Provide deterministic selection methods:

- select_model(project_id, task_type)
- select_fallback(project_id, task_type, failed_provider_id, failed_model_id)
- list_assignments(project_id)
- validate_assignment(project_id, task_type)
- get_active_configuration(project_id)

Selection behavior:

- Return the primary model when available.
- Skip disabled, unavailable, or incompatible models.
- Use fallback order deterministically.
- Stop when no valid model remains.
- Return a safe structured no-model-available result.
- Never silently select a model from another project.
- Never silently select a provider that is disabled.
- Preserve exact provider and model identifiers in usage reports.

Budget and Limit Controls

Support per-project limits:

- monthly_budget
- daily_budget
- per_request_budget
- monthly_token_limit
- daily_token_limit
- per_request_input_token_limit
- per_request_output_token_limit
- request_rate_limit
- enabled

Requirements

- Reject requests that exceed configured hard limits.
- Support soft-warning thresholds.
- Budget evaluation must be deterministic.
- Missing pricing data must be reported as unknown, not zero.
- Do not claim exact cost when pricing metadata is unavailable.
- Budget checks must occur before provider execution.
- Usage updates must be atomic.
- Budget state must recover after restart.

Usage Records

Record safe structured usage metadata:

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

- Never store prompts, completions, screenshots, message content, or secrets in usage records.
- Usage records must remain isolated per project.
- Usage summaries must be deterministic.
- Support daily and monthly summaries.
- Support summaries by provider, model, task type, and project.
- Invalid negative token or cost values must be rejected.
- Unknown cost must remain null.

Public Service Interface

Provide a ProviderModelManager class with methods suitable for future Admin API and Dashboard integration:

- create_provider(config)
- update_provider(provider_id, changes)
- enable_provider(provider_id)
- disable_provider(provider_id)
- get_provider(provider_id)
- list_providers()
- register_model(config)
- update_model(provider_id, model_id, changes)
- enable_model(provider_id, model_id)
- disable_model(provider_id, model_id)
- get_model(provider_id, model_id)
- list_models(provider_id=None)
- refresh_models(provider_id)
- test_provider(provider_id)
- assign_model(project_id, task_type, assignment)
- remove_assignment(project_id, task_type)
- get_assignment(project_id, task_type)
- list_assignments(project_id)
- select_model(project_id, task_type)
- select_fallback(project_id, task_type, failed_provider_id, failed_model_id)
- configure_budget(project_id, config)
- get_budget(project_id)
- check_budget(project_id, request_estimate)
- record_usage(record)
- usage_summary(project_id, period)
- status(project_id=None)
- latest_events(limit, project_id=None)

Persistence

- Persist providers, models, assignments, budgets, usage metadata, and events as deterministic JSON.
- Use atomic writes.
- Use file locking to prevent corruption.
- Recover safely after restart.
- Reject corrupted state instead of silently overwriting it.
- Keep provider credentials outside persisted configuration.
- Keep project data isolated.
- Prevent symbolic-link and path traversal escape.
- Unrelated files must never be modified.

Structured Events

Emit deterministic safe events for:

- provider_created
- provider_updated
- provider_enabled
- provider_disabled
- provider_health_succeeded
- provider_health_failed
- model_registered
- model_updated
- model_enabled
- model_disabled
- model_deprecated
- models_refreshed
- assignment_created
- assignment_updated
- assignment_removed
- fallback_selected
- budget_configured
- budget_warning
- budget_blocked
- usage_recorded

Each event must contain safe identifiers and status only.

Never include:

- API keys
- secret values
- prompts
- completions
- raw provider responses
- uploaded image content
- unrestricted filesystem paths
- authorization headers

Admin Panel Integration Contract

The future panel must be able to:

- view the active provider and model
- view task-specific assignments
- change the primary model
- configure fallback order
- enable or disable providers
- enable or disable models
- test provider availability
- refresh provider model lists
- view whether credentials are configured
- replace provider credentials
- configure budgets and token limits
- view token and estimated-cost reports
- filter usage by project, provider, model, and task
- see which model handled each mission
- see whether fallback was used

Do not build the web UI in this mission.
Create the reusable service layer only.

Project Integration

- Use project_id from agent.projects.project_registry.
- Reject unknown projects through a dependency-injected project resolver.
- Never access another project's assignments, budgets, or usage.
- The same provider may be configured differently for different projects.
- The same model may be primary for one project and disabled for another.
- Mitigate must be treated as one project profile, not hardcoded behavior.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use tempfile and TemporaryDirectory.
- Tests must not perform real network access.
- Tests must not call real AI providers.
- Tests must not execute Git commands.
- Tests must not execute Background Worker.
- Use fake provider adapters, fake secret store, fake project resolver, fake clock, and deterministic identifier generation.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports such as agent.providers.provider_model_manager.
- Do not modify sys.path inside tests.
- Tests involving locks or concurrency must use bounded timeouts and must never hang.

Testing Requirements

- Test provider creation.
- Test provider update.
- Test provider enable and disable.
- Test missing credential-reference handling.
- Test secrets are never serialized.
- Test provider health success and failure.
- Test model registration.
- Test deterministic model listing.
- Test model enable and disable.
- Test deprecated model handling.
- Test provider-model ownership validation.
- Test task assignment.
- Test invalid task type rejection.
- Test project isolation.
- Test vision capability enforcement.
- Test tool capability enforcement.
- Test deterministic primary selection.
- Test fallback selection.
- Test duplicate fallback rejection.
- Test circular fallback rejection.
- Test unavailable model skipping.
- Test disabled provider skipping.
- Test no-model-available result.
- Test model refresh success.
- Test model refresh failure preserving previous registry.
- Test per-project budget configuration.
- Test budget warning.
- Test budget blocking.
- Test unknown pricing handling.
- Test atomic usage recording.
- Test daily usage summary.
- Test monthly usage summary.
- Test summary by provider.
- Test summary by model.
- Test summary by task type.
- Test invalid negative usage rejection.
- Test restart recovery.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test structured event redaction.
- Test two independent projects with different model assignments.
- Test adding another provider without core changes.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_model_manager.py
- agent/providers/provider_config.example.json
- agent/tests/test_provider_model_manager.py
