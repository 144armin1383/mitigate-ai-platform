Mission: Build Runtime Private API Core

Goal

Create the production-only private HTTP API entrypoint for the existing RuntimeService.

Scope

- Generate production code only.
- Do not generate tests in this mission.
- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Fully typed and compatible with Python 3.12.
- Do not build a dashboard.
- Do not add Nginx or systemd configuration.
- Do not call external providers directly.
- Do not execute Git or shell commands.
- Bind to localhost by default.

Existing Components

Use existing public interfaces for:

- ApplicationConfig
- RuntimeConfig
- RuntimeService
- build_runtime
- runtime_status

Do not reimplement runtime orchestration.

Architecture

Provide:

- RuntimeAPIConfig
- RuntimePrivateAPI
- build_runtime_private_api(config, runtime=None)
- main()

Default settings:

- host = 127.0.0.1
- port = 8765
- request_body_limit_bytes = 1048576
- response_body_limit_bytes = 1048576
- request_timeout_seconds = 30
- graceful_shutdown_timeout_seconds = 15
- enable_lifecycle_endpoints = false

Authentication

- Use bearer-token authentication.
- Resolve the token through an injected token resolver.
- Do not store secrets in source code or committed files.
- Compare tokens with hmac.compare_digest().
- Missing authentication returns HTTP 401.
- Invalid authentication returns HTTP 403.
- GET /health/live may be unauthenticated.
- All other endpoints require authentication.
- Never log or return the bearer token.

Configuration Validation

- Reject unknown fields.
- Validate host and port.
- Accept port 0 for ephemeral test binding.
- Reject public wildcard hosts 0.0.0.0 and ::.
- Validate request and response body limits.
- Validate timeout values.
- auth_token_reference must be non-empty.
- Never resolve credentials through dynamic code execution.

Endpoints

GET /health/live

- Return HTTP 200 while the API process is alive.
- No authentication required.

GET /health/ready

- Authentication required.
- Return HTTP 200 when runtime state is running and application_ready is true.
- Return HTTP 503 otherwise.

GET /v1/runtime/status

- Authentication required.
- Return safe RuntimeService status.

POST /v1/requests

- Authentication required.
- Accept one JSON object.
- Call RuntimeService.submit_request().
- Return HTTP 202 when accepted.
- Map documented failures safely.

POST /v1/execution-outcomes

- Authentication required.
- Accept one JSON object.
- Call RuntimeService.process_execution_outcome().
- Return HTTP 200 when processed successfully.

POST /v1/runtime/start
POST /v1/runtime/stop

- Authentication required.
- Available only when enable_lifecycle_endpoints is true.
- Use RuntimeService public lifecycle methods only.

POST /v1/components/background-worker/start
POST /v1/components/background-worker/stop
POST /v1/components/autonomous-controller/start
POST /v1/components/autonomous-controller/stop

- Authentication required.
- Available only when enable_lifecycle_endpoints is true.
- Use RuntimeService public lifecycle methods only.

Request Handling

- Accept application/json only for POST endpoints.
- Reject malformed JSON with HTTP 400.
- Reject non-object JSON when an object is required.
- Reject unsupported content types with HTTP 415.
- Reject oversized bodies with HTTP 413.
- Use deterministic UTF-8 JSON responses.
- Set Content-Type: application/json; charset=utf-8.
- Set Cache-Control: no-store.
- Set X-Content-Type-Options: nosniff.
- Never reflect raw request content in errors.
- Never expose raw exceptions.

Response Format

Return:

- ok
- status
- timestamp
- request_id when safely available
- data
- error

Error objects may contain:

- code
- message

Never expose:

- credentials
- authorization headers
- bearer tokens
- environment-variable values
- full user messages
- uploaded contents
- provider responses
- raw exceptions
- tracebacks
- unrestricted filesystem paths

Failure Mapping

- invalid_request -> 400
- invalid_execution_outcome -> 400
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

Unknown failures map to HTTP 500 with a generic safe error.

Ephemeral Port

- Port 0 must be accepted.
- Construct and bind the HTTP server before start() returns.
- Read the actual bound host and port from server.server_address.
- address() must return the actual bound port greater than zero after successful start.
- Do not guess or preselect the ephemeral port.
- Store the actual bound address before start() returns.

Server Readiness

- start() must not return until the server is bound and ready.
- Use bounded deterministic synchronization.
- Do not use arbitrary sleep as the primary readiness mechanism.
- If readiness fails, close the server and return api_start_failed.
- Repeated start() calls must be idempotent.
- Repeated stop() and close() calls must be idempotent.

Lifecycle

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
- Support context-manager use.
- __enter__() must start the API and return self only after readiness.
- __exit__() must stop and close safely.
- Do not hold internal locks while calling shutdown().
- Avoid same-thread shutdown and self-join deadlocks.
- Clear server and thread references after close.
- Do not register global signal handlers in the reusable class.
- main() may register SIGINT and SIGTERM handlers.

Main Entrypoint

main() must:

1. Read safe configuration from command-line arguments.
2. Resolve the authentication token from an external environment reference.
3. Build ApplicationConfig.
4. Build RuntimeConfig.
5. Build and start RuntimeService.
6. Build and start RuntimePrivateAPI.
7. Serve until SIGINT or SIGTERM.
8. Stop the API.
9. Stop RuntimeService.
10. Return deterministic exit codes.

Command-line options may include:

- --host
- --port
- --data-root
- --repository-root
- --default-project-id
- --environment-name
- --auth-token-env
- --enable-lifecycle-endpoints

Security

- Default host must be 127.0.0.1.
- Reject 0.0.0.0 and ::.
- Do not enable debug mode.
- Do not return stack traces.
- Do not log request bodies.
- Do not log Authorization headers.
- Do not add wildcard CORS headers.
- Do not trust X-Forwarded-For.
- Do not expose full RuntimeConfig or ApplicationConfig.

Events

Emit safe events for:

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

Generated File Safety

- Do not use dynamic code execution.
- Do not use dynamic imports.
- Do not use subprocess, os.system, or shell execution.
- Generated production code must not contain the forbidden function-call pattern checked by Mission Runner.
- The generated file must pass py_compile.
- All existing unittest tests must pass.

Deliverables

- agent/api/runtime_private_api.py

Authentication Construction Contract

- build_runtime_private_api() must not eagerly resolve the authentication token.
- Construction must succeed even when auth_token_reference is empty.
- GET /health/live must work without authentication configuration.
- auth_token_reference becomes mandatory only when a protected endpoint is accessed or authentication is actually required.
- The token resolver must be invoked lazily.
- A resolver returning a valid token must not cause construction failure.
- Missing or unresolved authentication configuration must produce HTTP authentication responses during request handling rather than constructor exceptions whenever possible.
- Constructor validation must not reject configurations used by the unauthenticated health-live endpoint tests.


Authentication Construction Contract

- build_runtime_private_api() must not eagerly resolve the authentication token.
- Construction must succeed even when auth_token_reference is empty.
- GET /health/live must work without authentication configuration.
- auth_token_reference becomes mandatory only when a protected endpoint is accessed or authentication is actually required.
- The token resolver must be invoked lazily.
- A resolver returning a valid token must not cause construction failure.
- Missing or unresolved authentication configuration must produce HTTP authentication responses during request handling rather than constructor exceptions whenever possible.
- Constructor validation must not reject configurations used by the unauthenticated health-live endpoint tests.


Complete HTTP Response Contract

- Every request path must produce exactly one complete HTTP response.
- Every response path must call send_response() exactly once.
- Every response path must send all required headers.
- Every response path must call end_headers() before writing the body.
- Every response with a body must include an exact Content-Length header calculated from the UTF-8 encoded response bytes.
- Write the complete response body to wfile before returning.
- Flush wfile after writing the response body.
- Set close_connection to true after writing the response unless a correct persistent-connection implementation is explicitly maintained.
- Never leave a client waiting for connection close to determine body length.
- Never omit both Content-Length and connection close.

Response Helper

- Implement one shared response-writing helper used by successful and error responses.
- The helper must serialize deterministic JSON to UTF-8 bytes before sending headers.
- The helper must set:
  - Content-Type: application/json; charset=utf-8
  - Content-Length: exact encoded byte length
  - Cache-Control: no-store
  - X-Content-Type-Options: nosniff
  - Connection: close
- The helper must call send_response(), send_header(), end_headers(), wfile.write(), and wfile.flush() in the correct order.
- Do not call send_error(), because its default HTML response format is not allowed.
- Do not write more than one response for a request.

Immediate Error Responses

- Missing authentication must return HTTP 401 immediately.
- Invalid authentication must return HTTP 403 immediately.
- Unsupported Content-Type must return HTTP 415 immediately.
- Malformed JSON must return HTTP 400 immediately.
- Non-object JSON must return HTTP 400 immediately.
- Oversized request bodies must return HTTP 413 immediately.
- Unknown routes must return HTTP 404 immediately.
- Unexpected exceptions must return safe HTTP 500 immediately.
- Every immediate error path must use the shared complete-response helper.

Health Response Rules

- GET /health/live must return immediately without waiting for RuntimeService state changes.
- GET /health/ready must read a current safe runtime status and return immediately.
- GET /v1/runtime/status must not block on runtime lifecycle transitions.
- Health and status handlers must never wait on server shutdown or request-thread completion.

Request Body Handling

- Read no more than request_body_limit_bytes plus one byte.
- Validate Content-Length before reading when present.
- Do not perform an unbounded read from rfile.
- Do not wait for EOF to finish reading a request body.
- For requests with Content-Length, read exactly that bounded number of bytes.
- For POST requests requiring a body, reject missing or invalid Content-Length deterministically.

Threading and Locking

- Do not hold the API lifecycle lock while processing HTTP requests.
- Do not hold an internal lock while calling RuntimeService public methods.
- Request handlers must not wait on the server thread itself.
- Avoid nested acquisition of non-reentrant locks.
- All request handlers must terminate within bounded test timeouts.
- All Runtime Private API tests must complete without TimeoutError or deadlock.
- All existing and newly generated unittest tests must pass.
