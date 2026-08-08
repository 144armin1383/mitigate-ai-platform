Mission: Self-Healing Phase 2B-1 Mission Adapter v6

Goal

Create the final non-Core Mission Repair Adapter.

This version preserves proven retry, blocking, bounded-attempt, and path-safety
behavior while correcting two remaining test contracts:

1. Bearer authorization redaction must preserve the Bearer scheme.
2. Validation-exception tests must assert safe handling, not incorrectly require
   final failure when later validation succeeds.

Do not modify Mission Runner or protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

General

Use Python standard library only.

Use unittest only.

Do not use pytest or unittest.skip.

Do not modify existing Phase 1, Phase 2A, Core Protection, Recovery, or Mission Runner files.

Architecture

Create MissionRepairAdapter using the existing IntegrationCoordinator.

All side effects must be injected.

Maximum repair attempts is exactly 3.

No fourth attempt may occur.

Blocked states must terminate before generation or apply.

Bearer Redaction Contract

Authorization Bearer data must sanitize to the canonical safe form:

Authorization: Bearer [REDACTED]

The word Authorization must remain correct.

The word Bearer must remain visible.

The credential must be completely absent.

Do not apply generic authorization/token redaction in a way that transforms:

Authorization: Bearer [REDACTED]

into:

Authorization: [REDACTED] [REDACTED]

Bearer-specific redaction must run before generic redaction and the canonical
Bearer-safe form must be preserved by subsequent sanitization passes.

Failure history containing sanitized Bearer authorization data must retain:

Authorization: Bearer [REDACTED]

and must contain no original credential fragment.

Validation Exception Lifecycle Contract

A validation callback exception must be converted into a safe validation failure
for that validation event.

However, the FINAL MissionRepairResult must reflect the complete bounded lifecycle.

If a later repair and later validation succeed, the final result may legitimately
be success=True.

Therefore tests must NOT assert that final success is always False merely because
an earlier validation callback raised an Exception.

Instead, tests must verify:

- the exception event is safely represented
- raw secret values are absent
- failure history records the failure safely
- retry behavior remains bounded
- if a later validation succeeds, final result is succeeded
- if all later validations fail, final result is exhausted or blocked as appropriate

Exception Safety

Validation, generation, and apply callback Exceptions must be sanitized before
any retained or returned metadata is built.

Secret values must not remain in:

- safe_summary
- failure history
- repair requests
- repair history
- final result metadata

Retry Contract

Generation failure is retryable through attempt 3.

Exactly three maximum generation attempts.

No fourth generation callback.

Path Safety

Allowed paths must never expand automatically.

Denied paths must never be removed.

Inputs must not be mutated.

Generated Test Safety

Do not inspect sys.modules.

Do not include forbidden dangerous-call literals.

Use AST Import/ImportFrom inspection only for module-local safety checks.

Tests

Create zero-skip unittest coverage including at least:

1. initial validation success
2. one repair success
3. two repairs success
4. third repair success
5. no fourth repair
6. exhaustion
7. three generation failures mean exactly three generation calls
8. protected Core block
9. canonical test block
10. unavailable protection block
11. repository safety block
12. security policy block
13. provider authentication block
14. generation exception sanitized
15. apply exception sanitized
16. validation exception safely recorded
17. validation exception followed by later validation success may end succeeded
18. validation exception with continued failure ends exhausted
19. Bearer history uses exact canonical safe form
20. Bearer credential completely absent
21. generic secret values fully removed
22. allowed paths preserved
23. denied paths preserved
24. allowed paths not expanded
25. denied paths not removed
26. input immutability
27. repair history retained
28. failure history retained
29. deterministic equivalent result
30. no privileged marker output
31. AST module-local import safety
32. maximum attempts exactly 3

Mandatory regression assertions

Failure-history text containing a Bearer authorization event must contain:

Authorization: Bearer [REDACTED]

and must not contain the original credential.

A validation callback Exception must not automatically force final success=False
when a later bounded repair and validation sequence succeeds.

All tests must execute.

Acceptance

- adapter tests: zero failures/errors/skips
- Phase 2A tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
