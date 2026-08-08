Mission: Self-Healing Phase 2B-1.1 Adapter Coordinator Unification

Goal

Refactor the existing MissionRepairAdapter so that the existing Phase 2A
IntegrationCoordinator is the single bounded repair-loop authority.

Do not modify Mission Runner or protected Core.

The current MissionRepairAdapter must not maintain an independent competing
retry state machine.

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

MissionRepairAdapter must become an adapter around IntegrationCoordinator.

There must be one authoritative bounded repair loop.

Do not duplicate the three-attempt loop independently in MissionRepairAdapter.

MissionRepairAdapter Responsibilities

The adapter should only:

1. translate mission context into IntegrationCoordinator inputs
2. translate validation callback output into ValidationResult-compatible data
3. translate IntegrationCoordinator RepairPlan into immutable RepairRequest
4. invoke repair-generation callback
5. invoke repair-application callback
6. return a mission-oriented safe result

IntegrationCoordinator must own:

- initial validation
- attempt counting
- retry progression
- blocked state
- succeeded state
- exhausted state
- revalidation lifecycle
- maximum attempt enforcement

Maximum Attempts

Default maximum = 3.

No fourth repair generation may occur.

MissionRepairAdapter must not contain an independent retry loop that can diverge
from IntegrationCoordinator.

Repair Request

Preserve immutable RepairRequest with:

- mission_name
- attempt_number
- objective
- failure_category
- failure_summary
- allowed_paths
- denied_paths
- validation_required

Do not expose raw diagnostic values.

Security

Preserve existing redaction behavior.

Bearer authorization must sanitize canonically to:

Authorization: Bearer [REDACTED]

Generic credential tests must verify complete secret removal and must not require
irrelevant quote preservation.

Path Safety

Allowed paths must never be expanded.

Denied paths must never be removed.

Input collections must not be mutated.

Blocked Conditions

Use the existing IntegrationCoordinator blocked-condition contract.

Protected Core, canonical recovery test, unavailable Core protection,
repository safety, security policy, and provider authentication intervention
must terminate before repair generation.

Exception Handling

Ordinary callback Exceptions must be converted into safe failure results.

Do not catch BaseException.

Do not leak raw secret-bearing exception text.

Do not perform Git, subprocess, network, deployment, provider access, or direct
filesystem mutation in MissionRepairAdapter.

Compatibility

Preserve the public MissionRepairAdapter interface as far as practical.

Existing Phase 2B-1 behavior that already passed must remain passing.

Tests

Create zero-skip unittest coverage proving at least:

1. adapter actually instantiates or uses IntegrationCoordinator
2. no independent competing retry loop exists in adapter behavior
3. initial success performs zero repair attempts
4. one repair then success
5. two repairs then success
6. third repair then success
7. no fourth repair
8. exhaustion after three attempts
9. blocked Core performs zero repair callbacks
10. canonical-test block performs zero repair callbacks
11. unavailable-protection block
12. security-policy block
13. repository-safety block
14. provider-auth block
15. generation exception is safe
16. apply exception is safe
17. validation exception is safe
18. validation exception can later recover
19. Bearer canonical redaction preserved
20. generic secrets fully removed
21. allowed paths preserved
22. denied paths preserved
23. caller inputs immutable
24. attempt numbers come from coordinator plan
25. failure history preserved
26. deterministic equivalent behavior
27. adapter does not directly import prohibited process/network/Git modules
28. IntegrationCoordinator maximum-attempt policy is authoritative

Do not inspect sys.modules.

Do not use pytest.
Do not use unittest.skip.

Acceptance

- Mission Adapter tests: zero failures/errors/skips
- Phase 2A IntegrationCoordinator tests remain unchanged and passing
- Phase 1 Self-Healing tests remain unchanged and passing
- Core Protection remains passing
- Portable Recovery remains passing
- full repository unittest suite remains passing

Do not modify agent/ai/mission_runner.py.
Do not modify agent/repair/integration.py in this mission.
