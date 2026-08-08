Mission: Self-Healing Phase 2B-1 Mission Adapter

Goal

Create the non-Core adapter used later by Mission Runner to perform bounded
self-healing of failed generated mission output.

This phase MUST NOT modify Mission Runner or any protected Core path.

Reuse the existing Phase 1 repair subsystem and Phase 2A IntegrationCoordinator.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

General

Use Python standard library only.

Use unittest only.

Do not use pytest or unittest.skip.

Do not modify any existing file.

Do not perform Git commit, Git push, branch switching, deployment, network calls,
or Core maintenance.

Architecture

Create a MissionRepairAdapter which bridges:

- IntegrationCoordinator
- validation callback
- repair-generation callback
- generated-file replacement callback

All side effects MUST be injected.

The adapter itself must not import Mission Runner.

The adapter itself must not directly invoke subprocess, Git, provider APIs,
network clients, deployment systems, or filesystem mutation.

Inputs

The adapter must accept safe mission-level context including:

- mission_name
- objective
- deliverables
- allowed_paths
- denied_paths
- max_attempts, default 3

Injected callbacks must include:

1. validate_callback
   Returns a Phase 2A ValidationResult-compatible value.

2. generate_repair_callback
   Receives a safe repair request and returns a repair-generation result.

3. apply_repair_callback
   Applies generated repair output and returns success/failure.

Repair Request

Create an immutable RepairRequest containing at least:

- mission_name
- attempt_number
- objective
- failure_category
- failure_summary
- allowed_paths
- denied_paths
- validation_required

Do not include raw unsanitized diagnostics.

Do not include secrets.

Do not include privileged Core-maintenance markers.

Repair Result

Create an immutable MissionRepairResult containing at least:

- success
- final_state
- attempts
- safe_summary
- repair_requests
- failure_history

Flow

Use IntegrationCoordinator as the bounded control loop.

For each repair attempt:

1. receive RepairPlan from IntegrationCoordinator
2. construct safe immutable RepairRequest
3. call generate_repair_callback
4. reject generation failure safely
5. call apply_repair_callback only after generation succeeds
6. return repair execution success/failure to IntegrationCoordinator
7. IntegrationCoordinator performs revalidation

Maximum Attempts

Default is 3.

No fourth repair generation callback may occur.

Blocked Conditions

The following must stop before generation or apply callback:

- protected-core-access
- canonical-recovery-test-access
- unavailable-core-protection
- repository-safety-bypass
- security-policy-bypass
- provider-authentication-intervention

Paths

Caller-provided denied paths must always be retained.

Allowed paths must not be expanded automatically.

Generated repair output must never authorize paths not already allowed by caller.

The adapter must not introduce protected Core paths.

Exception Safety

If generation callback raises Exception:

- convert to safe repair failure
- do not leak raw exception secrets
- allow coordinator policy to determine remaining bounded behavior

If apply callback raises Exception:

- convert to safe repair failure
- do not crash unexpectedly

Do not catch BaseException.

Determinism

Equivalent callback behavior and equivalent normalized inputs must produce
equivalent MissionRepairResult metadata.

Tests

Create comprehensive zero-skip unittest tests including at least:

1. initial validation succeeds, no repair generated
2. one failed validation then repair succeeds
3. two repair attempts then success
4. third repair attempt then success
5. no fourth repair attempt
6. exhaustion after three attempts
7. protected Core block calls neither generation nor apply
8. canonical-test block calls neither generation nor apply
9. unavailable-protection block
10. repository-safety block
11. security-policy block
12. provider-auth block
13. generation failure handled safely
14. generation exception handled safely
15. apply failure handled safely
16. apply exception handled safely
17. validation exception remains safe
18. repair request contains correct attempt number
19. repair request contains failure category
20. repair request contains safe failure summary
21. allowed paths preserved
22. denied paths preserved
23. allowed paths never expanded
24. denied paths never removed
25. input collections not mutated
26. repair history retained
27. failure history retained
28. deterministic equivalent result
29. secret-bearing validation data is not copied raw into repair request
30. no privileged maintenance marker emitted
31. no direct subprocess/Git/network behavior in adapter
32. max attempts remains bounded at 3

All tests must execute.

Acceptance

- new adapter tests: zero failures/errors/skips
- Phase 2A tests remain passing
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do NOT modify agent/ai/mission_runner.py in this phase.
