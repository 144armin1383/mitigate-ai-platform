Mission: Self-Healing Phase 3A Observability and Repair Audit Trail

Goal

Add a deterministic, sanitized, local observability layer for Self-Healing
missions and repair activity.

This phase must NOT change repair decisions, retry behavior, Core Protection,
Mission Runner safety rules, Git behavior, provider behavior, or deployment.

Observability must be passive: it records what happened but never controls
whether a repair proceeds.

# Deliverables

- agent/repair/observability.py
- agent/tests/test_self_healing_observability.py

# End Deliverables

Architecture

Create a side-effect-light observability module dedicated to Self-Healing.

Do not modify:

- agent/ai/mission_runner.py
- agent/repair/mission_adapter.py
- agent/repair/integration.py
- agent/repair/repair_loop.py
- agent/policies/
- Core Lock configuration

This phase only creates the observability model and serialization layer.

Data Model

Create immutable dataclasses for at least:

RepairAttemptEvent

Fields:
- mission_name
- repair_id
- attempt_number
- failure_category
- safe_failure_summary
- allowed_paths
- denied_paths
- generation_status
- application_status
- validation_status
- started_at
- completed_at

SelfHealingAuditRecord

Fields:
- schema_version
- mission_name
- repair_id
- initial_failure_category
- initial_safe_summary
- final_state
- total_attempts
- blocked_condition
- attempts
- started_at
- completed_at

Final state must support:

- succeeded
- exhausted
- blocked
- failed

Immutability

All public records must be frozen / immutable.

Sequences must be stored as tuples.

Caller-provided collections must not be mutated.

Determinism

Provide deterministic serialization to plain JSON-safe dictionaries.

Serialization order and field names must remain stable.

Do not include:
- object memory addresses
- exception repr
- random IDs
- process IDs
- unstable dictionary ordering

Repair IDs

Do NOT invent a second repair-ID algorithm if Phase 1 already provides one.

Accept repair_id as an input from the existing repair subsystem.

Observability must not create autonomous identifiers.

Security / Redaction

Observability is a security boundary.

Never store raw:
- exceptions
- traceback text
- provider responses
- test output
- Authorization credentials
- passwords
- API keys
- access tokens
- refresh tokens
- private keys
- raw environment values

Implement a reusable sanitizer for observability strings.

Bearer data must normalize to:

Authorization: Bearer [REDACTED]

Generic credential values must become:

[REDACTED]

Raw secret values must not appear in:
- dataclass fields
- serialized dicts
- JSON serialization
- repr of public records

Truncation

Bound potentially large text fields.

Use an explicit maximum diagnostic/summary length.

When truncation occurs, use a deterministic suffix such as:

... [truncated]

Never truncate in a way that re-exposes secret fragments.

Timestamps

Accept timestamps as inputs.

Do not call current time implicitly inside pure model constructors if avoidable.

Normalize timestamps to stable UTC ISO-8601 strings for serialization.

Do not make tests depend on wall-clock time.

Audit Builder

Create a small builder/coordinator API that can:

1. start an audit record
2. append immutable repair-attempt events
3. finalize to succeeded / exhausted / blocked / failed
4. return the final immutable SelfHealingAuditRecord

The builder may be mutable internally, but finalized public records must be
immutable snapshots.

The builder must reject:
- attempt number <= 0
- duplicate attempt numbers
- attempts added after finalization
- second finalization
- invalid final states

It must preserve attempt ordering.

No Side Effects

agent/repair/observability.py must NOT:

- write files
- modify Git
- execute subprocesses
- use network
- call providers
- mutate repository files
- read environment secrets
- access databases

Persistence is explicitly OUT OF SCOPE for Phase 3A.

Phase 3A defines the audit model only.

Integration into Mission Runner will be a later Phase 3B.

Tests

Use unittest only.
No pytest.
Zero skips.

Cover at least:

1. immutable RepairAttemptEvent
2. immutable SelfHealingAuditRecord
3. deterministic serialization
4. stable schema_version
5. attempts preserve order
6. duplicate attempt rejected
7. zero attempt rejected
8. negative attempt rejected
9. finalize succeeded
10. finalize exhausted
11. finalize blocked
12. finalize failed
13. invalid final state rejected
14. add after finalize rejected
15. double finalize rejected
16. allowed paths immutable
17. denied paths immutable
18. caller collections not mutated
19. Bearer token redaction
20. password redaction
21. api_key redaction
22. access token redaction
23. refresh token redaction
24. private key redaction
25. raw exception-like secret absent
26. summary truncation deterministic
27. secret removed before truncation
28. timestamps serialized consistently
29. no filesystem side effects
30. no process/network/provider imports
31. JSON-safe output
32. equivalent inputs produce equivalent serialized output
33. repr does not expose raw secret values

Acceptance

- new observability tests: zero failures/errors/skips
- existing Self-Healing Phase 1 tests remain passing
- Phase 2A tests remain passing
- Mission Adapter tests remain passing
- Mission Runner Self-Healing tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify any existing production file in this mission.

GENERATED SOURCE SAFETY — MANDATORY

Both generated deliverables must themselves pass Mission Runner forbidden-content
validation.

Do NOT place repository-forbidden literal fragments anywhere in generated source,
including:

- strings
- regex patterns
- comments
- docstrings
- fixtures
- assertions
- sample credentials
- test names or messages

In particular, do not embed a complete PEM private-key header literal in source.

If testing redaction of private-key-like material is necessary, construct the
sensitive marker dynamically from harmless pieces at runtime, for example by
joining separate neutral fragments.

The resulting runtime test value may simulate sensitive content, but the complete
forbidden marker must not occur literally anywhere in either generated file.

Apply the same principle to every Mission Runner forbidden fragment.

Do not include literal dangerous execution-call expressions in tests or
observability.py.

SECURITY TESTING CONTRACT

Tests should verify semantics, not forbidden source literals.

For private-key redaction:

- construct the synthetic private-key-like input dynamically
- verify its sensitive body/value is absent from sanitized output
- verify [REDACTED] is present
- do not require the original sensitive marker to remain visible

For credential tests:

- dynamically construct sensitive values where necessary
- raw credential values must be absent from records, repr, dictionaries and JSON

OBSERVABILITY REMAINS PASSIVE

This source-safety correction must not alter the original Phase 3A architecture.

Still do NOT modify any existing production file.

Still create only:

- agent/repair/observability.py
- agent/tests/test_self_healing_observability.py

No persistence.
No Mission Runner integration.
No retry behavior.
No Git.
No subprocess.
No network.
No provider calls.
