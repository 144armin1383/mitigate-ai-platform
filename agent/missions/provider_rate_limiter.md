Mission: Build Provider Rate Limiter

Goal

Create a small reusable multi-project request rate limiter for AI provider execution.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Support dependency injection for project resolver and clock.
- Fully typed and compatible with Python 3.12.

Rate Limit Configuration

Each project configuration must support:

- project_id
- enabled
- request_limit
- window_seconds
- burst_limit
- created_at
- updated_at

Validation

- Every configuration belongs to exactly one project_id.
- Reject unknown projects using the injected project resolver.
- request_limit must be a positive integer.
- window_seconds must be a positive integer.
- burst_limit must be a non-negative integer or null.
- Reject unknown fields.
- Project data must remain isolated.
- Cross-project access must be rejected.

Request Registration

Each request registration must support:

- project_id
- request_id
- timestamp

Rules

- request_id must be unique within the project.
- Duplicate request registration must not count twice.
- Expired requests must be removed deterministically.
- Rate limits must be enforced independently per project.
- Concurrent checks and registrations must not permit more requests than the configured limit.
- Missing configuration must return an unrestricted allowed result.
- Disabled configuration must return an unrestricted allowed result.
- All time calculations must use UTC.

Decision Result

Return:

- allowed
- blocked_reason
- remaining_requests
- reset_at
- project_id
- request_id
- evaluated_at

Public Interface

Provide a ProviderRateLimiter class with:

- configure_limit(project_id, config)
- update_limit(project_id, changes)
- get_limit(project_id)
- remove_limit(project_id)
- check_request(project_id, request_id, timestamp=None)
- register_request(project_id, request_id, timestamp=None)
- check_and_register(project_id, request_id, timestamp=None)
- remaining(project_id, timestamp=None)
- status(project_id=None)
- latest_events(limit, project_id=None)

Atomicity and Concurrency

- check_and_register() must be atomic.
- Concurrent callers must never exceed the configured request limit.
- Duplicate request identifiers must not consume additional quota.
- Use one clear lock boundary per public mutating operation.
- Internal helpers called while a lock is held must not reacquire the same non-reentrant lock.
- Avoid nested file locks.
- Locking tests must use bounded timeouts and must never hang.

Persistence

- Persist configuration, request-window state, and events as deterministic JSON.
- Use atomic writes and file locking.
- Recover safely after restart.
- Reject corrupted storage.
- Accept safe internally generated temporary filenames.
- Prevent path traversal and symbolic-link escape.
- Never store prompts, completions, images, credentials, authorization headers, or provider responses.
- Never modify unrelated files.

Events

Emit safe deterministic events for:

- rate_limit_configured
- rate_limit_updated
- rate_limit_removed
- request_registered
- rate_limit_warning
- rate_limit_blocked

Events may contain only safe identifiers, counters, and timestamps.

Testing Policy

- Use unittest only.
- Never use pytest.
- Do not add dependencies.
- Use unittest.mock and TemporaryDirectory.
- Use fake project resolver and fake clock.
- Do not use network, providers, Git commands, or Background Worker.
- Every generated Python file must pass py_compile.
- Tests must run from repository root.
- Do not modify sys.path.
- Concurrency tests must use bounded timeouts.

Testing Requirements

- Test configuration creation.
- Test configuration update.
- Test configuration removal.
- Test unknown project rejection.
- Test invalid request limit.
- Test invalid window seconds.
- Test invalid burst limit.
- Test missing configuration unrestricted behavior.
- Test disabled configuration unrestricted behavior.
- Test request registration.
- Test duplicate request registration.
- Test rate-limit blocking.
- Test remaining request count.
- Test reset time.
- Test expired request cleanup.
- Test UTC handling.
- Test project isolation.
- Test two projects with different limits.
- Test atomic check_and_register.
- Test concurrent request enforcement.
- Test restart recovery.
- Test atomic persistence.
- Test safe temporary filenames.
- Test corrupted storage rejection.
- Test deterministic serialization.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/providers/provider_rate_limiter.py
- agent/providers/provider_rate_limiter.example.json
- agent/tests/test_provider_rate_limiter.py

Duplicate Request and Atomic Registration Contract

- check_and_register() must perform duplicate detection, limit checking, and registration within one atomic critical section.
- For a given project_id and request_id, only the first successful registration may return allowed=true.
- A repeated request_id within the active window must not be treated as a new successful registration.
- A duplicate check_and_register() call must return allowed=false with a deterministic blocked_reason such as duplicate_request.
- Duplicate request identifiers must not consume additional quota.
- Concurrent calls using the same project_id and request_id must produce exactly one successful result.
- All other concurrent duplicate calls must return allowed=false.
- Duplicate registration must not update the original timestamp.
- Duplicate registration must not extend the rate-limit window.
- check_request() may report whether capacity exists, but check_and_register() must guarantee exactly-once registration semantics.
- Duplicate detection must occur before available-capacity evaluation.
- The test_atomic_check_and_register unittest must produce exactly one true result.
- All existing and newly generated unittest tests must pass.
