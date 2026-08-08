Mission: Self-Healing Phase 2B-1 Mission Adapter v7

Goal

Create the final non-Core Mission Repair Adapter and its correct test suite.

Do not modify Mission Runner or protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

General

Use Python standard library only.
Use unittest only.
Do not use pytest.
Do not use unittest.skip.

Do not modify existing Phase 1, Phase 2A, Core Protection, Recovery, or Mission Runner files.

Architecture

Create MissionRepairAdapter that connects:

- existing IntegrationCoordinator
- validation callback
- repair-generation callback
- repair-application callback

All side effects must be injected.

The adapter must not directly perform Git, shell/process execution, network calls,
deployment, provider access, or filesystem mutation.

Maximum Attempts

Maximum repair attempts is exactly 3.

No fourth repair attempt may occur.

When generation fails on all attempts:

- generate callback called exactly 3 times
- final state exhausted
- no fourth call

Blocked Conditions

Immediately stop before generation/apply for:

- protected-core-access
- canonical-recovery-test-access
- unavailable-core-protection
- repository-safety-bypass
- security-policy-bypass
- provider-authentication-intervention

Repair Request

Create immutable safe RepairRequest containing:

- mission_name
- attempt_number
- objective
- failure_category
- failure_summary
- allowed_paths
- denied_paths
- validation_required

Do not include raw unsanitized diagnostics.

Path Safety

Allowed paths must never expand automatically.

Denied paths must never be removed.

Caller inputs must not be mutated.

Exception Safety

Validation, generation, and apply callback Exceptions must be converted to safe
failure events.

Do not catch BaseException.

Do not leak raw secret values.

Redaction Contract

Generic credential redaction must remove the complete secret value.

Examples of acceptable semantic output:

password: [REDACTED]

or

password: '[REDACTED]'

Tests MUST NOT require preservation of quotation marks.

Tests must require:

- original secret absent
- [REDACTED] present
- credential key context remains understandable

Bearer authorization has a stricter canonical form:

Authorization: Bearer [REDACTED]

The Bearer scheme must remain visible.

The original credential must be completely absent.

Validation Exception Lifecycle

A validation exception is a failure event.

It does NOT automatically require final mission failure.

If a later bounded repair and validation succeeds, final result may be succeeded.

If validation continues failing through attempt 3, final result becomes exhausted
unless policy blocks earlier.

AST Safety Test

Do NOT inspect sys.modules.

Do NOT read the test file and assert that a string used by the assertion itself
is absent.

Inspect only:

agent/repair/mission_adapter.py

Use ast.parse.

Inspect only Import and ImportFrom nodes.

Build prohibited module names from harmless string pieces at runtime if needed.

Verify that mission_adapter.py itself does not directly import prohibited process,
network, Git, or deployment modules.

Do not use global interpreter state.

Do not include repository-forbidden dangerous call expressions literally in
generated source.

Tests

Create comprehensive zero-skip unittest tests covering at least:

1. initial validation success
2. one repair success
3. two repairs success
4. third repair success
5. no fourth attempt
6. exhaustion
7. exactly three generation calls on three generation failures
8. protected Core block
9. canonical test block
10. unavailable Core protection block
11. repository safety block
12. security policy block
13. provider authentication block
14. generation failure
15. generation exception sanitized
16. apply failure
17. apply exception sanitized
18. validation exception safely recorded
19. validation exception followed by later success
20. validation exception followed by continued failure
21. Bearer canonical redaction
22. Bearer secret absence
23. generic secret removal without quote-format requirement
24. allowed paths preserved
25. denied paths preserved
26. allowed paths not expanded
27. denied paths not removed
28. input immutability
29. repair history retained
30. failure history retained
31. deterministic equivalent result
32. no privileged maintenance output
33. AST module-local import safety
34. maximum attempts exactly 3

All tests must execute.

Acceptance

- adapter tests: zero failures
- zero errors
- zero skips
- Phase 2A tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
