Mission: Complete Self-Healing Operational Hardening

Goal

Complete the production-oriented operational hardening of the existing
Self-Healing subsystem in one mission.

The existing Self-Healing architecture is already implemented and must be
preserved:

Mission Runner
-> MissionRepairAdapter
-> IntegrationCoordinator
-> bounded repair attempts
-> runtime audit capture
-> sanitized immutable audit record
-> append-only audit persistence
-> Private Admin read-only monitoring

This mission must harden that existing architecture against operational
failure modes without redesigning it.

This is NOT a new repair system.
This is NOT a new retry system.
This is NOT a replacement for the existing audit system.

The existing behavior, safety boundaries, Core Protection rules and
three-attempt maximum are authoritative.

# Deliverables

- agent/repair/operational_hardening.py
- agent/tests/test_self_healing_operational_hardening.py
- agent/tests/test_self_healing_failure_injection.py

# End Deliverables

Existing Architecture

The implementation must work with the existing APIs in:

- agent/repair/mission_adapter.py
- agent/repair/integration.py
- agent/repair/repair_loop.py
- agent/repair/observability.py
- agent/repair/audit_integration.py
- agent/repair/runtime_audit.py
- agent/repair/audit_store.py
- agent/ai/mission_runner.py

Do not duplicate or replace these components.

Do not introduce another retry loop.

MissionRepairAdapter / IntegrationCoordinator remain the sole authority for
repair attempts and retry progression.

The maximum number of repair attempts must remain exactly three.

Operational Hardening Requirements

Implement deterministic, passive operational-hardening helpers for the
Self-Healing subsystem.

The module must provide safe primitives for detecting and representing
operational failure conditions without controlling repair decisions.

Cover at least the following conditions:

1. audit persistence failure
2. malformed or corrupted audit JSONL records
3. partially written audit records
4. unavailable audit path
5. permission-denied audit persistence
6. concurrent audit readers and writers
7. duplicate audit records
8. repeated repair identifiers
9. malformed mission-result structures
10. missing optional audit fields
11. unexpected callback exceptions
12. validation callback exceptions
13. generation callback exceptions
14. application callback exceptions
15. audit capture exceptions
16. audit persistence exceptions
17. interrupted operational state
18. stale/incomplete operational metadata
19. deterministic handling of unknown failure categories
20. bounded behavior under repeated failures

Operational Status Model

Create an immutable operational status/result model.

It must expose only sanitized operational information.

At minimum represent:

- healthy
- degraded
- unavailable

Include safe machine-readable reason codes.

Do not retain raw exceptions.

Do not retain raw provider responses.

Do not retain credentials, authorization headers, tokens, passwords,
private-key material or environment secrets.

All externally visible error information must be sanitized.

Failure Isolation

Observability and audit failures must remain passive.

An audit persistence failure must never:

- create a repair attempt
- trigger a retry
- change retry count
- change a repair decision
- change a successful repair into a failed repair
- bypass Core Protection
- modify mission deliverables
- invoke a provider
- invoke Git
- invoke deployment

Operational hardening must not become a control plane.

Concurrency

Validate existing append-only audit behavior under concurrent access.

Tests must demonstrate that concurrent append operations do not produce
interleaved or invalid JSON records.

Tests must demonstrate that readers tolerate concurrent append activity.

Do not introduce background threads into production behavior.

Threads or processes may be used only inside tests where necessary to
exercise concurrency.

Corruption Tolerance

Operational inspection of audit data must tolerate:

- blank lines
- truncated final lines
- malformed JSON
- structurally invalid records
- unknown fields
- unsupported records

A corrupt audit record must not crash operational inspection.

Valid records surrounding a corrupt record must remain readable.

Do not silently transform corrupt records into valid audit records.

Determinism

Equivalent inputs must produce equivalent operational results.

Ordering must be deterministic.

Reason-code ordering must be deterministic.

Do not use randomness.

Do not use wall-clock time to make control decisions.

Do not generate UUIDs for operational decisions.

Boundedness

No new unbounded loop is allowed.

No recursive retry mechanism is allowed.

No hidden retry mechanism is allowed.

No retry may be introduced around:

- provider calls
- Git operations
- audit persistence
- mission execution
- validation
- repair generation
- repair application

Existing bounded Self-Healing behavior remains authoritative.

Security

No new network access.

No shell execution.

No subprocess execution.

No Git invocation.

No provider invocation.

No deployment behavior.

No environment-variable enumeration.

No secret persistence.

No raw exception persistence.

No raw provider-response persistence.

No dynamic code execution.

Do not use:

- eval
- exec
- pickle
- marshal

Production Module Restrictions

agent/repair/operational_hardening.py must remain side-effect-light.

Importing the module must not:

- create files
- create directories
- modify files
- start threads
- start processes
- access the network
- invoke Git
- invoke providers

Filesystem access, if required for explicit operational inspection, must be
read-only.

The module must not modify audit records.

The module must not repair corrupted audit files.

It may report sanitized operational conditions only.

Compatibility

Do not modify the public behavior of:

- MissionRepairAdapter
- IntegrationCoordinator
- RepairLoop
- SelfHealingAuditRecord
- SelfHealingAuditStore
- RuntimeAuditCaptureResult
- Private Admin API

Do not modify Core Lock configuration.

Do not modify repository protection policies.

Do not modify deployment behavior.

Do not modify provider behavior.

Do not modify requirements.txt.

Use Python standard library only.

Testing

Use unittest only.

Do not use pytest.

Do not add testing dependencies.

Tests must include comprehensive failure injection.

At minimum verify:

- immutable operational result model
- deterministic serialization
- sanitized reason codes
- no raw exception retention
- no raw provider-response retention
- secret redaction
- malformed audit tolerance
- truncated final-record tolerance
- valid records survive neighboring corruption
- concurrent append integrity
- concurrent read tolerance
- persistence failure isolation
- audit capture failure isolation
- callback exception isolation
- duplicate record handling
- deterministic ordering
- exactly-three-attempt ceiling remains unchanged
- no fourth repair attempt can occur
- operational helpers cannot invoke repair execution
- operational helpers cannot invoke provider execution
- operational helpers cannot invoke Git
- operational helpers cannot invoke deployment
- no production background thread creation
- no production process creation
- no filesystem writes by operational inspection
- existing Self-Healing APIs remain compatible
- existing audit APIs remain compatible
- existing Private Admin monitoring remains compatible

Failure-injection tests must prove that audit/observability failures cannot
change repair outcome or retry count.

Regression Safety

All existing repository tests must continue to pass.

Do not weaken existing assertions merely to make tests pass.

Do not delete existing tests.

Do not skip new tests.

Do not change the existing three-attempt repair ceiling.

Do not modify unrelated production files.

Generated Source Safety

Do not include complete repository-forbidden credential/private-key markers
literally anywhere in generated source, including tests, comments, strings,
docstrings, regex patterns or fixtures.

If secret-like test material is required, construct it dynamically from
harmless fragments at runtime.

Do not place real credentials or realistic production credentials in tests.

Completion Criteria

The mission is complete only when:

1. all declared deliverables are generated;
2. Python compilation succeeds;
3. the new operational-hardening tests pass;
4. failure-injection tests pass;
5. the full repository unittest suite passes;
6. no existing Self-Healing behavior is weakened;
7. the maximum repair attempt count remains exactly three;
8. no forbidden production side effects are introduced;
9. repository safety and Core Protection remain unchanged.

Generate only the declared deliverables.
