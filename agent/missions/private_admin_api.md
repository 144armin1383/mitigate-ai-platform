Mission: Build Private Admin API

Goal

Create a secure private HTTP API that allows an authenticated administrator to submit high-level development requests, invoke AI Planner, enqueue generated missions, inspect Mission Queue, read worker status, and control mission lifecycle without using SSH.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Use http.server.ThreadingHTTPServer.
- Use the existing AI Planner.
- Use the existing persistent Mission Queue.
- Do not execute missions directly inside HTTP request handlers.
- Background Worker remains responsible for mission execution.
- Keep API, Queue, Planner, and Worker responsibilities separated.
- Fully typed and compatible with Python 3.12.

Security

- Require bearer-token authentication for every endpoint except health.
- Read the admin token only from environment variable MITIGATE_AI_ADMIN_TOKEN.
- Never store the token in source code, repository files, logs, reports, or API responses.
- Refuse startup if the token is missing or empty.
- Compare authentication tokens with hmac.compare_digest.
- Bind to 127.0.0.1 by default.
- Never bind publicly unless explicitly configured.
- Reject oversized request bodies.
- Default maximum request size must be 1 MiB.
- Accept application/json only for JSON request endpoints.
- Return JSON error responses without stack traces.
- Never expose filesystem paths, environment variables, provider keys, secrets, or raw exceptions.
- Add deterministic request identifiers.
- Add basic in-memory rate limiting per client.
- Reject malformed JSON.
- Reject unknown fields on write endpoints.
- Validate mission identifiers and prevent path traversal.
- Never execute raw shell commands from API input.
- Never permit arbitrary file reads or writes.
- Never permit direct Git commands through the API.

Endpoints

- GET /health
- GET /v1/status
- POST /v1/requests
- GET /v1/missions
- GET /v1/missions/{mission_id}
- POST /v1/missions/{mission_id}/cancel
- POST /v1/missions/{mission_id}/resume
- POST /v1/missions/{mission_id}/retry
- GET /v1/events
- GET /v1/reports/latest

POST /v1/requests

- Accept a high-level development request.
- Validate request title, description, priority, and optional metadata.
- Pass the request to AI Planner.
- Convert the planner result into Mission Queue records.
- Preserve mission ordering and dependencies.
- Enqueue the entire plan atomically.
- Reject duplicate request identifiers.
- Return the request identifier and created mission identifiers.
- Do not wait for mission execution.

Queue Integration

- Use agent.runtime.mission_queue through its existing public API.
- Never mutate the queue persistence file directly.
- All queue changes must remain atomic.
- Mission status responses must use deterministic JSON.
- Cancel, resume, and retry operations must respect the existing Mission Queue state-transition contract.
- Invalid state transitions must return HTTP 409.
- Unknown missions must return HTTP 404.

Planner Integration

- Use agent.ai.ai_planner through its existing public API.
- Support dependency injection for tests.
- Planner failures must not partially enqueue missions.
- Planner validation failures must return a safe HTTP 422 response.
- Never expose internal prompts or provider responses.

Status and Reporting

- Report queue counts by state.
- Report whether the worker appears active based on a heartbeat file.
- Report the latest safe structured worker events.
- Limit returned events using a validated query parameter.
- Never expose secrets or unrestricted log files.
- Reports must be deterministic and JSON serializable.

CLI

- Support execution from repository root:

  python -m agent.api.private_admin_api

- Support:

  python -m agent.api.private_admin_api --host 127.0.0.1 --port 8765

- Support configurable queue path, events path, reports path, host, port, request-size limit, and rate limit.
- Use argparse.
- Invalid CLI arguments must raise SystemExit through argparse.
- Default host must be 127.0.0.1.
- Default port must be 8765.

Shutdown and Reliability

- Support graceful SIGTERM and SIGINT shutdown.
- Use ThreadingHTTPServer safely.
- Close server resources cleanly.
- A failed request must not terminate the API process.
- Concurrent requests must not corrupt Mission Queue.
- Write deterministic structured API events.
- Recover normally after restart.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use temporary directories from the standard library.
- Tests must not perform real network access outside localhost.
- Tests must not run real Git commands.
- Tests must not invoke real AI providers.
- Use fake Planner and fake Mission Queue through dependency injection.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports such as agent.api.private_admin_api.
- Do not modify sys.path in tests.

Testing Requirements

- Test health endpoint.
- Test missing authentication.
- Test invalid authentication.
- Test valid authentication.
- Test constant-time token comparison boundary.
- Test missing startup token.
- Test malformed JSON.
- Test unsupported content type.
- Test oversized request body.
- Test unknown request fields.
- Test successful planning and atomic enqueue.
- Test planner failure without partial enqueue.
- Test duplicate request rejection.
- Test mission listing.
- Test mission details.
- Test unknown mission.
- Test cancel, resume, and retry operations.
- Test invalid state transitions.
- Test deterministic status output.
- Test event limits.
- Test secret redaction.
- Test rate limiting.
- Test localhost default binding.
- Test CLI parsing.
- Test invalid CLI arguments.
- Test graceful shutdown.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/api/private_admin_api.py
- agent/tests/test_private_admin_api.py
