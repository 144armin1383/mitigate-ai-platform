Mission: Self-Healing Phase 3B-1 Audit Integration Adapter

Goal

Create a passive integration layer between the existing Self-Healing repair
results and the Phase 3A observability audit model.

This phase must NOT modify Mission Runner, MissionRepairAdapter,
IntegrationCoordinator, retry behavior, Core Protection, Git behavior,
provider behavior, or filesystem behavior.

The integration layer converts existing repair lifecycle information into
immutable Phase 3A audit records.

# Deliverables

- agent/repair/audit_integration.py
- agent/tests/test_self_healing_audit_integration.py

# End Deliverables

Existing Components

Reuse:

- agent/repair/mission_adapter.py
- agent/repair/integration.py
- agent/repair/observability.py

Do not duplicate:

- retry logic
- failure classification
- repair IDs
- redaction logic
- timestamp normalization
- observability record models

Architecture

Create a passive SelfHealingAuditIntegration component.

Its responsibility is translation only.

It accepts already-produced repair lifecycle information and constructs:

RepairAttemptEvent
SelfHealingAuditRecord

through the existing Phase 3A SelfHealingAuditBuilder.

It must not control repair execution.

Inputs

Support translation from mission-oriented repair information including:

- mission_name
- repair_id
- initial_failure_category
- initial_safe_summary
- allowed_paths
- denied_paths
- repair history / attempt history
- final_state
- blocked_condition
- started_at
- completed_at

Attempt Translation

Translate each repair attempt into RepairAttemptEvent.

Preserve:

- attempt number
- failure category
- safe summary
- allowed paths
- denied paths
- generation status
- application status
- validation status
- timestamps

Do not invent missing attempt numbers.

Do not reorder attempts.

Do not mutate caller input.

Repair ID

repair_id must be supplied by caller.

Do not generate repair IDs.

Sanitization

All strings must pass through existing Phase 3A sanitizer behavior.

Do not duplicate secret-regex logic if observability already provides it.

Raw exception messages must never be stored directly.

Raw provider responses must never be stored.

Raw test logs must never be stored.

Final State

Support exactly:

- succeeded
- exhausted
- blocked
- failed

Invalid final states must be rejected by the existing observability model.

Blocked Condition

Preserve a sanitized blocked_condition when final_state is blocked.

If final_state is not blocked, blocked_condition may be None.

Passive Contract

audit_integration.py must NOT:

- write files
- open files
- create directories
- call Git
- execute subprocesses
- use network
- call providers
- invoke MissionRepairAdapter.run
- invoke IntegrationCoordinator.run
- retry anything
- change repair decisions

It only translates already-existing state.

Input Immutability

All caller mappings, lists and tuples must remain unchanged.

Create defensive snapshots.

Output Immutability

Return only immutable SelfHealingAuditRecord objects.

No raw source objects should be retained by reference where mutation could alter
the audit record later.

Determinism

Equivalent inputs must produce equivalent serialized audit output.

No random values.
No implicit current time.
No process IDs.
No memory addresses.

Timestamps must be supplied by caller.

History Compatibility

Support the current MissionRepairAdapter result structure where appropriate:

- status
- attempts
- initial_validation
- history
- failures
- blocked_reasons

Do not require MissionRepairAdapter itself to change.

Provide a clear translation API such as:

build_audit_from_mission_result(...)

or equivalent.

The translator must safely handle:

- zero repair attempts
- one attempt
- multiple attempts
- exhausted result
- blocked result
- missing optional stage status
- sanitized failure entries

Validation

Reject structurally invalid attempt data that would create ambiguous audit
records.

Do not silently renumber attempts.

Do not silently invent successful statuses.

Tests

Use unittest only.
No pytest.
Zero skips.

Cover at least:

1. zero-attempt succeeded audit
2. one-attempt succeeded audit
3. two-attempt succeeded audit
4. three-attempt succeeded audit
5. exhausted audit
6. blocked audit
7. failed audit
8. blocked condition preserved
9. attempt order preserved
10. attempt number preserved
11. duplicate attempt rejected
12. missing attempt number rejected
13. invalid attempt number rejected
14. allowed paths preserved
15. denied paths preserved
16. caller history not mutated
17. caller path collections not mutated
18. Bearer secret redacted
19. password redacted
20. api key redacted
21. access token redacted
22. private-key-like content redacted
23. raw provider response not retained
24. raw exception object not retained
25. deterministic serialization
26. equivalent inputs equivalent output
27. timestamps preserved and normalized by Phase 3A
28. final states map correctly
29. missing optional validation status handled safely
30. no filesystem side effects
31. no subprocess/network/provider imports
32. no retry loops
33. audit integration does not invoke repair execution
34. output is immutable SelfHealingAuditRecord

Acceptance

- new Phase 3B-1 tests: zero failures/errors/skips
- Phase 3A observability tests remain passing
- Mission Adapter tests remain passing
- Phase 2A tests remain passing
- Phase 1 tests remain passing
- Mission Runner Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify existing production files.
