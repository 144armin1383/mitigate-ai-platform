Mission: Self-Healing Repair Loop Phase 1

Goal

Build an isolated, portable, deterministic self-healing repair subsystem for failed development missions.

This phase MUST NOT modify protected Core.

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

Do not include privileged Core maintenance markers anywhere in this mission.

# Deliverables

- agent/repair/__init__.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py
- agent/tests/test_self_healing_repair_loop.py

# End Deliverables

Architecture

Create a standalone repair subsystem that does NOT execute Git operations, deployment operations, shell commands, network calls, provider calls, or production writes.

The subsystem must be pure Python and dependency-free beyond the standard library.

Failure Capture

Implement deterministic failure capture for development validation failures.

Support these categories:

- compilation_failure
- unittest_failure
- validation_failure
- generated_file_failure
- unknown_failure

Create an immutable structured failure record containing at least:

- category
- safe_summary
- return_code
- attempt_number
- retryable
- source
- timestamp or deterministic timestamp input
- bounded diagnostic text

Sensitive Data Safety

Diagnostic data must be sanitized.

Never retain:

- API keys
- authorization headers
- passwords
- access tokens
- secrets
- environment variable values
- provider credentials
- complete generated source files

Redact common secret patterns.

Diagnostic output must be bounded to a safe maximum length.

Do not persist raw stdout/stderr without sanitization.

Repair Loop

Implement a bounded repair-loop state machine.

States should cover at least:

- pending
- diagnosing
- repair_planned
- validating
- succeeded
- exhausted
- blocked

Default maximum repair attempts:

3

Maximum attempts must be configurable but must reject:

- zero
- negative values
- unreasonable unlimited values

The loop must never be infinite.

Repair Decision

For each failure determine whether repair is allowed.

Retryable examples:

- syntax/compiler failures
- unit-test assertion failures
- deterministic validation failures

Blocked/non-retryable examples:

- Core lock failures
- Canonical test lock failures
- security-policy failures
- authentication/provider billing failures
- repository safety failures

Recognize these failure codes as blocked:

- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- CORE_PROTECTION_UNAVAILABLE

A blocked failure must stop immediately.

Repair Plan

Create an immutable repair-plan object containing only safe planning metadata.

Include:

- repair_id
- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

Repair plans must never contain secrets or unrestricted filesystem access.

Determinism

For equivalent normalized input, classification and repair state transitions must be deterministic.

Do not use random UUIDs unless an injected deterministic identifier generator is supplied.

No Core Escalation

This subsystem must never generate or add:

- CORE_MAINTENANCE_APPROVED
- TEST_CONTRACT_MAINTENANCE_APPROVED

It must never request automatic Core unlock.

If a repair requires protected Core modification, return blocked state and a safe reason.

Interfaces

Expose stable functions/classes from agent/repair/__init__.py.

The subsystem should be usable later by Mission Runner without redesign.

Tests

Create comprehensive tests for:

1. compilation failure classification
2. unittest failure classification
3. validation failure classification
4. unknown failure handling
5. secret redaction
6. diagnostic truncation
7. default three-attempt limit
8. configurable bounded limit
9. invalid attempt limit rejection
10. successful repair transition
11. retry then success
12. attempt exhaustion
13. CORE_PATH_LOCKED immediate block
14. CANONICAL_TEST_LOCKED immediate block
15. CORE_PROTECTION_UNAVAILABLE immediate block
16. security failure block
17. provider authentication failure block
18. deterministic repair identifiers
19. equivalent input deterministic output
20. no privileged markers emitted
21. allowed and denied path preservation
22. input objects are not mutated
23. no filesystem writes during pure repair planning
24. no subprocess/network/Git execution
25. unrelated repository files remain unchanged

All tests must execute.

Do not use unittest.skip.

No test in this new test file may be skipped.

Validation

All repository tests must remain passing.

This phase is successful only when:

- new self-healing tests have zero failures
- zero errors
- zero skips
- existing Core Protection tests remain passing
- existing Portable Recovery tests remain passing
- full repository unittest suite remains passing
