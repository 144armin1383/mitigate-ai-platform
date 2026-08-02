Mission: Build Queue Enqueue Coordinator

Goal

Create a small reusable multi-project coordinator that accepts an already validated and deterministically ordered mission list, resolves the correct project queue, and enqueues the missions safely.

Architecture

- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Remain provider-neutral and project-neutral.
- Use dependency-injected public interfaces only.
- Fully typed and compatible with Python 3.12.
- Do not validate planner output.
- Do not generate mission identifiers.
- Do not execute missions.
- Do not invoke Planner, Worker, Controller, providers, or Git.

Input

The coordinator accepts:

- project_id
- queue_reference
- missions

Each mission must already contain:

- mission_id
- project_id
- request_id
- conversation_id
- plan_id
- step_id
- task_type
- provider_id
- model_id
- dependencies
- priority
- payload
- status
- created_at

Validation

- project_id must be a valid non-empty identifier.
- missions must be a non-empty list.
- Every mission must belong to project_id.
- mission_id values must be unique.
- Every dependency must reference another mission_id in the same submitted mission list.
- No self-dependencies are allowed.
- Mission status must be pending.
- Input mission ordering must already be dependency-safe.
- Every dependency must appear earlier than its dependant.
- Unknown fields must be rejected.
- Cross-project references must be rejected.
- queue_reference must belong to the selected project.
- Never derive unrestricted filesystem paths from mission payloads.

Dependencies

Inject public interfaces for:

- queue resolver
- clock
- event sink

The queue resolver must receive project_id and queue_reference.

Queue Compatibility

Support both:

- atomic batch queue interfaces
- non-atomic single-mission queue interfaces

Atomic Queue Behavior

- Prefer an atomic batch method when available.
- Detect only documented callable batch methods.
- Pass the complete validated mission list in its existing deterministic order.
- A successful batch enqueue must return all submitted mission identifiers.
- A batch failure must return queue_failed.
- Do not attempt individual enqueue after a failed atomic batch call.

Non-Atomic Queue Behavior

- Absence of batch support must not be treated as an error.
- Validate the complete mission set before the first enqueue.
- Enqueue missions individually in their existing dependency-safe order.
- Use the documented callable single-mission enqueue method.
- Do not reorder missions.
- Do not regenerate identifiers.
- Do not convert dependencies again.
- Successful individual enqueue of every mission must return accepted=true.
- An actual enqueue failure must return queue_failed.
- Report successfully enqueued mission identifiers safely when partial enqueue occurs.
- Never claim full success after partial enqueue.

Interface Detection

- Optional methods must be checked with callable().
- Do not treat a non-callable attribute as queue support.
- Support dependency-injected test queues and production adapters through explicit documented method names.
- Never invoke arbitrary attributes dynamically.
- Do not use eval, exec, compile, dynamic imports, or shell execution.

Result

Return a deterministic structured result containing:

- accepted
- project_id
- mission_ids
- enqueued_count
- atomic
- blocked_reason
- created_at

Failure Codes

- invalid_enqueue_request
- cross_project_reference
- queue_resolution_failed
- unsupported_queue_interface
- queue_failed
- partial_enqueue

Public Interface

Provide QueueEnqueueCoordinator with:

- enqueue(project_id, queue_reference, missions)
- validate_enqueue_request(project_id, queue_reference, missions)
- status()
- latest_events(limit, project_id=None)

Security and Privacy

- Never return secrets.
- Never expose environment-variable values.
- Never include authorization headers.
- Never expose unrestricted filesystem paths.
- Never log payload content.
- Never return raw queue exceptions.
- Convert dependency errors to safe failure codes.
- Never mutate submitted mission objects.

Structured Events

Emit safe deterministic events for:

- queue_resolution_started
- queue_resolution_failed
- queue_batch_started
- queue_batch_completed
- queue_individual_started
- mission_enqueued
- queue_failed
- partial_enqueue
- enqueue_completed

Events may include safe project identifiers, mission identifiers, counts, atomic status, and timestamps only.

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake queue resolver, atomic queue, non-atomic queue, failing queue, clock, and event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git, Planner, Worker, or Controller.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use eval, exec, compile, dynamic imports, or shell execution.
- Generated files must not contain the substring "eval(" anywhere.

Testing Requirements

- Test successful atomic batch enqueue.
- Test successful non-atomic enqueue.
- Test atomic method preferred when available.
- Test non-callable batch attribute ignored.
- Test unsupported queue interface.
- Test queue resolution failure.
- Test batch enqueue failure.
- Test individual enqueue failure.
- Test partial enqueue reporting.
- Test mission order preserved.
- Test mission identifiers preserved.
- Test dependencies preserved.
- Test duplicate mission rejection.
- Test unknown dependency rejection.
- Test self-dependency rejection.
- Test dependency-order violation rejection.
- Test cross-project mission rejection.
- Test queue-reference project mismatch.
- Test pending-status enforcement.
- Test input objects are not mutated.
- Test deterministic result serialization.
- Test result redaction.
- Test event redaction.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/orchestrator/queue_enqueue_coordinator.py
- agent/tests/test_queue_enqueue_coordinator.py
