Mission: Self-Healing Repair Loop Phase 1 Bearer Final

Goal

Produce the final Phase 1 Self-Healing Repair subsystem.

Previous generations already proved that:
- deterministic repair IDs can pass
- diagnostic truncation can pass
- bounded retry logic can pass
- Core blocking can pass

Preserve those contracts.

The remaining defect to prevent is Authorization Bearer credential redaction.

Do not modify protected Core.

# Deliverables

- agent/repair/__init__.py
- agent/repair/failure_capture.py
- agent/repair/repair_loop.py
- agent/tests/test_self_healing_repair_loop.py

# End Deliverables

General

Use Python standard library only.

Tests must use unittest only.

Do not use pytest.

Do not use unittest.skip.

All generated source must pass existing Mission Runner content-safety validation.

Do not modify any existing repository file outside the four deliverables.

Failure Capture

Implement immutable structured failure records supporting:

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

Diagnostic Safety

Sanitize diagnostics before retaining them.

Redact credential-like values.

Use one explicit maximum diagnostic length.

For truncated diagnostics:

- result must remain within the maximum
- result must end exactly with:

... [truncated]

- no newline or whitespace may follow that suffix

Bearer Authorization Contract

This contract is mandatory.

An authorization header using the Bearer authentication scheme must preserve the header name and authentication scheme while removing only the credential value.

Semantic input:

Authorization: Bearer <credential>

Required sanitized output:

Authorization: Bearer [REDACTED]

Requirements:

1. Preserve the exact word:
Authorization

2. Preserve the exact word:
Bearer

3. Replace the complete credential following Bearer with:
[REDACTED]

4. Do not leave any part of the original credential.

5. Do not misspell, duplicate, mutate, or partially rewrite Authorization.

6. Do not produce forms such as:
- Authoriization
- Authorization: [REDACTED]
- Bearer <original credential>
- Authorization: Bearer <partial credential>

7. Matching should be case-insensitive where appropriate, while sanitized output should use canonical:
Authorization: Bearer [REDACTED]

Implementation Guidance

Handle the complete Authorization Bearer pattern before applying more general token/password/secret redaction rules.

The specific Bearer-header rule must take precedence over generic credential rules.

A regular-expression substitution using the Python standard library is appropriate.

After Bearer-specific redaction is complete, generic sanitization may run without altering the already sanitized canonical result.

Tests must build sensitive-looking fixture credentials dynamically from harmless pieces where necessary so generated source remains compatible with repository content-safety scanning.

Deterministic Repair IDs

Repair IDs must be derived only from canonical stable inputs.

They must NOT depend on:

- current time
- random values
- random UUID generation
- process state
- object identity
- mutable counters

Equivalent normalized inputs must always produce identical repair_id values.

Use deterministic canonical serialization plus a standard-library digest.

Repair Loop

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

Reject zero and negative limits.

Immediately block conditions representing:

- protected Core access
- canonical recovery test access
- unavailable Core protection
- security-policy bypass
- repository-safety bypass
- provider authentication intervention

Never escalate automatically into protected Core.

Repair Plan

Repair plans must be immutable and contain:

- repair_id
- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

Pure Logic

The subsystem must not:

- execute shell commands
- execute external processes
- perform network access
- execute Git
- deploy
- mutate filesystem state during planning

Tests

Create at least 25 unittest tests.

Mandatory tests include:

1. compilation classification
2. unittest classification
3. validation classification
4. generated-file classification
5. unknown classification
6. generic credential redaction
7. Authorization Bearer redaction
8. exact canonical Authorization spelling
9. Bearer scheme preservation
10. original Bearer credential completely absent after sanitization
11. diagnostic truncation
12. exact truncation suffix
13. diagnostic maximum length
14. short diagnostic unchanged
15. default three-attempt limit
16. configurable attempt limit
17. invalid attempt limit
18. successful transition
19. retry then success
20. exhaustion
21. protected-Core immediate block
22. canonical-test immediate block
23. unavailable-protection immediate block
24. deterministic repair IDs for equivalent input
25. changed meaningful input changes repair ID
26. allowed and denied path preservation
27. input immutability
28. no privileged maintenance output
29. no filesystem mutation during planning

Acceptance Gate

The following must all pass:

- Self-Healing tests: zero failures
- Self-Healing tests: zero errors
- Self-Healing tests: zero skips
- Core Protection tests unchanged and passing
- Portable Recovery tests unchanged and passing
- complete repository unittest suite passing

The previously observed output:

Authoriization: Bearer abc123XYZ

is explicitly incorrect and must never occur.

The required semantic sanitized form is:

Authorization: Bearer [REDACTED]
