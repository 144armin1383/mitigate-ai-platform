Mission: Self-Healing Phase 2B-1.1 Adapter Coordinator Unification v5

Goal

Finalize MissionRepairAdapter against the REAL existing Phase 2A
IntegrationCoordinator API.

This version fixes exactly two remaining integration defects:

1. constraints must be passed to IntegrationCoordinator as a Mapping, not a tuple.
2. MissionRepairAdapter must sanitize translated IntegrationResult history so
   raw exception diagnostics can never leak through the mission-facing result.

Do not modify IntegrationCoordinator.
Do not modify Mission Runner.
Do not modify protected Core.

# Deliverables

- agent/repair/mission_adapter.py
- agent/tests/test_self_healing_mission_adapter.py

# End Deliverables

REAL COORDINATOR API

Construct:

IntegrationCoordinator(max_attempts=<integer>)

Call:

coordinator.run(
    objective,
    allowed_paths=...,
    denied_paths=...,
    constraints=<MAPPING>,
    validate_callback=<ZERO ARGUMENT CALLBACK>,
    repair_callback=<ONE RepairPlan ARGUMENT CALLBACK>,
    source=...,
)

Do not invent alternate APIs.

CONSTRAINTS CONTRACT

IntegrationCoordinator expects constraints to support:

constraints.items()

Therefore MissionRepairAdapter MUST pass a Mapping.

Acceptable safe forms include:

- dict
- MappingProxyType wrapping a dict

Do NOT convert constraints to:

- tuple
- list
- sequence of pairs

before passing them into IntegrationCoordinator.

Caller constraints must not be mutated.

Create a defensive dictionary snapshot:

safe_constraints = dict(constraints or {})

Pass that mapping to coordinator.run.

If mission context contains constraint-like values in another form, normalize them
to a dict before Coordinator invocation.

ZERO-ARG VALIDATION WRAPPER

IntegrationCoordinator calls validate_callback with zero arguments.

MissionRepairAdapter must wrap mission-level context-aware validation in a
zero-argument closure.

The wrapper may capture an immutable/deep-copied mission context.

REPAIR CALLBACK

IntegrationCoordinator calls repair_callback(plan).

The adapter must:

1. receive real RepairPlan
2. create immutable RepairRequest
3. copy plan.attempt_number exactly
4. call generation callback
5. if generation succeeds, call apply callback
6. return RepairExecutionResult-compatible success/failure

No retry loop in MissionRepairAdapter.

Coordinator remains the only retry authority.

MISSION RESULT SANITIZATION BOUNDARY

Treat IntegrationResult as trusted control-flow data but NOT automatically safe
for direct mission-facing serialization.

Before constructing MissionRepairResult, sanitize all string-bearing fields copied
from IntegrationResult, including:

- safe_summary
- FailureRecord.summary
- FailureRecord.diagnostic
- FailureRecord.source when appropriate
- any translated repair/failure text
- blocked-condition text if free-form

Do not mutate the IntegrationResult object.

Create safe translated snapshots.

RAW EXCEPTION LEAK PREVENTION

A validation Exception may contain arbitrary sensitive text even when it does not
have an obvious key=value prefix.

MissionRepairAdapter must never expose raw Exception diagnostic text directly in
MissionRepairResult.

For exception-derived failure records, prefer safe bounded canonical text such as:

validation exception

or a sanitized/redacted diagnostic.

The original raw exception value must not appear anywhere in:

- MissionRepairResult.safe_summary
- MissionRepairResult.failure_history
- MissionRepairResult repair metadata
- string representation of the mission-facing result

If failure.category == "validation-exception", do not blindly copy raw diagnostic.

Similarly protect generation/apply exception-derived failure data.

Do not rely solely on detecting words such as token/password/secret in the value.

The mission-facing boundary itself must guarantee that raw exception messages do
not leak.

BLOCKED CONDITION

When final_state == "blocked":

derive MissionRepairResult.blocked_condition from the relevant FailureRecord:

1. blocking_condition when it is a known string
2. otherwise category when category matches a known blocked category

Preserve exact category value.

CONSTRAINT/PATH IMMUTABILITY

Preserve:

- allowed_paths
- denied_paths
- constraints

without mutating caller data.

Allowed paths must never expand.
Denied paths must never shrink.

MAXIMUM ATTEMPTS

Default 3.

Pass max_attempts into IntegrationCoordinator constructor.

No fourth attempt.

TEST CONTRACT

Use the REAL IntegrationCoordinator.

Do not replace it with a fake API.

Mandatory regressions:

1. constraints passed to coordinator are Mapping-compatible
2. constraints input dict remains unchanged
3. no AttributeError involving constraints.items
4. initial success succeeds
5. one repair succeeds
6. two repairs succeed
7. third repair succeeds
8. no fourth repair
9. exhaustion after three
10. real plan.attempt_number copied
11. blocked condition preserved exactly for all six known categories
12. blocked flow performs zero generation
13. blocked flow performs zero apply
14. validation exception does not propagate
15. validation exception raw message is absent from MissionRepairResult
16. validation-exception diagnostic is safely replaced/redacted
17. later validation may recover successfully
18. generation exception raw message does not leak
19. apply exception raw message does not leak
20. allowed paths preserved
21. denied paths preserved
22. caller inputs immutable
23. IntegrationResult mappings correct
24. failure history retained in sanitized form
25. adapter contains no independent retry loop
26. real IntegrationCoordinator remains authoritative

TEST SOURCE SAFETY

Do not inspect sys.modules.

Do not include forbidden dangerous-call expressions literally in generated test
source.

Use AST Import / ImportFrom inspection only for module-local safety.

Use unittest only.
Do not use pytest.
Do not use unittest.skip.

Acceptance

- Mission Adapter tests: zero failures/errors/skips
- Phase 2A Integration tests unchanged and passing
- Phase 1 Self-Healing tests unchanged and passing
- Core Protection passing
- Portable Recovery passing
- full repository suite passing

Do not modify agent/repair/integration.py.
Do not modify agent/ai/mission_runner.py.
