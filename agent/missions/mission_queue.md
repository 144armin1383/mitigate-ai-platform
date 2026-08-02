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

Circular Dependency Acceptance Criteria

- The queue must validate the entire dependency graph whenever a mission is added, updated, resumed, or loaded from persistence.
- Circular dependencies must be rejected immediately with ValueError.
- Detect direct self-dependencies.
- Detect two-node cycles such as A depends on B and B depends on A.
- Detect longer cycles such as A -> B -> C -> A.
- Cycle detection must use deterministic graph traversal.
- Dependency validation must not depend on mission execution state.
- Persisted queue data containing a cycle must be rejected during load.
- The test_circular_dependency_rejection unittest must pass.
- All existing and newly generated unittest tests must pass.

State Transition and Dependency Contract

- Mission state transitions must be explicit and deterministic.
- claim() may select only pending or retrying missions whose dependencies are all completed.
- claim() must change the selected mission state to running atomically.
- complete() may be called only for a running mission.
- fail() may be called only for a running mission.
- Tests for complete() and fail() must call claim() first and must not bypass the running state.
- A failed mission with retry attempts remaining must become retrying.
- A failed mission with no retry attempts remaining must become failed.
- A retrying mission may be claimed again only when all dependencies remain completed.
- blocked and cancelled missions must never be claimable.
- Cancelling a completed, failed, or already cancelled mission must raise ValueError.
- Resuming is allowed only for blocked or cancelled missions.
- Resuming any other mission state must raise ValueError.
- Completing, failing, blocking, cancelling, or resuming an unknown mission identifier must raise KeyError.
- A mission with an unresolved dependency must not be claimable.
- A mission may be claimed only after every dependency has status completed.
- Dependency checks must use mission identifiers, not queue position or creation order.
- A failed, blocked, cancelled, running, retrying, or pending dependency does not satisfy dependency completion.
- Dependency graph validation must be atomic.
- If enqueue or update introduces a circular dependency, reject the operation with ValueError and leave the queue unchanged.
- Detect self-cycles, two-node cycles, and longer cycles.
- Circular dependency validation must also run when loading persisted state.
- Test cases must use isolated temporary queue files and must not share state across tests.
- Every test must create a fresh MissionQueue instance and fresh temporary persistence path.
- State from one unittest must never leak into another unittest.
- All existing and newly generated unittest tests must pass.

Python Enum and Deserialization Acceptance Criteria

- Never use TypeScript-style casting syntax such as "as MissionState".
- Python source must use valid Python 3.12 syntax only.
- Deserialize enum values by calling the enum class explicitly.
- Mission state deserialization must use MissionState(str(value)).
- Invalid persisted mission states must raise ValueError.
- All generated Python files must pass py_compile before unittest execution.
- The generated mission_queue.py must not contain the token sequence " as MissionState".
- All existing and newly generated unittest tests must pass.
