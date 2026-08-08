Mission: Self-Healing Repair Loop Phase 1 v6

Goal

Build a minimal, deterministic, dependency-free self-healing repair subsystem for failed non-Core development missions.

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

General Rules

Use only the Python standard library.

Tests MUST use unittest only.

Do not import or depend on pytest.

All generated source must pass existing Mission Runner forbidden-content checks.

Do not include sensitive or dangerous forbidden fragments literally in source, strings, comments, fixtures, or docstrings.

Failure Capture

Create immutable failure records with:

- category
- safe_summary
- return_code
- attempt_number
- retryable
- source
- diagnostic

Support categories:

- compilation_failure
- unittest_failure
- validation_failure
- generated_file_failure
- unknown_failure

Sanitize diagnostic text.

Redact common credential-like values.

Use a fixed diagnostic maximum length.

When truncation occurs:

- total result must remain within the maximum
- result must end with the text:
  ... [truncated]

Repair Loop

Create deterministic states:

- pending
- diagnosing
- repair_planned
- validating
- succeeded
- exhausted
- blocked

Default maximum attempts: 3.

Allow configurable finite limits.

Reject invalid limits including zero and negative values.

Immediately block failures corresponding to:

- protected Core access
- canonical recovery test access
- unavailable Core protection
- security-policy failures
- repository-safety failures
- provider authentication failures

Do not attempt Core escalation.

Do not emit privileged maintenance markers.

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

Equivalent normalized input must produce deterministic repair IDs and decisions.

Pure Logic

This subsystem must not:

- execute shell commands
- execute processes
- access network services
- execute Git commands
- perform deployment
- mutate the filesystem during planning

Do not create tests that inspect global sys.modules.

Do not create AST-based dangerous-call tests in this phase.

Tests

Create at least 20 unittest tests covering:

1. compilation classification
2. unittest classification
3. validation classification
4. generated-file classification
5. unknown classification
6. secret redaction using harmless dynamically assembled test data
7. diagnostic truncation
8. diagnostic length bound
9. default three-attempt limit
10. configurable attempt limit
11. invalid attempt limit rejection
12. successful transition
13. retry then success
14. attempt exhaustion
15. protected-Core failure block
16. canonical-test failure block
17. unavailable-protection failure block
18. deterministic repair IDs
19. input immutability
20. allowed and denied path preservation
21. no privileged marker output
22. no filesystem mutation during planning

Do not use unittest.skip.

All tests in test_self_healing_repair_loop.py must execute.

Validation

Existing Core Protection tests must remain unchanged and passing.

Existing Portable Recovery tests must remain unchanged and passing.

All repository tests must remain passing.
