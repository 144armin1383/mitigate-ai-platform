Mission: Self-Healing Phase 2B-1.1 Adapter Coordinator Unification v6

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


PYTHON SYNTAX REGRESSION REQUIREMENT

The previous generation failed Python compilation because an assignment near
the generation callback was emitted with invalid syntax equivalent to a
backslash immediately before an equals sign.

This defect must not recur.

All assignment statements must use ordinary valid Python syntax.

For example, when invoking the injected generation callback, use a valid form
such as:

generated = generation_callback(request)

Never emit a backslash before an assignment operator.

Never emit malformed assignment syntax.

Both generated deliverables must compile successfully with py_compile before
any unittest execution.

CALLBACK IMPLEMENTATION REQUIREMENT

Inside the coordinator repair callback:

- receive the real RepairPlan
- create RepairRequest
- invoke generation_callback exactly through valid Python
- normalize generation failure safely
- invoke apply_callback only after generation succeeds
- return RepairExecutionResult-compatible output

Do not introduce a second retry loop.

All constraints, zero-argument validation wrapping, IntegrationResult
translation, blocked-condition preservation, and mission-facing sanitization
requirements from v5 remain mandatory.

FINAL PRODUCTION CONTRACT CORRECTIONS

This v7 supersedes v6 for three mandatory production-contract corrections.

1. REPAIR CALLBACK RETURN TYPE

The existing IntegrationCoordinator accepts repair callback results through its
real repair-result coercion contract.

MissionRepairAdapter MUST return a supported type.

Prefer the real Phase 2A:

RepairExecutionResult(
    success=<bool>,
    summary=<safe string>,
)

Do NOT return SimpleNamespace or another arbitrary object with a success
attribute.

Generation failure, generation exception, apply failure, and apply exception
must all return a real RepairExecutionResult-compatible value.

A successful generation plus successful apply MUST be interpreted by the real
IntegrationCoordinator as repair success.

Tests MUST use the real IntegrationCoordinator and prove that successful repair
execution is actually recognized as success.

2. NO RAW INTEGRATION RESULT IN MISSION-FACING RESULT

MissionRepairResult is a security boundary.

Do NOT store:

raw=integration_result

or any direct reference to the original unsanitized IntegrationResult.

MissionRepairResult must contain sanitized immutable snapshots only.

It must include at least:

- succeeded: bool
- final_state: str
- attempts: int
- safe_summary: str
- blocked_condition: optional string
- failure_history: immutable sanitized sequence
- repair_requests: immutable sequence where applicable
- allowed_paths: immutable sequence
- denied_paths: immutable sequence

IntegrationResult.success MUST map directly to MissionRepairResult.succeeded.

The repr/string form of MissionRepairResult must never expose raw diagnostic
content through a hidden raw object reference.

3. VALIDATION CALLBACK SIGNATURE ADAPTATION

Do NOT use execution-time:

try:
    callback(context)
except TypeError:
    callback()

to detect callback arity.

That pattern incorrectly treats a real TypeError raised INSIDE validation logic
as a signature mismatch and can execute validation twice.

Determine the callback calling convention BEFORE execution.

Use a safe standard-library signature inspection approach such as
inspect.signature where possible.

Then create exactly one zero-argument coordinator validation closure that calls
the mission validation callback exactly once per coordinator validation event.

Requirements:

- a context-aware callback receives the captured mission context
- a zero-argument callback receives no arguments
- an internal TypeError raised by validation is allowed to reach
  IntegrationCoordinator once
- IntegrationCoordinator then converts it into its safe validation-exception
  failure
- validation callback must never be executed twice because it raised TypeError

REGRESSION TESTS

Add mandatory tests using the REAL IntegrationCoordinator:

1. successful RepairExecutionResult is accepted as repair success
2. no SimpleNamespace repair-result compatibility dependency exists
3. MissionRepairResult.succeeded maps IntegrationResult.success
4. MissionRepairResult contains no raw IntegrationResult reference
5. repr(MissionRepairResult) cannot reveal a raw validation secret
6. context-aware validation callback called exactly once per validation event
7. zero-argument validation callback called exactly once per validation event
8. validation callback that internally raises TypeError is NOT retried with a
   different signature
9. internal TypeError becomes safe validation-exception history
10. successful one-repair flow works through the real Coordinator
11. successful two-repair flow works through the real Coordinator
12. successful third-repair flow works through the real Coordinator
13. no fourth repair attempt
14. all prior constraints Mapping, blocking-condition, sanitization, path
    immutability, and Core-safety regressions remain passing

Do not modify agent/repair/integration.py.
Do not modify agent/ai/mission_runner.py.
