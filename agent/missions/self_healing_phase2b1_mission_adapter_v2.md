Mission: Self-Healing Phase 2B-1 Mission Adapter v2

Goal

Create the non-Core Mission Repair Adapter used later by Mission Runner.

This version corrects the safety-test contract from the previous failed attempt.

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

The adapter itself must not perform:

- subprocess execution
- shell execution
- Git execution
- network access
- provider calls
- deployment
- direct filesystem mutation

Flow

Use IntegrationCoordinator for bounded control.

Support:

validation
→ repair request
→ generation callback
→ apply callback
→ validation
→ repeat up to maximum 3 attempts

No fourth repair attempt.

Blocked conditions must terminate before generation or application:

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

Never include raw unsanitized diagnostic content.

Never add privileged maintenance authorization.

Path Safety

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

Ordinary callback exceptions must become safe failures.

Do not expose raw secret-bearing exceptions.

Do not catch BaseException.

CRITICAL SAFETY TEST CORRECTION

The previous implementation used a global-interpreter assertion such as checking
whether prohibited modules exist in sys.modules.

That approach is invalid because the wider repository legitimately imports
process, network, and Git-related modules before this adapter test runs.

DO NOT inspect sys.modules.

DO NOT assert that a module is absent from the global Python interpreter.

Instead, verify ONLY the Mission Adapter implementation itself.

Acceptable approaches include:

- inspect the AST of agent/repair/mission_adapter.py
- inspect Import and ImportFrom nodes belonging to that file
- inspect that module's own namespace
- inspect that module's own source text using safely assembled prohibited names

The test must prove that mission_adapter.py itself does not directly import or
invoke prohibited process/network/Git facilities.

The test must remain valid regardless of what other repository modules have
already imported.

Do not create a test that fails merely because another repository module has
loaded subprocess, socket, asyncio, urllib, Git helpers, or similar modules.

Tests

Create comprehensive zero-skip unittest coverage including at least:

1. initial validation success
2. one repair then success
3. two repairs then success
4. third repair then success
5. no fourth repair
6. exhaustion
7. protected Core block
8. canonical test block
9. unavailable protection block
10. repository safety block
11. security policy block
12. provider authentication block
13. generation failure
14. generation exception
15. apply failure
16. apply exception
17. validation exception
18. correct attempt number
19. safe failure category
20. safe failure summary
21. allowed paths preserved
22. denied paths preserved
23. allowed paths not expanded
24. denied paths not removed
25. input immutability
26. repair history
27. failure history
28. deterministic equivalent result
29. secret diagnostic not copied raw
30. no privileged marker output
31. module-local safety test that does NOT inspect sys.modules
32. maximum repair attempts remains 3

All tests must execute.

Acceptance

- adapter tests: zero failures
- zero errors
- zero skips
- Phase 2A tests remain passing
- Phase 1 tests remain passing
- Core Protection remains passing
- Portable Recovery remains passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
