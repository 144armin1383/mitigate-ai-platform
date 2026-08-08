Mission: Self-Healing Repair Loop Phase 1 Final

Goal

Build the final deterministic dependency-free Self-Healing Repair Loop Phase 1.

This mission supersedes previous failed Phase 1 generation attempts.

Do not modify protected Core or canonical recovery tests.

# Deliverables

- agent/repair/__init__.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py
- agent/tests/test_self_healing_repair_loop.py

# End Deliverables

GENERAL

Use Python standard library only.

Tests must use unittest only.

Do not use pytest.

Do not use unittest.skip.

All generated source must pass existing Mission Runner content-safety validation.

Do not modify any existing repository file outside the four deliverables.

FAILURE CAPTURE

Implement immutable structured failure records.

Support:

- compilation_failure
- unittest_failure
- validation_failure
- generated_file_failure
- unknown_failure

Include safe metadata:

- category
- safe_summary
- return_code
- attempt_number
- retryable
- source
- diagnostic

Sanitize diagnostic information before retaining it.

DIAGNOSTIC BOUNDING

Use one explicit maximum diagnostic-length constant.

Use the exact truncation suffix:

... [truncated]

For oversized diagnostics:

suffix = "... [truncated]"
available = maximum_length - len(suffix)
result = sanitized_text[:available] + suffix

Required invariants:

- result length never exceeds maximum
- truncated result ends exactly with the suffix
- no whitespace or newline follows suffix
- short diagnostics remain unchanged

SECRET REDACTION CONTRACT

Redaction must preserve useful non-sensitive authentication scheme context.

For authorization-style values using the Bearer scheme:

Input concept:

Authorization header + Bearer scheme + credential value

Required safe semantic result:

Authorization: Bearer [REDACTED]

The word Bearer must remain visible.

The credential value following Bearer must be fully removed.

Do not leave fragments of the original credential.

Other password/token/secret values must be replaced with [REDACTED].

Tests must construct sensitive-looking fixtures dynamically from harmless pieces so generated test source passes repository content-safety scanning.

DETERMINISTIC REPAIR ID CONTRACT

Repair IDs MUST NOT depend on:

- current time
- timestamps
- random values
- UUID randomness
- process state
- object identity
- memory address
- mutable global counters

Equivalent normalized repair-plan input must always produce exactly the same repair_id.

Generate repair_id from canonical stable plan inputs only.

Canonical inputs should include stable values such as:

- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

Normalize before hashing:

- strings consistently
- tuples/lists deterministically
- path collections deterministically
- mapping keys deterministically

Use a deterministic standard-library digest over canonical serialized data.

A suitable result form is:

rpln_<stable digest prefix>

Creating the same plan twice with equivalent inputs MUST produce identical repair IDs.

Changing a meaningful canonical input SHOULD change the repair ID.

REPAIR LOOP

Support states:

- pending
- diagnosing
- repair_planned
- validating
- succeeded
- exhausted
- blocked

Default maximum attempts: 3.

Allow reasonable finite configurable limits.

Reject invalid limits including zero and negative values.

Failures requiring protected Core changes, canonical-test changes, unavailable Core protection, repository safety bypass, security bypass, or provider authentication intervention must become blocked.

Never escalate into protected Core automatically.

Repair plans must be immutable and preserve:

- repair_id
- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

PURE LOGIC

The subsystem must not perform shell execution, external process execution, network access, Git execution, deployment, or filesystem mutation during planning.

TEST CONTRACT

Create at least 25 unittest tests with zero skips.

Tests must cover:

- all failure classifications
- unknown failures
- secret redaction
- Bearer scheme preservation with credential redaction
- no residual credential fragments
- diagnostic truncation
- exact truncation suffix
- diagnostic length bound
- short diagnostic preservation
- default three attempts
- configurable attempts
- invalid attempts
- success transition
- retry then success
- exhaustion
- blocked protected-Core condition
- blocked canonical-test condition
- unavailable protection block
- deterministic repair IDs for equivalent inputs
- different meaningful input produces different repair ID
- deterministic behavior across repeated construction
- allowed paths preserved
- denied paths preserved
- input immutability
- no privileged authorization output
- no filesystem mutation during planning

CRITICAL ACCEPTANCE CONDITIONS

The following previous defects must not recur:

1. Two equivalent RepairPlan constructions must never produce different repair_id values.

2. Bearer-style authorization redaction must preserve the Bearer scheme and replace only the credential with [REDACTED].

3. Truncated diagnostic text must end exactly with "... [truncated]".

Existing Core Protection tests must remain unchanged and passing.

Existing Portable Recovery tests must remain unchanged and passing.

The complete repository unittest suite must pass.
