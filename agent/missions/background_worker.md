Mission: Build Autonomous Background Worker

Goal

Create a persistent background worker that continuously consumes missions from Mission Queue and executes them through Autonomous Controller.

Requirements

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Poll Mission Queue continuously with a configurable interval.
- Claim only missions whose dependencies are completed.
- Execute claimed missions through Autonomous Controller.
- Mark successful missions completed.
- Mark retryable failures retrying.
- Mark exhausted failures failed.
- Mark policy or security failures blocked.
- Recover safely after process restart.
- Recover missions left in running state after an unexpected shutdown.
- Support graceful shutdown on SIGTERM and SIGINT.
- Prevent multiple workers from processing the same mission.
- Use deterministic structured JSON logs.
- Never expose secrets in logs.
- Never execute raw shell commands from mission payloads.
- Never bypass Validation, Retry, Git Review, or repository safety checks.
- Support configurable poll interval, worker identifier, and maximum idle cycles.
- Provide a single-run mode for testing and maintenance.
- Fully typed and compatible with Python 3.12.
- Provide a CLI entry point using argparse.

CLI Requirements

- Support:
  python -m runtime.background_worker --queue-path PATH
- Support:
  python -m runtime.background_worker --queue-path PATH --once
- Support:
  python -m runtime.background_worker --queue-path PATH --poll-interval 5
- Invalid arguments must raise SystemExit through argparse.
- Default poll interval must be safe and deterministic.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Every generated Python file must pass py_compile.
- Tests must be compatible with unittest discovery.
- Use temporary directories from the standard library.
- Use fake Mission Queue and fake Autonomous Controller through dependency injection.
- Never run real Git commands, network requests, or external processes in tests.

Testing Requirements

- Test successful mission execution.
- Test retryable failure handling.
- Test exhausted failure handling.
- Test blocked security failure handling.
- Test graceful shutdown.
- Test restart recovery.
- Test prevention of duplicate processing.
- Test single-run mode.
- Test idle polling behavior.
- Test deterministic structured logs.
- Test CLI parsing.
- Test invalid CLI arguments.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/runtime/background_worker.py
- agent/tests/test_background_worker.py

Structured Event Logging Contract

- Every state transition must emit one structured event.
- The worker must expose deterministic structured events for unit tests.
- Events must be stored in memory as dictionaries.
- Each event must contain at least:
  - event
  - mission_id (when applicable)
  - timestamp
- Successful claim emits event="claimed".
- Successful completion emits event="completed".
- Retry scheduling emits event="retrying".
- Permanent failure emits event="failed".
- Recovery after restart emits event="recovered".
- Graceful shutdown emits event="shutdown".
- Every idle polling cycle emits event="idle".
- Tests must inspect these structured events instead of stdout.
- Structured events must remain deterministic.
- Logging must never require the Python logging module during tests.
- All existing and newly generated unittest tests must pass.


Final Worker Loop and Exclusive Claim Contract

- Mission acquisition must occur exclusively through queue.claim().
- Never inspect a pending mission and then claim it in separate operations.
- queue.claim() must be treated as the single atomic ownership boundary.
- The worker must execute and complete the exact mission returned by queue.claim().
- A claimed mission must not remain pending.
- On successful controller execution, the worker must call queue.complete() for the claimed mission identifier.
- When two workers poll the same queue, at most one worker may receive a given mission.
- A second worker must receive no mission while the first worker owns it.
- Duplicate prevention must not cause the successfully claimed mission to be skipped.
- The test_prevent_duplicate_processing unittest must finish with the mission state equal to completed.

- Every empty polling cycle must emit exactly one event="idle".
- An idle event must be emitted before evaluating maximum idle-cycle termination.
- An idle event must also be emitted before graceful shutdown when the current polling cycle found no mission.
- Graceful shutdown must emit event="shutdown" exactly once.
- A shutdown request must not suppress the idle event for an already-started empty polling cycle.
- The test_graceful_shutdown unittest must observe both idle and shutdown events.
- Structured event order must be deterministic.
- All existing and newly generated unittest tests must pass.

Python Package Import Contract

- Generated tests must import project modules using repository-root package paths.
- Use imports from agent.runtime.background_worker, not runtime.background_worker.
- Use imports from agent.runtime.mission_queue, not runtime.mission_queue.
- Use imports from agent.ai.autonomous_controller, not ai.autonomous_controller.
- Tests must run successfully from the repository root with unittest discovery.
- Do not modify sys.path inside tests.
- Do not rely on the current working directory being agent/.
- The generated background worker CLI may support python -m agent.runtime.background_worker from the repository root.
- If compatibility with python -m runtime.background_worker is required from inside agent/, implement explicit import fallbacks in production code, not test-only path hacks.
- All generated imports must match the existing package layout.
- All existing and newly generated unittest tests must pass.
