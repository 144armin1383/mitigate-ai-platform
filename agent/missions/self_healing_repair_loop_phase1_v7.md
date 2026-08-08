Mission: Self-Healing Repair Loop Phase 1 v7

Goal

Build the minimal deterministic self-healing repair subsystem for failed non-Core missions.

This is the final Phase 1 contract.

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

General

Use Python standard library only.

Tests MUST use unittest only.

Do not use pytest.

All generated files must pass existing Mission Runner forbidden-content validation.

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
- diagnostic

Sanitize diagnostic text and redact credential-like values.

Diagnostic Truncation Contract

Define one explicit constant for the maximum diagnostic length.

Define the truncation suffix exactly as:

... [truncated]

When sanitized diagnostic text exceeds the configured maximum:

1. reserve space for the complete suffix
2. keep only the leading portion that fits
3. append the complete suffix
4. ensure len(result) is never greater than the configured maximum
5. ensure result.endswith("... [truncated]") is always True for truncated output

Conceptually:

suffix = "... [truncated]"
available = maximum_length - len(suffix)
result = sanitized_text[:available] + suffix

Reject invalid diagnostic maximum values that are too short to contain the suffix.

Do not truncate after appending the suffix.

Do not append whitespace or newline after the suffix.

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

Allow finite configurable attempt limits.

Reject zero, negative, unlimited, or unreasonable limits.

Immediately block failures corresponding to:

- protected Core access
- canonical recovery test access
- unavailable Core protection
- security policy
- repository safety
- provider authentication

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

Equivalent normalized inputs must produce deterministic decisions and repair identifiers.

Pure Logic

The repair subsystem must not:

- execute shell commands
- execute external processes
- access network services
- execute Git
- deploy
- mutate filesystem state during planning

Tests

Create at least 20 unittest tests.

The diagnostic truncation tests are mandatory and must prove:

- long diagnostic is truncated
- truncated diagnostic ends exactly with "... [truncated]"
- truncated diagnostic length is <= configured maximum
- short diagnostic remains unchanged
- no newline follows truncation suffix

Also test:

- failure classifications
- secret redaction with dynamically assembled safe fixtures
- default 3-attempt limit
- configurable attempt limit
- invalid attempt limits
- success
- retry then success
- exhaustion
- protected Core block
- canonical-test block
- unavailable-protection block
- deterministic repair IDs
- input immutability
- allowed/denied paths
- no privileged marker output
- no filesystem mutation during planning

Do not use unittest.skip.

All Self-Healing tests must execute with:

- zero failures
- zero errors
- zero skips

Existing Core Protection and Portable Recovery tests must remain unchanged and green.

Full repository unittest suite must remain passing.
