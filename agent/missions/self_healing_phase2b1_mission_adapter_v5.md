Mission: Self-Healing Phase 2B-1 Mission Adapter v5

Goal

Create the final non-Core Mission Repair Adapter.

This version preserves the proven retry and blocking behavior from previous
attempts and fixes exception sanitization so secret values are fully removed.

Do not modify Mission Runner or protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

General

Use Python standard library only.

Use unittest only.

Do not use pytest or unittest.skip.

Do not modify existing Phase 1, Phase 2A, Core Protection, Recovery,
or Mission Runner files.

Architecture

Create MissionRepairAdapter that bridges:

- IntegrationCoordinator
- validation callback
- repair-generation callback
- repair-application callback

All side effects must be injected.

Maximum repair attempts is exactly 3.

No fourth attempt may occur.

Generation failures are retryable until attempt 3 is exhausted.

Blocked conditions terminate immediately before generation/apply.

Repair Request

Use immutable safe RepairRequest with:

- mission_name
- attempt_number
- objective
- failure_category
- failure_summary
- allowed_paths
- denied_paths
- validation_required

Do not include raw diagnostics.

Paths

Allowed paths must never be expanded automatically.

Denied paths must never be removed.

Inputs must not be mutated.

Exception Sanitization Contract

This contract is mandatory.

Any exception-derived text that may contain credential-like key/value material
must be sanitized before being copied into:

- safe_summary
- failure history
- repair history
- repair requests
- returned result metadata

Sensitive key/value patterns may use:

- =
- :
- surrounding whitespace

When a sensitive key is detected, the COMPLETE associated value must be removed.

For example, a semantic pattern like:

secret=<credential>

must NOT become:

[redacted]=<credential>

It must become a form where the credential value is completely absent.

Similarly, a validation exception containing a sensitive key/value pair must
not leave any part of the value in safe_summary.

After sanitization:

- the original secret value must not appear anywhere
- no suffix or fragment of the secret may remain
- no raw exception text containing the secret may be preserved
- the sanitized text may use [REDACTED] or equivalent safe replacement

Handle at least common credential-like keys such as:

- password
- token
- secret
- api key variants
- authorization-style values

Bearer-style authentication must preserve only safe scheme context where
appropriate and remove the credential.

Sanitization must occur BEFORE building any user-visible or retained summary.

Do not rely on only replacing the sensitive key name.

Retry Contract

- generation failure on attempt 1 may retry
- generation failure on attempt 2 may retry
- generation failure on attempt 3 exhausts
- three total generation attempts maximum
- no fourth generation callback

Exception Safety

Validation, generation, and apply callback Exceptions must become safe failures.

Do not catch BaseException.

Do not leak raw exception values.

Generated Test Safety

Do not inspect sys.modules.

Do not include repository-forbidden dangerous call expressions literally.

For adapter safety validation, use AST Import / ImportFrom inspection only.

Tests

Create comprehensive zero-skip unittest coverage including at least:

1. initial validation success
2. one repair success
3. two repair success
4. third repair success
5. no fourth repair
6. exhaustion
7. generation failures invoke exactly three attempts
8. protected Core block
9. canonical test block
10. unavailable protection block
11. repository safety block
12. security policy block
13. provider authentication block
14. generation failure
15. generation exception is sanitized
16. generation exception secret value completely absent
17. apply failure
18. apply exception is sanitized
19. validation exception is sanitized
20. validation exception secret value completely absent from safe_summary
21. no raw exception secret remains in failure history
22. correct attempt numbers
23. safe failure category
24. allowed paths preserved
25. denied paths preserved
26. allowed paths not expanded
27. denied paths not removed
28. input immutability
29. repair history retained
30. failure history retained
31. deterministic equivalent result
32. secret diagnostics not copied raw
33. no privileged marker output
34. AST module-local import safety
35. maximum repair attempts exactly 3

Mandatory regression assertions

A generation exception containing a dynamically assembled value equivalent to:

secret=<value>

must not retain <value> anywhere in the result.

A validation exception containing a dynamically assembled value equivalent to:

token=<value>

must not retain <value> in safe_summary or failure history.

All tests must execute.

Acceptance

- adapter tests: zero failures/errors/skips
- Phase 2A tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
