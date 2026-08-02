Mission: Build Runtime Private API Entrypoint

Goal

Create a production-oriented private HTTP API entrypoint for the existing RuntimeService.

The API must expose a minimal authenticated localhost interface for runtime lifecycle, request submission, execution outcome reporting, health checks, and safe status inspection.

Scope

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Fully typed and compatible with Python 3.12.
- Do not build a dashboard.
- Do not add Nginx or systemd configuration in this mission.
- Do not expose the API publicly.
- Bind to localhost by default.
- Do not call external providers directly.
- Do not execute Git or shell commands.
- Do not start real worker or controller loops unless explicitly requested through the runtime public lifecycle interface.

Existing Components

Use existing public interfaces for:

- ApplicationConfig
- RuntimeConfig
- RuntimeService
- build_runtime
- runtime_status
- UnifiedRequestFlowService
- ExecutionOutcomeCoordinator

Do not reimplement runtime orchestration.

Architecture

Create a private HTTP API using Python standard library HTTP facilities.

Provide:

- RuntimeAPIConfig
- RuntimePrivateAPI
- build_runtime_private_api(config, runtime=None)
- main()

Default network settings:

- host: 127.0.0.1
- port: 8765

The server must not bind to 0.0.0.0 by default.

Authentication

Use a bearer token supplied at runtime through an external credential source.

Requirements:

- Do not store the bearer token in source code.
- Do not store the bearer token in committed JSON files.
- Do not log the bearer token.
- Do not include the bearer token in status or events.
- Compare tokens using hmac.compare_digest().
- Reject missing authentication with HTTP 401.
- Reject invalid authentication with HTTP 403.
- Health liveness may be unauthenticated.
- Readiness, status, request, execution, and lifecycle endpoints must require authentication.

RuntimeAPIConfig

Support:

- host
- port
- auth_token_reference
- request_body_limit_bytes
- response_body_limit_bytes
- request_timeout_seconds
- graceful_shutdown_timeout_seconds
- enable_lifecycle_endpoints
- environment_name

Defaults:

- host = 127.0.0.1
- port = 8765
- request_body_limit_bytes = 1048576
- response_body_limit_bytes = 1048576
- request_timeout_seconds = 30
- graceful_shutdown_timeout_seconds = 15
- enable_lifecycle_endpoints = false

Validation

- Reject unknown configuration fields.
- Validate host and port.
- Reject public wildcard host values unless explicitly permitted by a future deployment layer.
- Reject invalid body limits.
- Reject invalid timeout values.
- auth_token_reference must be non-empty.
- Never resolve credentials through arbitrary code execution.
- Support injected token resolver for tests and production composition.

Endpoints

GET /health/live

- No authentication required.
- Return HTTP 200 while the API process is alive.
- Return:
  - status
  - service
  - timestamp

GET /health/ready

- Authentication required.
- Return HTTP 200 when RuntimeService is running and application_ready=true.
- Return HTTP 503 otherwise.
- Return safe readiness metadata only.

GET /v1/runtime/status

- Authentication required.
- Return RuntimeService.runtime_status().
- Never expose secrets, unrestricted filesystem paths, raw exceptions, or full project configuration.

POST /v1/requests

- Authentication required.
- Accept one JSON request object.
- Call RuntimeService.submit_request().
- Preserve safe downstream blocked_reason and failure_code.
- Return HTTP 202 for accepted requests.
- Return HTTP 400 for invalid input.
- Return HTTP 409 for documented runtime state conflicts.
- Return HTTP 429 for budget or rate-limit blocking.
- Return HTTP 503 for dependency failures.

POST /v1/execution-outcomes

- Authentication required.
- Accept one JSON execution outcome.
- Call RuntimeService.process_execution_outcome().
- Return HTTP 200 for successfully processed outcomes.
- Return HTTP 400 for invalid outcomes.
- Return HTTP 404 for mission_not_found.
- Return HTTP 409 for duplicate execution or invalid status transition.
- Return HTTP 503 for dependency failures.

POST /v1/runtime/start

- Authentication required.
- Available only when enable_lifecycle_endpoints=true.
- Call RuntimeService.start().
- Return deterministic safe status.

POST /v1/runtime/stop

- Authentication required.
- Available only when enable_lifecycle_endpoints=true.
- Call RuntimeService.stop().
- The HTTP response must be completed safely before server shutdown is initiated.
- Do not deadlock the request-handling thread.

POST /v1/components/background-worker/start
POST /v1/components/background-worker/stop
POST /v1/components/autonomous-controller/start
POST /v1/components/autonomous-controller/stop

- Authentication required.
- Available only when enable_lifecycle_endpoints=true.
- Use RuntimeService public lifecycle methods only.
- Do not access component internals directly.

Request Handling

- Accept application/json only for POST endpoints.
- Reject unsupported content types with HTTP 415.
- Reject malformed JSON with HTTP 400.
- Reject oversized requests with HTTP 413.
- Reject JSON values that are not dictionaries where object input is required.
- Use deterministic JSON responses.
- Use UTF-8.
- Set Content-Type: application/json; charset=utf-8.
- Set Cache-Control: no-store.
- Set X-Content-Type-Options: nosniff.
- Do not reflect raw request content in errors.
- Do not expose raw exceptions.

Response Format

All responses must contain:

- ok
- status
- timestamp
- request_id when safely available
- data
- error

Error objects may contain:

- code
- message

Never include:

- raw exception text
- tracebacks
- credentials
- authorization headers
- bearer tokens
- environment-variable values
- unrestricted filesystem paths
- full user messages
- uploaded content
- provider responses

HTTP Error Mapping

Map documented failure codes consistently:

- invalid_request -> 400
- invalid_execution_outcome -> 400
- invalid_runtime_config -> 400
- runtime_not_running -> 409
- invalid_runtime_transition -> 409
- duplicate_execution -> 409
- invalid_status_transition -> 409
- mission_not_found -> 404
- budget_blocked -> 429
- rate_limit_blocked -> 429
- unknown_project -> 404
- cross_project_reference -> 403
- no_model_available -> 503
- planner_failed -> 503
- queue_resolution_failed -> 503
- queue_failed -> 503
- usage_recording_failed -> 503
- report_persistence_failed -> 503
- dependency_failed -> 503

Unknown failures must map to HTTP 500 with a generic safe error.

Server Lifecycle

RuntimePrivateAPI must provide:

- start()
- serve_forever()
- stop()
- close()
- status()
- address()
- latest_events(limit)

Rules:

- Construction must not start the server.
- start() must start at most one server.
- stop() must be idempotent.
- close() must be idempotent.
- Support context-manager use.
- Do not register global signal handlers in the reusable class.
- main() may register SIGINT and SIGTERM handlers.
- Shutdown must be graceful.
- Do not hold internal locks while calling server shutdown methods.
- Avoid self-join and same-thread shutdown deadlocks.
- Tests must use bounded timeouts and never hang.

Main Entrypoint

Provide a main() function that:

1. Reads non-secret configuration from command-line arguments or safe environment references.
2. Resolves the authentication token through an injected or external runtime source.
3. Builds ApplicationConfig.
4. Builds RuntimeConfig.
5. Builds RuntimeService.
6. Starts RuntimeService.
7. Builds RuntimePrivateAPI.
8. Serves until SIGINT or SIGTERM.
9. Stops the API.
10. Stops RuntimeService.
11. Exits with deterministic status codes.

Command-line options may include:

- --host
- --port
- --data-root
- --repository-root
- --default-project-id
- --environment-name
- --auth-token-env
- --enable-lifecycle-endpoints

Security Rules

- Default host must remain 127.0.0.1.
- Reject 0.0.0.0 and :: unless an explicit unsafe-public-bind override is added in a later deployment mission.
- Do not permit CORS wildcard headers.
- Do not trust X-Forwarded-For in this mission.
- Do not expose debug mode.
- Do not expose stack traces.
- Do not log request bodies.
- Do not log Authorization headers.
- Do not return full RuntimeConfig or ApplicationConfig.

Events

Emit safe deterministic events for:

- api_created
- api_starting
- api_started
- api_start_failed
- request_received
- authentication_failed
- request_rejected
- request_completed
- api_stopping
- api_stopped
- api_operation_failed

Events may contain only:

- endpoint
- method
- HTTP status
- safe request identifier
- runtime state
- timestamp
- failure code

Public Interface

Provide:

- RuntimeAPIConfig
- RuntimePrivateAPI
- build_runtime_private_api
- main

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock.
- Use TemporaryDirectory.
- Use fake RuntimeService, token resolver, clock, and event sink.
- Use localhost and an ephemeral port only.
- Do not use external network access.
- Do not call real providers.
- Do not execute Git or shell commands.
- Do not start real worker or controller loops.
- Every generated Python file must pass py_compile.
- Tests must run from repository root using unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use dynamic code execution, dynamic imports, subprocess, os.system, or shell execution.
- Generated files must not contain the forbidden function-call pattern checked by Mission Runner.
- Tests must use bounded timeouts.
- Tests must never hang.
- Tests must clean up all server threads and sockets.

Testing Requirements

- Test default localhost binding.
- Test public wildcard binding rejection.
- Test ephemeral port binding.
- Test API construction does not start server.
- Test successful server start.
- Test start idempotency.
- Test stop idempotency.
- Test close idempotency.
- Test context-manager lifecycle.
- Test unauthenticated liveness.
- Test missing bearer token.
- Test invalid bearer token.
- Test valid bearer token.
- Test readiness while runtime running.
- Test readiness while runtime stopped.
- Test runtime status endpoint.
- Test valid request submission.
- Test blocked request mapping.
- Test budget block mapping.
- Test rate-limit mapping.
- Test invalid JSON.
- Test non-object JSON rejection.
- Test unsupported content type.
- Test oversized body rejection.
- Test valid execution outcome.
- Test invalid execution outcome.
- Test mission-not-found mapping.
- Test duplicate execution mapping.
- Test dependency failure mapping.
- Test lifecycle endpoints disabled.
- Test runtime start endpoint enabled.
- Test runtime stop endpoint enabled.
- Test component lifecycle endpoints.
- Test deterministic JSON serialization.
- Test security headers.
- Test no-cache header.
- Test response redaction.
- Test event redaction.
- Test Authorization header never appears in logs or events.
- Test graceful shutdown.
- Test shutdown does not deadlock.
- Test no leaked server thread.
- Test no leaked socket.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/api/runtime_private_api.py
- agent/tests/test_runtime_private_api.py

Ephemeral Port and Server Readiness Contract

- Port value 0 must be supported for tests and controlled runtime use.
- Port 0 means the operating system selects an available ephemeral port.
- RuntimeAPIConfig validation must accept port 0.
- After the HTTP server is constructed and bound, read the actual bound address from the server socket.
- address() must return the actual bound host and actual bound port.
- address() must never continue returning configured port 0 after successful binding.
- The actual bound port must be an integer greater than zero.
- Do not guess or preselect an ephemeral port before binding.

Start Readiness

- start() must not return success until the HTTP server has been constructed, bound, and is ready to accept connections.
- Create and bind the server before starting the serving thread.
- Store the actual bound address before start() returns.
- Use a bounded readiness event or equivalent deterministic synchronization.
- Do not use arbitrary sleep calls as the primary readiness mechanism.
- If readiness is not reached within a bounded timeout, stop and close the server and return api_start_failed.
- start() must remain idempotent.
- Repeated start() calls must return the same actual bound address while the server is running.

Context Manager

- __enter__() must call start() and return only after the server is ready.
- A request made immediately after entering the context manager must succeed.
- __exit__() must stop and close the server safely.

Test Isolation

- Each test server instance must bind independently.
- Tests must not reuse a closed server socket.
- Tests must not retain stale configured port 0 after a prior server instance.
- stop() and close() must clear active server and thread references safely.
- Every test must clean up its server thread and socket.
- The context-manager lifecycle, lifecycle-endpoint, and oversized-body tests must receive an actual bound port greater than zero.
- All existing and newly generated unittest tests must pass.
