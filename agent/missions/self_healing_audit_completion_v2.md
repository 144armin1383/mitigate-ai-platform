
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
