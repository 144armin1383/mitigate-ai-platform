Mission: Self-Healing Repair Loop Phase 1 v4

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

Include safe fields:

- category
- safe_summary
- return_code
- attempt_number
- retryable
- source
- timestamp
- bounded diagnostic text

Sanitization

Redact common secret material.

Never retain raw unsanitized diagnostics.

Diagnostics must have a fixed maximum length.

When truncation occurs:

- final string must remain within the configured maximum
- final string must end exactly with:

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

Reject zero, negative, unlimited, or unreasonable limits.

Blocked failures must include:

- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- CORE_PROTECTION_UNAVAILABLE
- security policy failures
- repository safety failures
- provider authentication failures
- provider billing failures

Never attempt Core escalation.

Never emit privileged maintenance markers.

Repair Plan

Create immutable repair plans containing:

- repair_id
- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

Equivalent normalized input must produce deterministic results.

Safety

The repair subsystem must be pure planning/state logic.

It must not import process-execution, network-client, or Git-execution modules.

IMPORTANT TEST RULE

Safety tests must inspect only AST Import and ImportFrom nodes of:

- agent/repair/__init__.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py

Do not inspect global sys.modules.

Do not test dangerous function-call names.

Do not include literal dangerous call expressions anywhere in the generated test file.

Do not include any Mission Runner forbidden-content fragments in generated source, comments, strings, fixtures, assertions, or documentation.

Safety tests should simply parse each repair module with ast.parse and verify imported top-level module names are not members of a safely constructed prohibited-import set.

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
10. default three-attempt limit
11. configurable bounded limit
12. invalid limit rejection
13. success transition
14. retry then success
15. exhaustion
16. CORE_PATH_LOCKED block
17. CANONICAL_TEST_LOCKED block
18. CORE_PROTECTION_UNAVAILABLE block
19. security failure block
20. authentication failure block
21. deterministic identifiers
22. equivalent input determinism
23. allowed-path preservation
24. denied-path preservation
25. input immutability
26. no privileged marker emission
27. no filesystem writes during planning
28. AST import safety for repair modules

Do not use unittest.skip.

All new tests must execute.

All existing repository tests must remain passing.

Core Protection and Portable Recovery tests must remain unchanged and green.
