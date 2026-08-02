Mission: Build Persistent Mission Queue

Goal

Create a persistent and deterministic mission queue that connects AI Planner output to Autonomous Controller execution.

Requirements

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Support pending, running, retrying, completed, failed, blocked, and cancelled states.
- Support mission priorities.
- Preserve mission dependencies.
- Never run a mission before all dependencies are completed.
- Detect circular dependencies.
- Prevent duplicate mission identifiers.
- Persist queue state atomically as JSON.
- Recover safely after process restart.
- Use file locking to prevent concurrent queue corruption.
- Support enqueue, dequeue, claim, complete, fail, retry, block, cancel, resume, and list operations.
- Support configurable maximum retry attempts.
- Preserve deterministic ordering by priority and creation sequence.
- Never execute shell commands.
- Never modify Git state.
- Never expose secrets in reports or stored queue data.
- Provide deterministic dictionary and JSON serialization.
- Integrate cleanly with AI Planner output.
- Provide an interface suitable for Autonomous Controller.
- Fully typed and compatible with Python 3.12.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Every generated Python file must pass py_compile.
- Tests must be compatible with unittest discovery.
- Use temporary directories from the standard library for persistence tests.
- Test enqueue and deterministic ordering.
- Test dependency handling.
- Test circular dependency rejection.
- Test duplicate identifier rejection.
- Test atomic persistence and reload.
- Test restart recovery.
- Test retry limits.
- Test blocked and cancelled missions.
- Test concurrent access protection.
- Test deterministic serialization.
- Test that unrelated files are never modified.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/runtime/mission_queue.py
- agent/tests/test_mission_queue.py
