Mission: Self-Healing Phase 2A Integration Coordinator

Goal

Create a standalone integration coordinator that connects validation failures,
FailureRecord, RepairLoop, repair execution callbacks, and revalidation.

This phase MUST NOT modify Mission Runner or any protected Core path.

Do NOT modify:

- agent/ai/
- agent/core/
- agent/runtime/
- agent/api/
- agent/orchestrator/
- agent/autonomy/
- agent/memory/
- agent/bootstrap/
- agent/policies/
- agent/services/
- agent/providers/
- agent/deploy/
- agent/tests/test_portable_agent_recovery.py
- agent/tests/test_core_protection.py
- agent/tests/test_self_healing_repair_loop.py

# Deliverables

- agent/repair/integration.py
- agent/tests/test_self_healing_phase2_integration.py

# End Deliverables

General

Use Python standard library only.

Use unittest only.

Do not use pytest.

Do not use unittest.skip.

Do not execute Git, shell commands, subprocesses, network operations, deployment,
or filesystem mutation inside the coordinator.

All side-effectful behavior must be injected as callables.

Existing Phase 1 files should be reused, not rewritten.

Integration Coordinator

Implement a deterministic coordinator that uses:

- FailureRecord
- RepairLoop
- RepairPlan

The coordinator must accept injected callables for:

- validation
- repair execution

The coordinator itself must not know how AI generation, Git, subprocess execution,
or deployment works.

Lifecycle

Support this flow:

initial validation
→ success: return succeeded immediately

OR

initial validation failure
→ create safe FailureRecord
→ feed RepairLoop
→ determine blocked/retryable status
→ create RepairPlan
→ invoke injected repair callback
→ invoke injected validation callback again
→ repeat within bounded attempt limit
→ succeeded / exhausted / blocked

Default maximum repair attempts must remain 3.

No fourth repair attempt may occur.

Validation Result Contract

Define a small immutable validation-result structure with safe fields such as:

- success
- category
- summary
- diagnostic
- return_code
- source
- blocking_condition

Raw unsafe exception objects must not be stored.

Repair Execution Result Contract

Define a small immutable repair-execution result such as:

- success
- summary

The coordinator must react safely if repair execution reports failure.

Blocked Conditions

Immediately stop without calling the repair callback when failure represents:

- protected Core access
- canonical recovery test access
- unavailable Core protection
- repository safety bypass
- security policy bypass
- provider authentication intervention

Map blocking conditions into the existing RepairLoop blocking constraints.

Core Safety

Never generate or request privileged Core-maintenance authorization.

Never modify allowed_paths to include a denied Core path.

Never remove denied_paths supplied by the caller.

Never automatically retry a blocked failure.

Determinism

Given equivalent validation results, objectives, constraints, allowed paths,
denied paths, and callback results, the coordinator result must be deterministic.

Result

Return an immutable integration result containing at least:

- success
- final_state
- attempts
- repair_plans
- failure_history
- safe_summary

Do not include raw secrets or raw unsanitized output.

Exception Handling

If injected validation or repair callbacks raise ordinary exceptions:

- convert them into safe failure state
- do not expose raw secret-bearing exception details
- do not crash the coordinator unexpectedly

Do NOT catch BaseException.

Tests

Create comprehensive zero-skip unittest coverage, including at least:

1. validation succeeds first try
2. validation fails then one repair succeeds
3. validation fails twice then succeeds
4. validation succeeds on third repair attempt
5. fourth repair attempt never occurs
6. attempt exhaustion
7. protected-Core block before repair callback
8. canonical-test block before repair callback
9. unavailable-protection block before repair callback
10. security-policy block
11. repository-safety block
12. authentication-intervention block
13. repair callback failure handled safely
14. validation callback exception handled safely
15. repair callback exception handled safely
16. repair plan history retained
17. failure history retained
18. attempts count accurate
19. allowed_paths preserved
20. denied_paths preserved
21. input collections not mutated
22. deterministic equivalent execution result
23. secrets in validation diagnostics are sanitized
24. no privileged maintenance marker output
25. no subprocess/network/Git behavior in coordinator
26. existing RepairLoop maximum attempts respected
27. no repair callback when initial validation succeeds
28. blocked state is terminal
29. succeeded state is terminal
30. exhausted state is terminal

All tests in this new file must execute.

Acceptance

- Phase 2 integration tests: zero failures/errors/skips
- Phase 1 Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify Mission Runner in this phase.
