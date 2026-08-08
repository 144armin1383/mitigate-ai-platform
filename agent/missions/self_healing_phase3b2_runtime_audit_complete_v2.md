Mission: Self-Healing Phase 3B-2 Complete Runtime Audit Integration v2

CORE_MAINTENANCE_APPROVED

Goal

Complete runtime integration of the existing Self-Healing observability and
audit system in ONE phase.

When Mission Runner actually invokes Self-Healing, create a sanitized immutable
audit record from the already-produced MissionRepairAdapter result.

Audit must remain passive and must NEVER affect mission success, repair
decisions, retry behavior, Core Protection, validation, provider execution,
Git operations, or recovery behavior.

No persistence is required in this phase.

# Deliverables

- agent/repair/runtime_audit.py
- agent/ai/mission_runner.py
- agent/tests/test_self_healing_runtime_audit.py
- agent/tests/test_mission_runner_self_healing_audit.py

# End Deliverables

EXISTING ARCHITECTURE — DO NOT REPLACE

Current runtime path is:

Mission Runner
→ validate_with_self_healing
→ MissionRepairAdapter
→ IntegrationCoordinator
→ repair generation/apply/revalidation
→ final mission result

Existing audit path:

MissionRepairAdapter-style result
→ build_audit_from_mission_result
→ SelfHealingAuditRecord

Phase 3B-2 only connects these existing components.

Do NOT introduce another retry loop.
Do NOT introduce another repair engine.
Do NOT redesign Phase 3A or Phase 3B-1.

RUNTIME AUDIT MODULE

Create:

agent/repair/runtime_audit.py

Public API:

- RuntimeAuditCaptureResult
- capture_self_healing_audit

RuntimeAuditCaptureResult must be:

@dataclass(frozen=True)

and contain:

- captured: bool
- record: Optional[SelfHealingAuditRecord]
- safe_error_code: Optional[str]

Successful capture:

captured == True
record is SelfHealingAuditRecord
safe_error_code is None

Failed capture:

captured == False
record is None
safe_error_code == "AUDIT_CAPTURE_FAILED"

Never return:
- exception repr
- raw exception messages
- traceback
- provider data
- test logs
- credentials

CAPTURE API

capture_self_healing_audit must accept:

- mission_name
- repair_id
- mission_result
- failure_category
- safe_failure_summary
- allowed_paths
- denied_paths
- started_at
- completed_at

It must delegate translation directly to:

build_audit_from_mission_result(...)

from:

agent/repair/audit_integration.py

or package-relative equivalent.

Do not duplicate the translator.

NON-FATAL GUARANTEE

Audit capture is passive.

capture_self_healing_audit may catch ordinary Exception raised by audit
translation.

If capture fails:

return RuntimeAuditCaptureResult(
    captured=False,
    record=None,
    safe_error_code="AUDIT_CAPTURE_FAILED",
)

Do NOT propagate the audit exception.

Do NOT retry audit capture.

Do NOT change the repair result.

Do NOT include str(exc).

Do NOT catch BaseException.

NO SIDE EFFECTS

runtime_audit.py must NOT:

- write files
- read files
- create directories
- call Git
- execute subprocess
- use network
- call providers
- invoke repair execution
- invoke validation
- retry anything
- read environment variables

MISSION RUNNER INTEGRATION

Modify only the existing Self-Healing path in:

agent/ai/mission_runner.py

Do not redesign run_mission.

Do not modify normal successful mission behavior.

If initial validation passes without Self-Healing:
- do not create a repair audit
- do not call runtime audit capture

If Self-Healing is invoked:
- capture the returned MissionRepairAdapter result
- attempt passive audit capture exactly once after adapter.run returns
- audit capture happens before translating failed repair status into MissionError
- audit failure must NOT replace or alter the original Self-Healing result

The existing behavior must remain:

status == succeeded:
    continue successful mission flow

status == blocked:
    raise MissionError("SELF_HEALING_BLOCKED")

otherwise:
    raise MissionError("SELF_HEALING_EXHAUSTED")

Audit must not modify these semantics.

AUDIT RECORD EXPOSURE

Because this phase has NO persistence, retain the latest runtime audit result in
a minimal module-level non-authoritative observation slot in Mission Runner:

LAST_SELF_HEALING_AUDIT

Rules:

- default value None
- set only when Self-Healing actually runs
- contains RuntimeAuditCaptureResult
- reset to None at the beginning of each run_mission invocation
- never used to control mission behavior
- never used by Core Protection
- never used for retry decisions
- never committed or written to filesystem

This exists only for observability/testing until a later persistence/API phase.

REPAIR ID

Do NOT invent or add a new cryptographic repair-ID algorithm in this phase.

For runtime audit correlation, use a deterministic non-secret correlation value
derived only from existing safe runtime identifiers already available in
Mission Runner.

Use:

repair_id = f"{mission_path.stem}:{failure_category}"

This value is an audit correlation identifier only.

Do NOT modify:
- RepairLoop ID generation
- IntegrationCoordinator
- MissionRepairAdapter
- Phase 1 deterministic repair IDs

Do not claim this audit correlation identifier is an internal RepairPlan ID.

No random UUID.
No current time in repair_id.
No secret-bearing material.

TIMESTAMPS

Runtime audit requires started_at and completed_at.

Mission Runner may capture UTC timestamps specifically for passive observability.

Use timezone-aware UTC datetime values.

Do not use timestamps for:
- repair decisions
- retry limits
- IDs
- validation
- Git
- branching

Audit timestamps must have no behavioral effect.

Capture started_at immediately before adapter.run.

Capture completed_at immediately after adapter.run returns.

If adapter.run raises unexpectedly, preserve existing exception behavior;
do not add new recovery semantics.

IMPORT COMPATIBILITY

Mission Runner is executed in runtime context as:

python -m ai.mission_runner

and tests may import package modules differently.

Use the same narrow runtime-compatible import pattern already used for
MissionRepairAdapter.

Expose runtime audit capture at module scope so tests can patch it.

Do not catch broad import exceptions.

CORE SAFETY

Preserve all existing:

- Core Lock validation
- protected path checks
- canonical test protection
- forbidden generated content scanning
- deliverable allowlist
- repository clean requirement
- branch safety
- atomic writes
- commit/push behavior
- failed mission recovery

Audit must not weaken or bypass any safety boundary.

NO NEW RETRY LOOP

Mission Runner must contain no local audit retry loop and no new repair retry
loop.

Exactly one repair retry authority remains:

MissionRepairAdapter
→ IntegrationCoordinator

Audit capture runs at most once per Self-Healing invocation.

SECURITY

Never pass raw validation exception text into audit.

Use the already-safe values:

failure_category
safe_summary

Do not use:
- CalledProcessError output
- stderr
- stdout
- traceback
- raw provider response

Audit integration and Phase 3A sanitizer remain responsible for final field
sanitization.

Do not embed repository-forbidden complete literals in generated source or tests.

Construct synthetic credential/private-key-like test values dynamically where
necessary.

TESTS — RUNTIME AUDIT

Use unittest only.
No pytest.
Zero skips.

agent/tests/test_self_healing_runtime_audit.py must cover at least:

1. successful capture
2. captured record is SelfHealingAuditRecord
3. zero-attempt capture
4. one-attempt capture
5. exhausted capture
6. blocked capture
7. failed capture where structurally supported
8. repair_id preserved
9. allowed paths preserved
10. denied paths preserved
11. history preserved
12. caller mission_result not mutated
13. caller paths not mutated
14. Bearer secret absent
15. password secret absent
16. translation exception becomes AUDIT_CAPTURE_FAILED
17. translation exception does not propagate
18. raw exception text absent
19. result immutable
20. deterministic equivalent capture
21. no filesystem side effects
22. no subprocess/network/provider imports
23. no retry loop
24. no repair execution invoked

TESTS — MISSION RUNNER HOOK

agent/tests/test_mission_runner_self_healing_audit.py must cover at least:

1. normal validation success does not capture audit
2. Self-Healing success captures exactly once
3. Self-Healing blocked captures exactly once
4. Self-Healing exhausted captures exactly once
5. audit capture failure does not change successful repair outcome
6. audit capture failure does not change blocked outcome
7. audit capture failure does not change exhausted outcome
8. LAST_SELF_HEALING_AUDIT defaults to None
9. LAST_SELF_HEALING_AUDIT resets per run
10. LAST_SELF_HEALING_AUDIT populated after repair
11. repair result is not mutated by audit capture
12. safe failure category passed to audit
13. safe summary passed to audit
14. allowed paths passed unchanged
15. denied paths passed unchanged
16. audit capture called only after adapter.run
17. no audit capture before Self-Healing
18. audit capture exactly once
19. no audit retry loop
20. no additional repair retry loop
21. existing SELF_HEALING_BLOCKED semantics preserved
22. existing SELF_HEALING_EXHAUSTED semantics preserved
23. successful repaired mission still follows commit path
24. failed repaired mission still follows recovery path
25. Core/security terminal failures still bypass Self-Healing audit
26. module-level audit result is observational only
27. no raw exception/secret passed to capture helper

REGRESSION ACCEPTANCE

Must remain green:

- Phase 1 Self-Healing tests
- Phase 2A IntegrationCoordinator tests
- MissionRepairAdapter tests
- Mission Runner Self-Healing tests
- Phase 3A observability tests
- Phase 3B-1 audit integration tests
- Core Protection tests
- Portable Recovery tests
- full repository unittest suite

Full repository result must have:
- zero failures
- zero errors

Do not modify:

- agent/repair/observability.py
- agent/repair/audit_integration.py
- agent/repair/integration.py
- agent/repair/mission_adapter.py
- agent/repair/repair_loop.py
- agent/repair/failure_capture.py
- agent/policies/core_protection.py
- agent/policies/core_lock_manifest.json

MISSION RUNNER PRESERVATION CONTRACT — CRITICAL

The previous attempt failed because generated repairs replaced too much of
agent/ai/mission_runner.py and temporarily broke existing module-level API
compatibility.

This version MUST modify mission_runner.py as a MINIMAL PATCH ONLY.

The existing mission_runner.py on main is authoritative.

Do NOT rewrite the file from scratch.
Do NOT regenerate unrelated functions.
Do NOT reorder existing code unnecessarily.
Do NOT remove or rename existing symbols.

The following existing module-level symbols MUST remain present and compatible:

- AGENT_ROOT
- REPOSITORY_ROOT
- MISSIONS_ROOT
- MissionError
- run_git
- validate_generated_files
- validate_with_self_healing
- run_mission

In particular, preserve exactly the existing repository root relationship:

REPOSITORY_ROOT = AGENT_ROOT.parent

Existing tests directly access:

ai.mission_runner.REPOSITORY_ROOT

Therefore REPOSITORY_ROOT MUST remain available at module scope after every
generated or repaired version.

SELF-HEALING HOOK PRESERVATION

Preserve the existing Phase 2B-2 implementation and behavior.

Do NOT replace validate_with_self_healing.

Only add the minimal audit capture statements around the EXISTING:

repair_result = adapter.run(...)

flow.

The intended change is conceptually:

1. existing validation fails
2. existing callbacks are created
3. existing MissionRepairAdapter is created
4. started_at captured
5. existing adapter.run executes unchanged
6. completed_at captured
7. passive audit capture called exactly once
8. existing status handling executes unchanged

Do not recreate the self-healing implementation.

RUNTIME IMPORT REQUIREMENT

Mission Runner currently runs successfully as:

cd agent
python -m ai.mission_runner

Preserve this runtime import behavior.

Do not introduce imports that make:

import ai.mission_runner

fail.

Use the same narrow import compatibility style already present in the existing
file.

UNITTEST ONLY — ABSOLUTE REQUIREMENT

All generated tests MUST use Python standard-library unittest only.

Forbidden in generated tests:

- import pytest
- from pytest ...
- pytest decorators
- pytest fixtures
- pytest.raises
- pytest monkeypatch

Use:

- unittest.TestCase
- unittest.mock.patch
- self.assertRaises
- standard library mocks

Do not add pytest as a dependency.

EXISTING MANUAL SELF-HEALING TESTS ARE CANONICAL REGRESSION TESTS

These existing tests MUST continue to pass unchanged:

agent/tests/test_mission_runner_self_healing_manual.py

Specifically preserve compatibility for:

- test_successful_repair_path
- test_core_path_locked_is_terminal

Do NOT modify this existing test file.

MINIMAL DIFF REQUIREMENT

Changes to agent/ai/mission_runner.py must be narrowly limited to:

- runtime audit imports
- LAST_SELF_HEALING_AUDIT observation slot
- timestamps surrounding the existing adapter.run call
- exactly one capture_self_healing_audit call
- resetting LAST_SELF_HEALING_AUDIT at the beginning of run_mission

No unrelated production behavior may change.

Do not modify:

- Git helpers
- branch creation
- repository root constants
- mission loading
- deliverable extraction
- generated file validation
- Core Protection
- recovery behavior
- provider checks
- generation plan construction
- write_generated_files
- commit_and_push
- CLI behavior

SELF-HEALING REPAIR INSTRUCTION

If validation of the generated Phase 3B-2 deliverables fails, repair generation
must preserve this same minimal-diff contract.

A repair must not replace mission_runner.py wholesale.

A repair must not remove any existing public/module-level symbol simply because
the new Phase 3B-2 tests do not reference it.

REGRESSION GATE

Before Mission completion, all of the following must pass together:

python -m unittest discover -s agent/tests -p "test_*.py" -v

There must be:

- zero failures
- zero errors

Existing test_mission_runner_self_healing_manual tests are mandatory and must
not be skipped, modified, deleted, renamed, or bypassed.

All previous Phase 1, Phase 2, Phase 3A, and Phase 3B-1 tests must remain green.

SOURCE SAFETY

Generated source must remain compatible with Mission Runner forbidden-content
validation.

Do not embed forbidden complete secret/private-key markers in source or tests.

FINAL RULE

Implement the complete Phase 3B-2 runtime audit integration in this single
mission.

Do not split the work into another phase.
