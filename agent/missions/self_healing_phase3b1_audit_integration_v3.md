Mission: Self-Healing Phase 3B-1 Audit Integration Adapter v3

Goal

Create exactly one passive translator from the EXISTING MissionRepairAdapter
result structure into the EXISTING Phase 3A observability model.

Do not invent a generic audit/event framework.

# Deliverables

- agent/repair/audit_integration.py
- agent/tests/test_self_healing_audit_integration.py

# End Deliverables

EXACT PUBLIC API

agent/repair/audit_integration.py MUST expose only the Phase 3B-1 integration
API:

- SelfHealingAuditIntegration
- build_audit_from_mission_result

Do NOT create unrelated public APIs such as:

- normalize_event
- merge_audit_streams
- summarize_events
- integrate_audit
- audit stream merging
- deduplication utilities
- generic event normalization
- generic severity models

This module is specifically and only for Self-Healing repair audit translation.

EXISTING PHASE 3A API — USE EXACTLY

Import from:

agent.repair.observability

or package-relative equivalent:

from .observability import (
    RepairAttemptEvent,
    SelfHealingAuditRecord,
    SelfHealingAuditBuilder,
)

RepairAttemptEvent constructor requires:

RepairAttemptEvent(
    mission_name=...,
    repair_id=...,
    attempt_number=...,
    failure_category=...,
    safe_failure_summary=...,
    allowed_paths=...,
    denied_paths=...,
    generation_status=...,
    application_status=...,
    validation_status=...,
    started_at=...,
    completed_at=...,
)

IMPORTANT:

The field name is:

safe_failure_summary

NOT:

safe_summary

mission_name and repair_id are mandatory on EVERY RepairAttemptEvent.

failure_category and safe_failure_summary are required constructor arguments
even when their values are None.

SelfHealingAuditBuilder constructor requires EXACTLY:

SelfHealingAuditBuilder(
    mission_name=...,
    repair_id=...,
    initial_failure_category=...,
    initial_safe_summary=...,
    started_at=...,
)

initial_failure_category and initial_safe_summary MUST be passed explicitly,
even when None.

Do NOT pass allowed_paths or denied_paths into SelfHealingAuditBuilder because
the existing Phase 3A builder does not accept them.

Add attempts using:

builder.add_attempt(event)

Finalize using:

builder.finalize(
    final_state=...,
    completed_at=...,
    blocked_condition=...,
)

Do not use inspect.signature or dynamic API discovery.

Do not create compatibility fallbacks.

The Phase 3A API already exists and is authoritative.

MISSION RESULT INPUT

Support the current MissionRepairAdapter result structure:

{
    "status": ...,
    "attempts": ...,
    "initial_validation": ...,
    "history": [...],
    "failures": [...],
    "blocked_reasons": [...]
}

IMPORTANT:

mission_result["attempts"] is an INTEGER COUNT in the current adapter.

The actual attempt entries are in:

mission_result["history"]

Therefore:

- NEVER interpret mission_result["attempts"] as a list
- use mission_result["history"] for attempt translation
- preserve history ordering
- preserve each history item's "attempt" number exactly

CURRENT HISTORY STRUCTURE

Each history entry may contain:

{
    "attempt": 1,
    "generation": {
        "success": True/False,
        "error": ...
    },
    "apply": {
        "success": True/False/None,
        "error": ...
    },
    "validation": {
        "success": True/False/None,
        "error": ...
    }
}

Translate statuses deterministically:

success True  -> "succeeded"
success False -> "failed"
success None  -> None

Do NOT copy raw error strings into audit output.

FAILURE INFORMATION

failure_category and safe_failure_summary are supplied by the caller for the
initial failure.

Attempt-level safe summaries may be derived only from already-sanitized,
non-secret structural information.

Never retain:

- raw exception objects
- raw error fields
- provider responses
- test logs
- traceback content

PATHS

allowed_paths and denied_paths are supplied as translator arguments.

Use defensive tuple snapshots.

Apply the same allowed_paths and denied_paths to every RepairAttemptEvent unless
the input explicitly provides safe per-attempt path values.

Do not mutate caller collections.

FINAL STATE

Accept only the Phase 3A final states:

- succeeded
- exhausted
- blocked
- failed

Map MissionRepairAdapter status directly when already one of these values.

Do not invent additional final-state synonyms unless required by tests.

For blocked results:

blocked_condition should be derived from the first value in blocked_reasons
when supplied, otherwise None.

ZERO ATTEMPTS

A succeeded result with empty history is valid.

It must produce:

total_attempts == 0
attempts == ()

REPAIR ID

repair_id is mandatory caller input.

Do not generate repair IDs.

PASSIVE CONTRACT

audit_integration.py MUST NOT:

- call MissionRepairAdapter
- mention MissionRepairAdapter by name in comments/docstrings/source
- call IntegrationCoordinator
- execute repairs
- retry anything
- run subprocesses
- use network
- access providers
- write files
- read files
- use Git
- access environment secrets
- create timestamps implicitly

It only translates already-produced state.

NO DYNAMIC FRAMEWORK

Do not use:

- inspect
- dynamic constructor discovery
- fallback event proxy classes
- generic event adapters
- generic stream merging
- dedupe/sort frameworks

Use the existing Phase 3A classes directly.

SOURCE SAFETY

Do not include repository-forbidden complete literals in source or tests.

For private-key-like sanitizer tests, construct synthetic sensitive material
dynamically from harmless string pieces.

Do not embed the complete forbidden marker in strings, comments, regexes,
docstrings or assertions.

TESTS

Use unittest only.
No pytest.
Zero skips.

Tests must exercise ONLY the Self-Healing audit translator defined above.

Do not create tests for generic merge/dedupe/sort behavior.

Cover:

1. zero-attempt succeeded result
2. one-attempt succeeded result
3. two-attempt succeeded result
4. three-attempt succeeded result
5. exhausted result
6. blocked result
7. failed result
8. blocked condition preserved
9. history order preserved
10. attempt number preserved
11. duplicate attempt numbers rejected
12. missing attempt number rejected
13. zero attempt number rejected
14. negative attempt number rejected
15. allowed paths preserved
16. denied paths preserved
17. caller history not mutated
18. caller paths not mutated
19. Bearer secret redacted through Phase 3A
20. password secret redacted
21. api-key secret redacted
22. access-token secret redacted
23. private-key-like value redacted using dynamically constructed test input
24. raw error field not retained
25. raw exception object not retained
26. deterministic serialization
27. equivalent inputs equivalent output
28. timestamp normalization delegated to Phase 3A
29. missing optional validation status handled
30. no filesystem/process/network/provider side effects
31. no retry loop
32. no repair execution component invocation
33. returned type is SelfHealingAuditRecord
34. attempts are immutable RepairAttemptEvent objects

TEST SOURCE MUST NOT assert generic audit-stream behavior.

Acceptance:

- Phase 3B-1 tests: zero failures/errors/skips
- Phase 3A tests remain passing
- Mission Adapter tests remain passing
- Phase 2A tests remain passing
- Phase 1 tests remain passing
- Mission Runner Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository suite remains passing

Do not modify any existing production file.
