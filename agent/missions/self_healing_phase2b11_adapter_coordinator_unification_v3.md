Mission: Self-Healing Phase 2B-1.1 Adapter Coordinator Unification v3

Goal

Refactor MissionRepairAdapter to use the EXISTING IntegrationCoordinator API
exactly as implemented in agent/repair/integration.py.

Do not modify IntegrationCoordinator.
Do not modify Mission Runner.
Do not modify protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

Critical API Contract

Use the actual existing IntegrationCoordinator interface.

Construction:

IntegrationCoordinator(max_attempts=<bounded integer>)

Execution:

coordinator.run(
    objective,
    allowed_paths=...,
    denied_paths=...,
    constraints=...,
    validate_callback=...,
    repair_callback=...,
    source=...,
)

Do NOT invent alternate coordinator APIs.

Do NOT call coordinator.run with:

- context
- validate
- generate
- apply
- max_attempts

Do NOT probe hypothetical coordinate(), execute(), or alternate interfaces.

Do NOT use hasattr-based compatibility guessing.

The adapter must target the actual current Phase 2A contract only.

Single Repair Loop

IntegrationCoordinator is the only retry-loop authority.

MissionRepairAdapter must contain no independent attempt loop.

IntegrationCoordinator owns:

- initial validation
- attempts
- retries
- blocking
- revalidation
- succeeded state
- exhausted state
- maximum attempts

Adapter Responsibilities

MissionRepairAdapter should:

1. accept mission-level context
2. construct IntegrationCoordinator(max_attempts=...)
3. provide validate_callback compatible with coordinator.run
4. provide ONE repair_callback compatible with RepairPlan
5. inside repair_callback:
   - convert RepairPlan to immutable RepairRequest
   - call injected generation callback
   - if generation fails, return safe RepairExecutionResult-compatible failure
   - if generation succeeds, call injected apply callback
   - return success/failure to coordinator
6. translate IntegrationResult into mission-facing immutable result

RepairRequest

RepairRequest must be derived from the actual Phase 2A RepairPlan fields:

- attempt_number
- failure_category
- objective
- constraints
- allowed_paths
- denied_paths
- validation_required

Preserve mission_name separately if needed.

Do not expect a RepairPlan field named only "attempt".
The authoritative field is attempt_number.

Validation

The injected validation callback must return a value accepted by
IntegrationCoordinator, preferably ValidationResult.

Blocked conditions must use the exact Phase 2A category/condition values:

- protected-core-access
- canonical-recovery-test-access
- unavailable-core-protection
- repository-safety-bypass
- security-policy-bypass
- provider-authentication-intervention

Maximum Attempts

Default 3.

Pass max attempts into IntegrationCoordinator constructor.

No fourth attempt.

Security

No raw secrets in requests or returned summaries.

Preserve safe Bearer semantics.

Do not catch BaseException.

No direct Git, process execution, shell execution, network calls,
provider access, deployment, or filesystem mutation.

Tests

Tests MUST use the REAL IntegrationCoordinator from agent/repair/integration.py
for integration-contract tests.

Do not replace IntegrationCoordinator with a fake that exposes a different API.

Mocks may be used only for injected:

- validation callback
- generation callback
- apply callback

Mandatory tests:

1. actual IntegrationCoordinator.run API works through adapter
2. no TypeError from invented kwargs
3. adapter contains no independent retry loop
4. initial validation success = zero repair attempts
5. one repair success
6. two repair success
7. third repair success
8. no fourth attempt
9. exhaustion after three
10. blocked Core causes zero generation
11. canonical-test block causes zero generation
12. unavailable-protection block
13. repository-safety block
14. security-policy block
15. provider-auth block
16. RepairRequest attempt_number comes from real RepairPlan.attempt_number
17. generation failure becomes repair execution failure
18. apply failure becomes repair execution failure
19. validation exception remains safe
20. later validation may recover
21. paths preserved
22. inputs immutable
23. real IntegrationResult is translated correctly
24. full failure history retained safely
25. deterministic behavior
26. adapter-local import safety

Do not inspect sys.modules.
Do not use pytest.
Do not use unittest.skip.
Do not include forbidden dangerous-call literals in generated tests.

Acceptance

- Mission Adapter tests: zero failures/errors/skips
- tests must exercise actual IntegrationCoordinator API
- Phase 2A tests unchanged and passing
- Phase 1 Self-Healing tests unchanged and passing
- Core Protection passing
- Portable Recovery passing
- full repository suite passing

Do not modify agent/repair/integration.py.
Do not modify agent/ai/mission_runner.py.
