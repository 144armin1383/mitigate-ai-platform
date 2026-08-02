Mission: Build Multi-Project Platform Foundation

Goal

Make the autonomous agent platform reusable across multiple websites, companies, repositories, and deployment targets without modifying reusable core source code.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Core agent modules must remain project-neutral.
- Never hardcode Mitigate-specific company names, domains, repository paths, WordPress paths, credentials, queue paths, upload paths, deployment targets, or policy values inside reusable core modules.
- Project-specific behavior must come from validated project profiles and dependency injection.
- Support multiple independent projects simultaneously.
- Fully typed and compatible with Python 3.12.

Project Profile

Each project profile must define:

- project_id
- display_name
- repository_root
- default_branch
- project_type
- mission_queue_path
- conversations_path
- uploads_metadata_path
- uploads_directory
- events_path
- reports_path
- worker_heartbeat_path
- deployment_target
- allowed_domains
- enabled_providers
- policy_profile
- created_at
- updated_at
- status

Supported project states:

- active
- suspended
- archived

Supported initial project types:

- generic
- wordpress
- python
- node
- nextjs
- react
- static

Project Registry

Create a persistent ProjectRegistry responsible for:

- create_project
- update_project
- get_project
- list_projects
- suspend_project
- activate_project
- archive_project
- delete_project
- validate_project
- resolve_project_paths
- status
- latest_events

Requirements

- Persist project profiles atomically as deterministic JSON.
- Recover safely after restart.
- Use file locking to prevent concurrent corruption.
- Reject duplicate project identifiers.
- Validate project identifiers strictly.
- Project identifiers must not contain path traversal, separators, control characters, or whitespace.
- Validate repository_root as an existing Git repository when validation is requested.
- Never create or modify a repository during profile validation.
- Resolve all project-specific paths relative to a configurable private data root unless explicitly absolute and permitted.
- Prevent symbolic-link escape.
- Never expose unrestricted filesystem paths in safe public responses.
- Never store secrets or provider API keys in project profiles.
- Store only provider identifiers and non-secret configuration references.
- Reject unknown fields.
- Deterministic ordering must use project_id.
- Deleting an active project must require force=True.
- Archiving must not delete project data.
- Delete operations must affect registry metadata only unless explicit cleanup is requested by a separate service.
- Core source code must not need modification when adding a new project profile.

Project Isolation

- Every conversation must belong to exactly one project_id.
- Every message must belong to exactly one project_id.
- Every upload must belong to exactly one project_id.
- Every high-level request must belong to exactly one project_id.
- Every plan must belong to exactly one project_id.
- Every mission must belong to exactly one project_id.
- Every queue record must belong to exactly one project_id.
- Every event must belong to exactly one project_id.
- Every report must belong to exactly one project_id.
- Every worker heartbeat must belong to exactly one project_id.
- Data belonging to one project must never be visible to or modify another project.
- Queue storage must remain isolated per project.
- Conversation storage must remain isolated per project.
- Upload storage must remain isolated per project.
- Event and report storage must remain isolated per project.
- Repository operations must always use the selected project's repository_root.
- Default branch operations must always use the selected project's default_branch.
- Cross-project dependencies must be rejected.
- Cross-project mission references must be rejected.
- Cross-project upload references must be rejected.
- Cross-project conversation access must be rejected.

Existing Component Integration Contracts

Provide adapters or service methods suitable for later integration with:

- agent.ai.ai_planner
- agent.runtime.mission_queue
- agent.runtime.background_worker
- agent.api.private_admin_api
- agent.api.ai_chat_gateway
- agent.ai.autonomous_controller

Do not rewrite those existing components in this mission.

Provide a ProjectContext object containing:

- project_id
- repository_root
- default_branch
- queue_path
- conversations_path
- uploads_metadata_path
- uploads_directory
- events_path
- reports_path
- worker_heartbeat_path
- deployment_target
- allowed_domains
- enabled_providers
- policy_profile
- project_type

ProjectContext must:

- be immutable after construction
- validate all fields
- provide deterministic dictionary serialization
- never include secrets
- be suitable for dependency injection into existing services

Mitigate Migration Profile

- Provide a project-profile template for Mitigate as data, not hardcoded behavior.
- Do not include credentials, API keys, tokens, or private secrets.
- The template may use placeholders for environment-specific paths.
- The reusable agent core must behave the same for Mitigate and any second project.
- Adding a second project must require only a new profile.

Structured Events

Emit deterministic structured events for:

- project_created
- project_updated
- project_suspended
- project_activated
- project_archived
- project_deleted
- project_validation_succeeded
- project_validation_failed

Each event must contain:

- event
- project_id
- timestamp
- safe status information

Never include secrets, raw exceptions, unrestricted filesystem paths, environment variables, or provider keys.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use tempfile and TemporaryDirectory.
- Tests must not perform real network access.
- Tests must not call real AI providers.
- Tests must not execute Background Worker.
- Tests must not run real Git mutations.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports such as agent.projects.project_registry.
- Do not modify sys.path inside tests.

Testing Requirements

- Test project creation.
- Test deterministic project listing.
- Test duplicate project rejection.
- Test invalid project identifiers.
- Test path traversal rejection.
- Test project update.
- Test suspend and activate.
- Test archive.
- Test protected active deletion.
- Test forced deletion.
- Test atomic persistence.
- Test restart recovery.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test immutable ProjectContext.
- Test two independent project profiles.
- Test queue-path isolation.
- Test conversation-path isolation.
- Test upload-path isolation.
- Test event-path isolation.
- Test report-path isolation.
- Test worker-heartbeat isolation.
- Test cross-project mission rejection.
- Test cross-project upload rejection.
- Test cross-project conversation rejection.
- Test repository-root selection.
- Test default-branch selection.
- Test Mitigate profile is data-driven.
- Test adding a second project without core changes.
- Test secret values are never serialized.
- Test unrestricted paths are absent from safe public responses.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/projects/project_registry.py
- agent/projects/mitigate.project.example.json
- agent/tests/test_project_registry.py
