Mission: Build Runtime Service

Goal

Create a production-oriented runtime lifecycle service that uses the existing Application Composition Root to build, start, inspect, and stop the Mitigate AI application safely.

Scope

- Build runtime lifecycle management only.
- Do not build a web UI.
- Do not add a permanent daemon or systemd unit in this mission.
- Do not start Background Worker or Autonomous Controller loops automatically during construction.
- Do not call external AI providers.
- Do not execute Git or shell commands.
- Do not modify requirements.txt.
- Use Python standard library only.
- Fully typed and compatible with Python 3.12.

Existing Components

Use existing public interfaces for:

- ApplicationConfig
- ApplicationContainer
- build_application
- application_status
- UnifiedRequestFlowService
- ExecutionOutcomeCoordinator
- Background Worker
- Autonomous Controller
- Private Admin API

Do not reimplement the Application Composition Root.

Runtime States

Support:

- created
- starting
- running
- stopping
- stopped
- failed

State Rules

- Initial state must be created.
- start() may transition created or stopped to starting, then running.
- stop() may transition running or failed to stopping, then stopped.
- Repeated start() while running must be idempotent.
- Repeated stop() while stopped must be idempotent.
- Invalid transitions must return deterministic safe failures.
- Runtime state changes must be atomic and thread-safe.
- Never acquire the same non-reentrant lock twice from the same call chain.

Runtime Construction

The runtime service must:

- accept ApplicationConfig
- accept optional dependency overrides
- build the ApplicationContainer only when start() is called
- not construct services in __init__()
- not start worker or controller loops automatically
- support dependency injection for application builder, clock, and event sink
- preserve the supplied configuration without mutation

Startup Flow

1. Validate current runtime state.
2. Set state to starting.
3. Build ApplicationContainer through build_application().
4. Validate application_status().
5. Require ready=true before entering running state.
6. Store the constructed container.
7. Emit safe startup events.
8. Return deterministic runtime status.

Startup Failure

- Convert construction exceptions into runtime_start_failed.
- Close any partially constructed container.
- Clear unusable container references.
- Set runtime state to failed.
- Never expose raw exceptions, credentials, environment values, or unrestricted paths.
- Startup failure must not leave worker threads or processes running.

Shutdown Flow

1. Validate current runtime state.
2. Set state to stopping.
3. Stop explicitly started runtime components in reverse order.
4. Call container.close().
5. Clear the active container reference.
6. Set state to stopped.
7. Emit safe shutdown events.
8. Return deterministic runtime status.

Component Activation

Provide explicit opt-in methods:

- start_background_worker()
- stop_background_worker()
- start_autonomous_controller()
- stop_autonomous_controller()
- start_private_admin_api()
- stop_private_admin_api()

Rules:

- Runtime must be running before component activation.
- Components must never start during RuntimeService construction.
- Components must never start automatically during start() unless explicitly configured.
- Repeated component start and stop operations must be idempotent.
- Use only documented public lifecycle methods.
- Track which components were started by this RuntimeService.
- stop() must stop only components started by this RuntimeService.
- Shutdown order must be Private Admin API, Autonomous Controller, Background Worker, then ApplicationContainer.
- Component failure must return a safe deterministic failure.
- Do not expose raw dependency exceptions.

Request Processing

Provide:

- submit_request(request)
- process_execution_outcome(outcome)

Rules:

- Runtime must be running.
- submit_request() must call container.request_flow.submit().
- process_execution_outcome() must call container.execution_outcome_coordinator.process().
- Preserve documented downstream blocked_reason and failure_code values.
- Convert unexpected exceptions into dependency_failed.
- Never mutate submitted request or outcome.
- Never log full user messages, uploaded contents, summaries, metadata, or provider responses.

Health and Status

Provide runtime_status() returning:

- state
- environment_name
- default_project_id
- application_ready
- container_present
- background_worker_running
- autonomous_controller_running
- private_admin_api_running
- started_at
- stopped_at
- last_failure_code
- warnings

Health checks must:

- be deterministic
- avoid network access
- avoid provider calls
- avoid starting components
- never expose secrets or unrestricted paths

Public Interface

Provide:

- RuntimeConfig
- RuntimeService
- build_runtime(config, overrides=None)
- runtime_status(runtime)

RuntimeConfig must support:

- application_config
- auto_start_background_worker
- auto_start_autonomous_controller
- auto_start_private_admin_api

Defaults:

- all auto-start flags must be false

RuntimeService must provide:

- start()
- stop()
- close()
- runtime_status()
- submit_request(request)
- process_execution_outcome(outcome)
- start_background_worker()
- stop_background_worker()
- start_autonomous_controller()
- stop_autonomous_controller()
- start_private_admin_api()
- stop_private_admin_api()
- latest_events(limit)

Lifecycle

- close() must be equivalent to safe stop().
- close() must be idempotent.
- Support use as a context manager.
- __enter__() must start the runtime and return self.
- __exit__() must stop the runtime.
- Do not raise raw exceptions from cleanup.
- Register no global signal handlers in this mission.
- Register no atexit hooks in this mission.

Concurrency

- Public lifecycle methods must be thread-safe.
- Concurrent start calls must build only one container.
- Concurrent stop calls must close the container once.
- Request submission must not occur while starting, stopping, stopped, or failed.
- Lock scope must be bounded.
- Never hold the runtime lock while calling external dependency lifecycle methods when re-entry is possible.
- Tests must use bounded joins and must never hang.

Security and Privacy

Never expose or persist:

- API keys
- credentials
- authorization headers
- environment-variable values
- full user messages
- uploaded contents
- provider responses
- raw tracebacks
- unrestricted filesystem paths

Events

Emit safe deterministic events for:

- runtime_created
- runtime_starting
- runtime_started
- runtime_start_failed
- runtime_stopping
- runtime_stopped
- component_starting
- component_started
- component_start_failed
- component_stopping
- component_stopped
- request_submitted
- request_rejected
- execution_outcome_processed
- runtime_operation_failed

Events may contain only safe state names, component names, project identifiers, counts, timestamps, and failure codes.

Failure Codes

- invalid_runtime_config
- invalid_runtime_transition
- runtime_not_running
- runtime_start_failed
- runtime_stop_failed
- component_start_failed
- component_stop_failed
- application_not_ready
- dependency_failed

Testing Policy

- Use Python standard library unittest only.
- Never use pytest.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use unittest.mock and TemporaryDirectory.
- Use fake application builder, container, services, components, clock, and event sink.
- Do not use network access.
- Do not call real providers.
- Do not execute Git or shell commands.
- Do not start real worker, controller, or API threads.
- Every generated Python file must pass py_compile.
- Tests must run from repository root using unittest discovery.
- Use repository-root imports.
- Do not modify sys.path.
- Do not use dynamic code execution, dynamic imports, subprocess, or shell execution.
- Generated files must not contain the forbidden function-call pattern checked by Mission Runner.

Testing Requirements

- Test initial created state.
- Test successful start.
- Test application built only during start.
- Test start idempotency.
- Test startup construction failure.
- Test application-not-ready failure.
- Test partial startup cleanup.
- Test successful stop.
- Test stop idempotency.
- Test close idempotency.
- Test context-manager lifecycle.
- Test no automatic component startup by default.
- Test each explicit component start.
- Test each explicit component stop.
- Test component start idempotency.
- Test component stop idempotency.
- Test component failure handling.
- Test reverse shutdown order.
- Test only runtime-started components are stopped.
- Test request submission while running.
- Test request rejection when not running.
- Test execution outcome processing while running.
- Test execution outcome rejection when not running.
- Test downstream failure-code propagation.
- Test request and outcome inputs are not mutated.
- Test deterministic runtime status.
- Test status redaction.
- Test event redaction.
- Test concurrent start builds one container.
- Test concurrent stop closes once.
- Test lifecycle methods never hang.
- Test supplied config and overrides are not mutated.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/runtime/runtime_service.py
- agent/tests/test_runtime_service.py
