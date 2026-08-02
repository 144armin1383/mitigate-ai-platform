Mission: Build Runtime Private API Tests

Goal

Create a comprehensive unittest suite for the existing RuntimePrivateAPI production module.

Scope

- Generate test code only.
- Do not modify agent/api/runtime_private_api.py.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use Python standard library unittest only.
- Fully compatible with Python 3.12.
- Tests must run from repository root using unittest discovery.

Module Under Test

- agent.api.runtime_private_api.RuntimeAPIConfig
- agent.api.runtime_private_api.RuntimePrivateAPI
- agent.api.runtime_private_api.build_runtime_private_api

Testing Environment

- Use unittest and unittest.mock.
- Use TemporaryDirectory.
- Use a deterministic fake RuntimeService.
- Use a deterministic fake token resolver.
- Use a deterministic fake clock and event sink.
- Bind only to 127.0.0.1.
- Use port 0 for ephemeral test ports.
- Do not use external network access.
- Do not call real providers.
- Do not execute Git or shell commands.
- Do not start real worker or controller loops.
- Do not modify sys.path.
- Use repository-root imports.

Server Safety

- Every test server must start on localhost with an ephemeral port.
- After start(), address() must return the actual bound port greater than zero.
- Create and bind the server before start() returns.
- Tests must use bounded timeouts.
- Tests must never hang.
- Every test must stop and close the server.
- Every server thread must terminate.
- Every socket must be released.
- Do not reuse a closed server instance.

Authentication Tests

- Test unauthenticated GET /health/live succeeds.
- Test missing bearer token returns HTTP 401.
- Test malformed authorization header returns HTTP 401.
- Test invalid bearer token returns HTTP 403.
- Test valid bearer token succeeds.
- Test token comparison behavior without exposing the token.
- Test Authorization header never appears in events or responses.

Configuration Tests

- Test default host is 127.0.0.1.
- Test default port is 8765.
- Test port 0 is accepted.
- Test public wildcard host 0.0.0.0 rejection.
- Test public wildcard host :: rejection.
- Test invalid port rejection.
- Test invalid request-body limit rejection.
- Test invalid response-body limit rejection.
- Test invalid timeout rejection.
- Test empty auth_token_reference rejection.
- Test unknown configuration field rejection.
- Test configuration is not mutated.

Lifecycle Tests

- Test construction does not start server.
- Test successful start.
- Test start idempotency.
- Test actual ephemeral port reporting.
- Test successful stop.
- Test stop idempotency.
- Test close idempotency.
- Test context-manager lifecycle.
- Test immediate request after __enter__().
- Test graceful shutdown.
- Test shutdown does not deadlock.
- Test no leaked thread.
- Test no leaked socket.

Health and Status Endpoints

- Test GET /health/live.
- Test GET /health/ready while runtime running and ready.
- Test GET /health/ready while runtime stopped.
- Test GET /v1/runtime/status.
- Test safe status redaction.
- Test Cache-Control no-store.
- Test X-Content-Type-Options nosniff.
- Test Content-Type application/json with UTF-8.

Request Submission Endpoint

- Test valid POST /v1/requests returns HTTP 202.
- Test invalid request returns HTTP 400.
- Test runtime_not_running returns HTTP 409.
- Test budget_blocked returns HTTP 429.
- Test rate_limit_blocked returns HTTP 429.
- Test unknown_project returns HTTP 404.
- Test cross_project_reference returns HTTP 403.
- Test no_model_available returns HTTP 503.
- Test planner_failed returns HTTP 503.
- Test dependency_failed returns HTTP 503.
- Test request object is passed without mutation.
- Test full user message is absent from events and errors.

Execution Outcome Endpoint

- Test valid POST /v1/execution-outcomes returns HTTP 200.
- Test invalid_execution_outcome returns HTTP 400.
- Test mission_not_found returns HTTP 404.
- Test duplicate_execution returns HTTP 409.
- Test invalid_status_transition returns HTTP 409.
- Test usage_recording_failed returns HTTP 503.
- Test report_persistence_failed returns HTTP 503.
- Test outcome object is passed without mutation.

Request Parsing

- Test application/json accepted.
- Test unsupported content type returns HTTP 415.
- Test malformed JSON returns HTTP 400.
- Test non-object JSON returns HTTP 400.
- Test empty body returns HTTP 400.
- Test oversized body returns HTTP 413.
- Test response JSON is deterministic.
- Test UTF-8 encoding.
- Test raw request content is not reflected in errors.

Lifecycle Endpoints

- Test lifecycle endpoints disabled by default.
- Test POST /v1/runtime/start when enabled.
- Test POST /v1/runtime/stop when enabled.
- Test background-worker start and stop endpoints.
- Test autonomous-controller start and stop endpoints.
- Test documented RuntimeService methods are called.
- Test component internals are never accessed directly.

Failure Mapping

Test exact HTTP mapping for:

- invalid_request
- invalid_execution_outcome
- runtime_not_running
- invalid_runtime_transition
- duplicate_execution
- invalid_status_transition
- mission_not_found
- budget_blocked
- rate_limit_blocked
- unknown_project
- cross_project_reference
- no_model_available
- planner_failed
- queue_resolution_failed
- queue_failed
- usage_recording_failed
- report_persistence_failed
- dependency_failed
- unknown failure mapped to safe HTTP 500

Security and Redaction

- Test no credentials in responses.
- Test no bearer token in responses.
- Test no authorization headers in events.
- Test no environment-variable values in responses.
- Test no unrestricted filesystem paths.
- Test no raw exceptions.
- Test no traceback content.
- Test no full RuntimeConfig or ApplicationConfig exposure.
- Test event redaction.
- Test status redaction.

Repository Safety

- Do not create persistent files in repository root.
- Clean up all temporary resources.
- Do not modify unrelated files.
- Tests must leave the working tree clean when started from a clean checkout.

Generated Test Safety

- Do not import ast.
- Do not use dynamic code execution.
- Do not use dynamic imports.
- Do not use subprocess, os.system, or shell execution.
- Generated test code must not contain the forbidden function-call pattern checked by Mission Runner.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/tests/test_runtime_private_api.py
