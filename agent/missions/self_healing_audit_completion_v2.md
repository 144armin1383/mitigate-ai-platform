Mission: Complete Self-Healing Audit System v2

Goal

Complete the Self-Healing audit subsystem in one implementation.

The existing architecture already contains:
- immutable sanitized observability records
- passive MissionRepairAdapter result translation
- passive Mission Runner runtime audit capture

This mission must finish the audit subsystem by:
1. fixing the existing runtime-to-translator API mismatch,
2. adding durable local persistence,
3. adding deterministic query/read support,
4. integrating persistence into runtime audit capture,
5. adding comprehensive regression and integration tests.

The audit subsystem must remain strictly passive.

Audit failures MUST NEVER alter:
- repair decisions
- retry decisions
- MissionRepairAdapter behavior
- IntegrationCoordinator behavior
- Core Protection
- mission success/failure
- Git behavior
- provider behavior

# Deliverables

- agent/repair/audit_store.py
- agent/repair/runtime_audit.py
- agent/tests/test_self_healing_audit_store.py
- agent/tests/test_self_healing_runtime_audit_persistence.py

# End Deliverables

Existing APIs

Use the existing Phase 3A model:

- RepairAttemptEvent
- SelfHealingAuditRecord
- SelfHealingAuditBuilder
- SelfHealingAuditRecord.to_dict()

Use the existing translator:

build_audit_from_mission_result(
    mission_name,
    repair_id,
    mission_result,
    *,
    allowed_paths=None,
    denied_paths=None,
    initial_failure_category=None,
    initial_safe_summary=None,
    started_at=None,
    completed_at=None,
)

IMPORTANT EXISTING BUG

agent/repair/runtime_audit.py currently calls the translator using:

failure_category=
safe_failure_summary=

but the actual translator requires:

initial_failure_category=
initial_safe_summary=

Fix this mismatch.

Do not change agent/repair/audit_integration.py merely to accommodate
the incorrect caller.

Persistence

Create agent/repair/audit_store.py.

Implement a dependency-free local JSONL audit store.

Requirements:

- standard library only
- append-only logical record model
- deterministic JSON serialization
- UTF-8
- one complete JSON object per line
- persist only SelfHealingAuditRecord.to_dict() output
- never accept or persist raw provider responses
- never accept raw exception objects
- never accept arbitrary mission_result structures
- storage API must accept SelfHealingAuditRecord objects
- create parent directory when required
- malformed existing records must not crash query operations
- partial/truncated final lines must be safely ignored
- persistence failure must be representable without exposing raw exception text

Default storage location must be deterministic and repository-local.

Use a path under:

tmp_self_healing_audit/

Do not store audit data inside agent source directories.

The runtime-generated audit directory must remain untracked.

Atomic / concurrency safety

Appending must avoid interleaving records from concurrent writers.

Use only Python standard-library mechanisms.

Do not introduce:
- database dependencies
- network storage
- Redis
- SQLite
- external locking packages

A failed write must not corrupt previously committed records.

Query API

Provide a small read/query API supporting filters for:

- mission_name
- repair_id
- final_state
- started_at lower bound
- started_at upper bound
- minimum total_attempts
- maximum total_attempts
- optional result limit

Results must be deterministic.

Newest/oldest ordering must be explicitly defined.

Query operations must not mutate stored data.

Deserialization

Stored records must be reconstructed as immutable
SelfHealingAuditRecord instances, including RepairAttemptEvent entries.

Do not return mutable raw dictionaries as the primary query result.

Schema

Preserve schema_version.

Unknown incompatible schema versions must be skipped safely by queries
rather than crashing the audit subsystem.

Runtime integration

Update agent/repair/runtime_audit.py.

Keep:

RuntimeAuditCaptureResult

and:

capture_self_healing_audit(...)

Fix the translator keyword mismatch.

After a SelfHealingAuditRecord is successfully built, persist it using
the audit store.

Persistence is fail-open.

If translation fails:

captured=False
record=None
safe_error_code="AUDIT_CAPTURE_FAILED"

If translation succeeds but persistence fails:

The repair/mission behavior must remain unaffected.

Return the successfully constructed sanitized record.

Use a stable safe error code such as:

"AUDIT_PERSISTENCE_FAILED"

Do not return raw exception text.

If both capture and persistence succeed:

captured=True
record=<SelfHealingAuditRecord>
safe_error_code=None

The meaning of captured must remain clear and tested.

No execution authority

Neither audit_store.py nor runtime_audit.py may:

- invoke MissionRepairAdapter
- invoke IntegrationCoordinator
- invoke RepairLoop
- invoke CodeGenerator
- invoke provider APIs
- invoke subprocess
- run Git commands
- control retry counts
- trigger repair attempts

Security

Tests must verify that persisted content does not contain secrets when
the input reaches persistence through the sanitized observability model.

Cover at least:

- Authorization Bearer token
- password
- API key
- access token
- refresh token
- URI credential parameter
- private-key-like content without embedding repository-forbidden
  static secret marker literals directly in generated source

Do not weaken existing forbidden-content validation.

Testing

Use unittest only.

Create comprehensive tests for:

1. successful append
2. multiple append operations
3. deterministic JSON serialization
4. reconstruction to SelfHealingAuditRecord
5. attempt reconstruction to RepairAttemptEvent
6. mission_name query
7. repair_id query
8. final_state query
9. time lower-bound query
10. time upper-bound query
11. min attempts query
12. max attempts query
13. result limit
14. deterministic ordering
15. malformed line ignored
16. truncated final line ignored
17. incompatible schema ignored
18. previous records survive failed append
19. parent directory creation
20. caller record not mutated
21. no raw exception persistence
22. no provider response persistence
23. secrets remain redacted
24. runtime translator API mismatch regression
25. runtime successful capture + persistence
26. runtime translation failure is fail-open
27. runtime persistence failure is fail-open
28. persistence failure exposes only safe error code
29. runtime record remains available after persistence failure
30. no repair execution authority
31. no subprocess/network/provider behavior
32. existing observability tests remain passing
33. existing audit integration tests remain passing
34. existing Mission Runner Self-Healing tests remain passing

Do not modify:

- agent/ai/mission_runner.py
- agent/repair/observability.py
- agent/repair/audit_integration.py
- agent/repair/mission_adapter.py
- agent/repair/integration.py
- agent/repair/repair_loop.py
- agent/policies/
- requirements.txt

Do not modify repair behavior.

Do not create an independent retry loop.

Do not add external dependencies.

The implementation is complete only when the full repository unittest
suite passes.

GENERATED TEST SOURCE SAFETY — MANDATORY

The previous generation failed because a generated test embedded a
repository-forbidden private-key marker literally in source.

Do NOT include any complete repository-forbidden secret/private-key marker
anywhere in generated source, including:

- strings
- comments
- docstrings
- regex patterns
- fixtures
- assertions
- sample credentials

For private-key-like redaction tests, construct the synthetic sensitive value
dynamically at runtime from harmless pieces.

Example semantic pattern:

begin = "BE" + "GIN"
private = "PRI" + "VATE"
key = "KE" + "Y"
end = "E" + "ND"

marker_start = f"-----{begin} {private} {key}-----"
marker_end = f"-----{end} {private} {key}-----"

Then compose the test value at runtime.

The complete forbidden marker must not appear literally in either:

- agent/tests/test_self_healing_audit_store.py
- agent/tests/test_self_healing_runtime_audit_persistence.py
- agent/repair/audit_store.py
- agent/repair/runtime_audit.py

The test must verify that:

- the synthetic secret body/value is absent after sanitization/persistence
- "[REDACTED]" is present where appropriate
- persisted audit content contains no raw private-key-like material

Apply the same source-safety principle to every Mission Runner forbidden
fragment.

All original Self-Healing Audit Completion requirements remain mandatory.

Do not modify any additional production file.

Generate only the four declared deliverables.
