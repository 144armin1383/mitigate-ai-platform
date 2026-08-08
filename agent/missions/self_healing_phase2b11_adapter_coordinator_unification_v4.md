Mission: Self-Healing Phase 2B-1.1 Adapter Coordinator Unification v4

Goal

Implement MissionRepairAdapter as a thin, correct translation layer around the
REAL existing Phase 2A IntegrationCoordinator API.

Do not modify IntegrationCoordinator.
Do not modify Mission Runner.
Do not modify protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

Authoritative Existing API

IntegrationCoordinator is constructed as:

IntegrationCoordinator(max_attempts=<integer>)

Its run method is:

coordinator.run(
    objective,
    allowed_paths=...,
    denied_paths=...,
    constraints=...,
    validate_callback=<ZERO ARGUMENT CALLBACK>,
    repair_callback=<ONE RepairPlan ARGUMENT CALLBACK>,
    source=...,
)

Do not invent any other Coordinator API.

CRITICAL CALLBACK ADAPTATION

The Mission-level validation callback may need mission context.

IntegrationCoordinator itself calls validate_callback with ZERO arguments.

Therefore MissionRepairAdapter MUST create a zero-argument closure.

Conceptually:

def coordinator_validate():
    return mission_validate_callback(safe_mission_context)

and pass coordinator_validate as validate_callback.

Do NOT pass a context-accepting callback directly to IntegrationCoordinator.

Repair Callback

IntegrationCoordinator calls:

repair_callback(plan)

with one real Phase 2A RepairPlan.

MissionRepairAdapter MUST create one repair closure that:

1. receives the real RepairPlan
2. constructs immutable RepairRequest from that plan
3. calls mission-level generate callback
4. if generation fails, returns RepairExecutionResult(success=False, ...)
5. if generation succeeds, calls mission-level apply callback
6. returns RepairExecutionResult reflecting application success/failure

There must be no retry loop inside MissionRepairAdapter.

IntegrationCoordinator is the only attempt/retry authority.

RepairRequest

Use actual RepairPlan fields:

- attempt_number
- failure_category
- failure_summary
- objective
- constraints
- allowed_paths
- denied_paths

Also preserve:

- mission_name
- validation_required

Attempt number MUST come from plan.attempt_number.

Mission Result

Create an immutable MissionRepairResult that explicitly contains:

- succeeded: bool
- final_state: str
- attempts: int
- safe_summary: str
- blocked_condition: optional string
- repair_requests: immutable sequence
- failure_history: immutable sequence
- allowed_paths: immutable sequence
- denied_paths: immutable sequence

Translation Rules

IntegrationResult.success -> MissionRepairResult.succeeded

IntegrationResult.final_state -> MissionRepairResult.final_state

IntegrationResult.attempts -> MissionRepairResult.attempts

IntegrationResult.safe_summary -> MissionRepairResult.safe_summary

IntegrationResult.failure_history -> MissionRepairResult.failure_history

Blocked Condition Translation

If final_state == "blocked":

inspect the latest relevant FailureRecord from IntegrationResult.failure_history.

MissionRepairResult.blocked_condition must preserve the actual blocking condition
or blocked category such as:

- protected-core-access
- canonical-recovery-test-access
- unavailable-core-protection
- repository-safety-bypass
- security-policy-bypass
- provider-authentication-intervention

Do not return None when the Coordinator has blocked for a known condition.

Validation Exception Contract

The real IntegrationCoordinator catches ordinary validation Exceptions and converts
them into sanitized ValidationResult / FailureRecord data.

Therefore tests MUST NOT expect RuntimeError or another ordinary validation
Exception to propagate.

Tests MUST verify instead:

- adapter does not crash
- result records safe validation failure
- raw secret is absent
- bounded repair may continue
- later successful validation may produce succeeded=True
- continued failures eventually produce exhausted

Do not catch BaseException in the adapter.

Initial Success

When adapted Mission validation succeeds on the first zero-argument Coordinator
validation call:

- succeeded=True
- final_state="succeeded"
- attempts=0
- generation callback count=0
- apply callback count=0

Retry Semantics

Use only Coordinator attempt behavior.

Prove:

- success after first repair
- success after second repair
- success after third repair
- exhaustion after three failed repairs
- never a fourth repair generation

Blocking

Validation callback must return a real ValidationResult with category and/or
blocking_condition matching Phase 2A.

When blocked:

- final_state="blocked"
- succeeded=False
- attempts=0
- blocked_condition preserved exactly
- generate callback never called
- apply callback never called

Path Safety

Pass allowed_paths and denied_paths directly into Coordinator as defensive
immutable snapshots.

Never expand allowed_paths.

Never remove denied_paths.

Do not mutate caller input.

Security

Reuse Phase 2A sanitization behavior.

Do not expose raw exception diagnostics in MissionRepairResult.

Bearer and credential secrets must not leak.

Side Effects

MissionRepairAdapter must not directly execute:

- Git
- subprocess/process commands
- shell commands
- network operations
- deployments
- providers
- filesystem mutation

All real side effects are injected callbacks.

Testing Contract

Use the REAL IntegrationCoordinator implementation.

Do NOT mock or replace IntegrationCoordinator with a fake API.

You may mock only mission-level callbacks:

- validation
- generation
- apply

Mandatory tests:

1. real IntegrationCoordinator API smoke test
2. zero-arg validation wrapper works with context-aware mission callback
3. initial validation success => succeeded
4. initial validation success => zero attempts
5. one repair success
6. two repairs success
7. third repair success
8. no fourth repair
9. exhaustion after three
10. protected-core blocking condition preserved exactly
11. canonical recovery blocking condition preserved exactly
12. unavailable protection condition preserved
13. repository safety condition preserved
14. security policy condition preserved
15. provider authentication condition preserved
16. blocked condition performs zero generation
17. blocked condition performs zero apply
18. real RepairPlan.attempt_number copied to RepairRequest
19. generation failure returned as RepairExecutionResult failure
20. apply failure returned as RepairExecutionResult failure
21. validation exception does NOT propagate
22. validation exception recorded safely
23. later validation recovery can succeed
24. continued validation failure exhausts
25. IntegrationResult.success maps to succeeded
26. final_state maps correctly
27. attempts maps correctly
28. failure history retained
29. allowed paths preserved
30. denied paths preserved
31. caller inputs immutable
32. no independent adapter retry loop
33. module-local import safety

TEST SAFETY

Do not inspect sys.modules.

Do not include forbidden dangerous-call literal expressions in test source.

Use AST Import / ImportFrom checks only when checking module-local imports.

Use unittest only.
Do not use pytest.
Do not use unittest.skip.

Acceptance

- Mission Adapter tests zero failures/errors/skips
- tests exercise REAL IntegrationCoordinator
- Phase 2A tests unchanged and passing
- Phase 1 Self-Healing tests unchanged and passing
- Core Protection passing
- Portable Recovery passing
- full repository suite passing

Do not modify agent/repair/integration.py.
Do not modify agent/ai/mission_runner.py.
