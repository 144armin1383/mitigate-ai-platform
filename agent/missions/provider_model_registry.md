Mission: Build Provider and Model Registry

Goal

Create the reusable multi-project registry for AI providers, models, task assignments, model discovery, health checks, and deterministic fallback selection.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Core modules must remain provider-neutral and project-neutral.
- Support dependency injection for provider adapters, secret store, project resolver, clock, and identifier generation.
- Fully typed and compatible with Python 3.12.

Supported Provider Identifiers

- openai
- anthropic
- google
- openrouter
- azure_openai
- ollama
- local

Additional providers must be addable without modifying existing core logic.

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

- Never store API keys, bearer tokens, passwords, or secret values in persisted JSON.
- Never store secrets in GitHub.
- Store only environment-variable names or external secret references.
- Never expose complete secret values through public methods.
- Never expose environment-variable values.
- Public output may show only whether credentials are configured.
- Secret references must be strictly validated.
- Provider exceptions must be converted into safe structured errors.
- Never store authorization headers or raw provider responses.

Model Configuration

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

Task Assignments

Support these task types:

- planning
- coding
- code_review
- validation
- vision
- chat
- summarization
- fast_tasks
- fallback

Each assignment must support:

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

Assignment Rules

- Every assignment belongs to exactly one project_id.
- Assignments must remain isolated per project.
- A model must belong to its configured provider.
- Disabled or unavailable providers and models cannot be selected.
- Vision assignments require supports_vision=true.
- Tool-required assignments require supports_tools=true.
- Fallback chains must not contain duplicates.
- Fallback chains must not contain the primary model.
- Fallback order must remain deterministic.
- Cross-project assignment access must be rejected.
- Unknown task types must be rejected.

Provider Discovery

Provide dependency-injected interfaces for:

- listing available provider models
- refreshing model metadata
- validating model availability
- testing provider connectivity
- reading capability metadata

Requirements

- Tests must never call real providers.
- Refresh failure must preserve the previous valid model registry.
- Deprecated models must be marked deprecated, not silently deleted.
- Discovery must never expose credentials.

Selection

Provide deterministic methods:

- select_model(project_id, task_type)
- select_fallback(project_id, task_type, failed_provider_id, failed_model_id)
- validate_assignment(project_id, task_type)
- get_active_configuration(project_id)

Selection Rules

- Prefer the configured primary model when available.
- Skip disabled, unavailable, deprecated, or incompatible models.
- Evaluate fallback entries in configured order.
- Return a safe no-model-available result when none remain.
- Never select models belonging to another project.
- Preserve exact provider and model identifiers in selection results.

Public Interface

Provide a ProviderModelRegistry class with:

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
- status(project_id=None)
- latest_events(limit, project_id=None)

Persistence

- Persist providers, models, assignments, and events as deterministic JSON.
- Use atomic writes.
- Use file locking.
- Recover safely after restart.
- Reject corrupted state rather than silently overwriting it.
- Prevent path traversal and symbolic-link escape.
- Never persist credentials.
- Never modify unrelated files.
- Tests involving locks must use bounded timeouts and never hang.

Structured Events

Emit safe events for:

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

Events must never contain secrets, prompts, completions, authorization headers, raw provider responses, or unrestricted filesystem paths.

Project Integration

- Use project_id through a dependency-injected project resolver.
- Unknown projects must be rejected.
- Provider configuration and assignments must remain isolated per project.
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
- Tests must not run Git commands.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Every generated Python file must pass py_compile.

Testing Requirements

- Test provider creation and update.
- Test provider enable and disable.
- Test missing credential reference handling.
- Test secrets are never serialized.
- Test provider health success and failure.
- Test model registration and deterministic listing.
- Test model enable, disable, and deprecation.
- Test provider-model ownership validation.
- Test task assignment.
- Test invalid task type rejection.
- Test project isolation.
- Test vision capability enforcement.
- Test tool capability enforcement.
- Test primary selection.
- Test fallback selection.
- Test duplicate fallback rejection.
- Test unavailable model skipping.
- Test disabled provider skipping.
- Test no-model-available result.
- Test refresh success.
- Test refresh failure preserving existing registry.
- Test restart recovery.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test event redaction.
- Test two independent projects with different assignments.
- Test adding another provider without core changes.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_model_registry.py
- agent/providers/provider_registry.example.json
- agent/tests/test_provider_model_registry.py
