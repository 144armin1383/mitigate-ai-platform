Mission: Self-Healing Phase 2B-1 Mission Adapter v4

Goal

Create the final non-Core Mission Repair Adapter used later by Mission Runner.

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

Create MissionRepairAdapter that bridges:

- IntegrationCoordinator
- validation callback
- repair-generation callback
- repair-application callback

All side effects must be injected.

The adapter itself must not directly perform process execution, shell execution,
Git execution, network access, provider access, deployment, or filesystem mutation.

Flow

Use IntegrationCoordinator for bounded control:

validation
→ repair request
→ generation callback
→ apply callback
→ revalidation
→ repeat as needed

Maximum repair attempts is exactly 3.

No fourth repair attempt may occur.

IMPORTANT RETRY CONTRACT

A generation failure is a retryable repair-attempt failure unless the enclosing
validation state is blocked or the maximum attempt count has been reached.

Therefore:

- if generation fails on attempt 1, attempt 2 may occur
- if generation fails on attempt 2, attempt 3 may occur
- if generation fails on attempt 3, the result must become exhausted
- when all three generation attempts fail, generate_repair_callback MUST have
  been called exactly 3 times
- no test may expect only 2 generation calls when max_attempts is 3 and all
  generation attempts fail
- no fourth generation callback may occur

Blocked conditions terminate before generation or application:

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

Do not include raw diagnostics or secrets.

Do not emit privileged maintenance authorization.

Paths

Allowed paths must never be expanded automatically.

Denied paths must never be removed.

Caller inputs must not be mutated.

Result

Return immutable MissionRepairResult containing:

- success
- final_state
- attempts
- safe_summary
- repair_requests
- failure_history

Exception Safety

Validation, generation, and apply callback Exceptions must become safe failures.

Do not expose raw secret-bearing exception details.

Do not catch BaseException.

Generated Test Safety

Do not inspect sys.modules.

Do not assert that global interpreter modules are absent.

For adapter safety validation:

- use ast.parse on agent/repair/mission_adapter.py
- inspect only Import and ImportFrom nodes
- verify mission_adapter.py itself does not directly import prohibited
  process/network/Git modules
- construct prohibited module names from harmless string pieces where needed
- do not include repository-forbidden dangerous call expressions literally
  anywhere in generated source, strings, comments, fixtures, assertions, or docstrings

Tests

Create comprehensive zero-skip unittest coverage including at least:

1. initial validation success
2. one repair then success
3. two repairs then success
4. third repair then success
5. no fourth repair
6. exhaustion
7. all three generation failures invoke generation exactly 3 times
8. generation failure on first attempt allows second attempt
9. generation failure on second attempt allows third attempt
10. third generation failure produces exhausted state
11. protected Core block
12. canonical test block
13. unavailable protection block
14. repository safety block
15. security policy block
16. provider authentication block
17. generation exception
18. apply failure
19. apply exception
20. validation exception
21. correct attempt number
22. safe failure category
23. safe failure summary
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
35. maximum repair attempts remains exactly 3

All tests must execute.

Acceptance

- adapter tests: zero failures/errors/skips
- Phase 2A tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
