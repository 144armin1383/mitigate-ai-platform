Mission: Self-Healing Repair Loop Phase 1 v2

Goal

Build an isolated, deterministic, dependency-free self-healing repair subsystem for failed development missions.

Do not modify protected Core.

Do NOT modify:

- agent/ai/
- agent/core/
- agent/runtime/
- agent/api/
- agent/orchestrator/
- agent/autonomy/
- agent/memory/
- agent/bootstrap/
- agent/policies/
- agent/services/
- agent/providers/
- agent/deploy/
- agent/tests/test_portable_agent_recovery.py
- agent/tests/test_core_protection.py

# Deliverables

- agent/repair/__init__.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py
- agent/tests/test_self_healing_repair_loop.py

# End Deliverables

Failure Capture

Create immutable structured failure records supporting:

- compilation_failure
- unittest_failure
- validation_failure
- generated_file_failure
- unknown_failure

Include safe fields such as:

- category
- safe_summary
- return_code
- attempt_number
- retryable
- source
- timestamp
- bounded diagnostic text

Secret Safety

Sanitize diagnostics and redact common secrets including:

- API keys
- authorization headers
- passwords
- tokens
- secrets
- credentials

Do not retain raw unsanitized stdout or stderr.

Diagnostics must have a documented maximum length.

If truncation occurs, the final returned diagnostic string MUST end exactly with:

... [truncated]

The total returned string, including that suffix, must remain within the configured maximum length.

Repair Loop

Implement a bounded deterministic repair-loop state machine with states:

- pending
- diagnosing
- repair_planned
- validating
- succeeded
- exhausted
- blocked

Default maximum attempts: 3.

Reject zero, negative, unlimited, or unreasonable attempt limits.

Blocked Failures

Immediately block:

- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- CORE_PROTECTION_UNAVAILABLE
- security-policy failures
- repository safety failures
- authentication failures
- provider billing failures

Never attempt automatic Core escalation.

Never emit privileged maintenance markers.

Repair Plan

Create immutable safe repair plans containing:

- repair_id
- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

No unrestricted filesystem access.

No secrets.

No Core unlock.

Determinism

Equivalent normalized input must produce deterministic classification and state transitions.

Do not use random identifiers unless a deterministic identifier generator is injected.

Critical Safety Test Contract

The repair subsystem itself must not import or execute:

- subprocess
- socket
- requests
- urllib network clients
- Git libraries or Git commands
- os.system

IMPORTANT:

Do NOT test this by asserting that "subprocess" or "socket" is absent from sys.modules.

Other repository tests legitimately import subprocess and socket.

Instead, safety tests must inspect ONLY the source or AST of:

- agent/repair/failure_capture.py
- agent/repair/repair_loop.py
- agent/repair/__init__.py

and prove that those repair modules themselves do not import or invoke prohibited execution/network/Git facilities.

Do not make assertions about global sys.modules state.

Tests

Create comprehensive zero-skip tests covering at least:

1. compilation classification
2. unittest classification
3. validation classification
4. unknown classification
5. secret redaction
6. diagnostic truncation and exact "... [truncated]" suffix
7. total bounded diagnostic length
8. default three-attempt limit
9. configurable bounded attempts
10. invalid attempt-limit rejection
11. success transition
12. retry then success
13. exhaustion
14. CORE_PATH_LOCKED block
15. CANONICAL_TEST_LOCKED block
16. CORE_PROTECTION_UNAVAILABLE block
17. security failure block
18. provider authentication block
19. deterministic repair identifiers
20. deterministic equivalent input
21. no privileged marker emission
22. allowed/denied path preservation
23. no input mutation
24. no filesystem writes during pure planning
25. AST/source-based proof of no subprocess/network/Git execution

Do not use unittest.skip.

All new tests must execute.

Validation

All existing repository tests must remain passing.

Core Protection tests must remain unchanged and green.

Portable Recovery tests must remain unchanged and green.
