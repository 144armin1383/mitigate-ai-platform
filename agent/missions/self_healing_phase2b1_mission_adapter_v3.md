Mission: Self-Healing Phase 2B-1 Mission Adapter v3

Goal

Create the non-Core Mission Repair Adapter used later by Mission Runner.

This version fixes the generated-source safety-test contract so that the test
itself does not contain repository-forbidden literal fragments.

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

Do not modify any existing file.

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
→ validation
→ repeat

Maximum repair attempts is 3.

No fourth repair attempt may occur.

Blocked conditions terminate before generation or apply:

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

Do not include raw diagnostics.

Do not include secrets.

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

Exceptions

Ordinary validation, generation, and apply callback exceptions must be converted
to safe failures.

Do not catch BaseException.

CRITICAL TEST-SOURCE SAFETY RULE

The generated test file itself MUST pass Mission Runner forbidden-content scanning.

Do NOT include complete dangerous call expressions anywhere in the generated test
source, including in strings, comments, fixtures, assertions, or docstrings.

Do NOT write literal dangerous execution expressions.

Do NOT inspect sys.modules.

For module-local safety validation:

- parse agent/repair/mission_adapter.py using ast.parse
- inspect only Import and ImportFrom nodes
- inspect imported top-level module names
- build prohibited module names from harmless string pieces at runtime if needed
- verify mission_adapter.py itself does not import prohibited process, network,
  or Git-related modules

Do not inspect dangerous Call expressions in this phase.

Do not include repository-forbidden literal fragments in generated files.

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
26. repair history retained
27. failure history retained
28. deterministic equivalent result
29. secret diagnostics not copied raw
30. no privileged maintenance marker emitted
31. AST import safety for mission_adapter.py only
32. maximum repair attempts remains 3

All tests must execute.

Acceptance

- adapter tests: zero failures/errors/skips
- Phase 2A tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
