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
