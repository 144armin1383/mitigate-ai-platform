Mission: Self-Healing Phase 2B-1.1 Adapter Coordinator Unification v2

Goal

Refactor MissionRepairAdapter so the existing Phase 2A IntegrationCoordinator
is the single authoritative repair-loop engine.

Do not modify Mission Runner or protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

Architecture

Reuse the existing:

- agent/repair/integration.py
- IntegrationCoordinator
- ValidationResult
- RepairExecutionResult
- IntegrationResult

MissionRepairAdapter must become a translation layer around IntegrationCoordinator.

IntegrationCoordinator must own:

- initial validation
- attempt counting
- retry progression
- revalidation
- succeeded state
- exhausted state
- blocked state
- maximum attempt enforcement

MissionRepairAdapter must NOT implement an independent competing retry loop.

Adapter Responsibilities

The adapter may only:

1. translate mission context into IntegrationCoordinator inputs
2. translate validation output into ValidationResult-compatible data
3. translate RepairPlan into immutable RepairRequest
4. call injected repair generation
5. call injected repair application
6. translate IntegrationResult into mission-oriented safe output

Maximum Attempts

The existing IntegrationCoordinator maximum-attempt policy is authoritative.

Default maximum is 3.

No fourth generation attempt may occur.

Blocked Conditions

Use the existing IntegrationCoordinator blocking contract for:

- protected-core-access
- canonical-recovery-test-access
- unavailable-core-protection
- repository-safety-bypass
- security-policy-bypass
- provider-authentication-intervention

Blocked conditions must prevent repair generation.

Security

Preserve canonical Bearer redaction:

Authorization: Bearer [REDACTED]

Generic secrets must be fully removed.

Do not leak exception credentials.

Do not catch BaseException.

Paths

Allowed paths must not expand automatically.

Denied paths must not be removed.

Caller inputs must not be mutated.

Side Effects

MissionRepairAdapter must not directly perform:

- process execution
- shell execution
- Git operations
- network access
- deployment
- provider access
- filesystem mutation

All side effects remain injected.

CRITICAL GENERATED-TEST SAFETY RULE

The generated test source itself must pass Mission Runner content validation.

Do NOT include complete forbidden call expressions anywhere in:

- source code
- strings
- comments
- fixtures
- assertions
- docstrings

Do not write dangerous execution call syntax literally.

Do not inspect sys.modules.

For module-local safety testing:

- parse agent/repair/mission_adapter.py using ast.parse
- inspect only ast.Import and ast.ImportFrom nodes
- verify imported top-level modules against a prohibited module-name set
- construct prohibited names from harmless string pieces at runtime if needed
- do not inspect Call nodes for dangerous functions in this phase
- do not search source text for forbidden call expressions

Tests

Create zero-skip unittest coverage proving:

1. IntegrationCoordinator is actually used by MissionRepairAdapter
2. adapter does not own an independent retry lifecycle
3. initial success causes zero repair attempts
4. one repair succeeds
5. two repairs succeed
6. third repair succeeds
7. no fourth attempt
8. exhaustion after maximum attempts
9. protected Core block prevents generation
10. canonical-test block prevents generation
11. unavailable protection block
12. repository-safety block
13. security-policy block
14. provider-auth block
15. generation exception safe
16. apply exception safe
17. validation exception safe
18. validation exception may later recover
19. canonical Bearer redaction
20. generic secret removal
21. allowed paths preserved
22. denied paths preserved
23. inputs immutable
24. attempt numbers originate from coordinator plan
25. failure history preserved
26. deterministic equivalent behavior
27. module-local AST import safety
28. IntegrationCoordinator is the authoritative attempt limiter

Do not use pytest.
Do not use unittest.skip.

Acceptance

- Mission Adapter tests: zero failures/errors/skips
- Phase 2A IntegrationCoordinator tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection remains passing
- Portable Recovery remains passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
Do not modify agent/repair/integration.py.
