Mission: Self-Healing Repair Loop Phase 1 v3

Goal

Build an isolated deterministic self-healing repair subsystem for failed non-Core development missions.

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

Include:

- category
- safe_summary
- return_code
- attempt_number
- retryable
- source
- timestamp
- bounded diagnostic text

Sanitization

Redact common secret material including:

- API keys
- passwords
- tokens
- authorization data
- credentials
- secrets

Never retain raw unsanitized output.

Diagnostics must have a fixed documented maximum length.

When truncation occurs:

- the returned value must remain within the configured maximum
- it must end exactly with:

... [truncated]

Repair Loop

Implement deterministic states:

- pending
- diagnosing
- repair_planned
- validating
- succeeded
- exhausted
- blocked

Default maximum attempts: 3.

Maximum attempts must be configurable within a reasonable finite bound.

Reject:

- zero
- negative
- unlimited
- unreasonable attempt limits

Blocked Failures

Immediately block:

- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- CORE_PROTECTION_UNAVAILABLE
- security policy failures
- repository safety failures
- provider authentication failures
- provider billing failures

Never attempt Core escalation.

Never emit privileged Core or canonical-test maintenance markers.

Repair Plan

Create immutable repair plans containing safe metadata only:

- repair_id
- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

Repair identifiers must be deterministic for equivalent normalized inputs.

Safety

The repair subsystem must remain pure Python planning/state logic.

It must not perform:

- process execution
- shell execution
- network activity
- Git execution
- deployment
- filesystem mutation during planning

IMPORTANT TEST IMPLEMENTATION RULE

Safety tests MUST NOT inspect global sys.modules state.

Safety tests must inspect only the AST/source structure of the three agent/repair modules.

Do not place forbidden execution-call expressions literally in the generated test source.

In particular, do not write literal call expressions for dangerous process or shell execution APIs anywhere in the generated test file, even inside strings, comments, assertions, fixtures, or documentation.

For AST safety validation:

- inspect Import and ImportFrom nodes
- reject prohibited imported module names using data values assembled safely
- inspect Call / Attribute nodes structurally
- detect prohibited calls using AST node attributes rather than embedding forbidden source-call text

The generated test itself must pass Mission Runner forbidden-content validation.

Tests

Create zero-skip tests covering at least:

1. compilation classification
2. unittest classification
3. validation classification
4. generated-file classification
5. unknown classification
6. secret redaction
7. diagnostic truncation
8. exact truncation suffix
9. total diagnostic size bound
10. default 3-attempt limit
11. configurable bounded limit
12. invalid limit rejection
13. successful transition
14. retry then success
15. exhaustion
16. CORE_PATH_LOCKED immediate block
17. CANONICAL_TEST_LOCKED immediate block
18. CORE_PROTECTION_UNAVAILABLE immediate block
19. security failure block
20. authentication failure block
21. deterministic identifiers
22. deterministic equivalent input
23. allowed-path preservation
24. denied-path preservation
25. input immutability
26. no privileged marker emission
27. no filesystem writes during planning
28. AST-based proof that repair modules do not import prohibited execution/network/Git modules
29. AST-based proof that repair modules do not invoke prohibited execution/network/Git calls

Do not use unittest.skip.

All new tests must execute.

Validation

All repository tests must remain passing.

Core Protection tests must remain unchanged and green.

Portable Recovery tests must remain unchanged and green.
