Mission: Self-Healing Repair Loop Phase 1 v5

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

Redact common secret material including API credentials, passwords,
authorization values, tokens, private-key material, and secrets.

Never retain raw unsanitized diagnostic output.

Diagnostics must have a fixed documented maximum length.

When truncation occurs:

- total returned string must remain within the configured maximum
- returned value must end exactly with:

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

Reject zero, negative, unlimited, and unreasonable limits.

Immediately block failures representing:

- protected Core writes
- canonical-test writes
- unavailable Core protection
- security-policy failures
- repository-safety failures
- provider authentication failures
- provider billing failures

Never attempt Core escalation.

Never emit privileged maintenance authorization markers.

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

The repair subsystem is pure planning/state logic.

It must not import or invoke process execution, shell execution,
network clients, Git execution, or deployment functionality.

CRITICAL GENERATED-SOURCE SAFETY CONTRACT

All four generated deliverables must themselves pass Mission Runner
forbidden-content validation.

The generated test source MUST NOT contain any complete forbidden
fragment as contiguous source text, including inside:

- strings
- comments
- fixtures
- assertions
- docstrings
- variable names
- sample diagnostics

For secret-redaction tests, construct sensitive-looking sample values
at runtime from harmless string pieces.

Example principle:

    prefix = "BEGIN "
    suffix = "PRIVATE" + " KEY"
    sample = prefix + suffix

The complete sensitive pattern must not appear contiguously in the
source file.

Use the same technique for any credential-like test value that could
match repository forbidden-content scanning.

Do not include literal examples copied from Mission Runner's forbidden
fragment list anywhere in generated files.

AST Safety Tests

Safety tests must inspect only Import and ImportFrom nodes of:

- agent/repair/__init__.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py

Do not inspect global sys.modules.

Do not include dangerous call expressions in source.

Build prohibited module-name values from harmless components where
necessary.

Tests

Create zero-skip tests covering at least:

1. compilation classification
2. unittest classification
3. validation classification
4. generated-file classification
5. unknown classification
6. secret redaction using dynamically assembled safe fixtures
7. diagnostic truncation
8. exact truncation suffix
9. bounded diagnostic length
10. default three-attempt limit
11. configurable bounded limit
12. invalid limit rejection
13. successful transition
14. retry then success
15. exhaustion
16. protected-Core failure immediate block
17. canonical-test failure immediate block
18. unavailable-protection failure immediate block
19. security failure block
20. authentication failure block
21. deterministic identifiers
22. equivalent-input determinism
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
