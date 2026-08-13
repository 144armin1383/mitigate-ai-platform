# MITIGATE Validation Evidence Core Wiring — Approved Core Maintenance

Mission ID: validation-evidence-core-wiring-approved-20260813063308
Request ID: validation-evidence-core-wiring-approved-20260813063308
Task Type: backend

CORE_MAINTENANCE_APPROVED

## Objective

Implement the minimum safe Core wiring required to connect validation
failure evidence to the existing bounded autonomous self-healing lifecycle.

The repository already contains:

- native self-healing components
- validation failure capture
- bounded retry controls
- allowlist recovery classification
- structured repair evidence
- retry budget enforcement

Previous implementation missions demonstrated that the remaining integration
point requires a protected Core change.

This mission is explicitly authorized to perform that minimum Core
maintenance under the repository's existing Core protection policy.

## Authorized Core Scope

The only protected Core production path authorized for modification is:

- agent/ai/mission_runner.py

Do not modify any other protected Core production path.

## Additional Allowed Deliverables

The mission may also create or modify:

- agent/tests/test_validation_evidence_core_wiring.py
- docs/architecture/validation-evidence-core-wiring.json

## Required Behaviour

Integrate the existing validation/self-healing evidence path at the smallest
appropriate interception point in agent/ai/mission_runner.py.

The implementation must:

1. Preserve validator authority.
2. Preserve Core protection.
3. Preserve the generated-path allowlist.
4. Never silently expand allowed deliverables.
5. Never silently remap generated paths.
6. Preserve retry budgets.
7. Preserve repeated-failure detection.
8. Preserve checkpoint and execution identity.
9. Preserve idempotent execution semantics.
10. Preserve provider independence.
11. Reuse existing repair/self-healing components rather than duplicating them.
12. Feed structured validation failure evidence into the existing bounded
    repair lifecycle where applicable.
13. Fail closed if self-healing integration is unavailable.
14. Never convert a protected-Core violation into an automatic unrestricted
    repair.
15. Keep this Core change minimal.

## Core Safety Requirements

The Core authorization in this mission applies ONLY to:

agent/ai/mission_runner.py

It does not authorize modification of:

- agent/runtime/
- agent/api/
- agent/orchestrator/
- agent/autonomy/
- agent/memory/
- agent/bootstrap/
- agent/policies/
- agent/core/
- agent/services/
- agent/providers/
- agent/deploy/

Do not modify:

agent/tests/test_portable_agent_recovery.py

Do not modify:

agent/policies/core_lock_manifest.json

Do not weaken or remove Core protection.

## Validation

Run targeted tests for the new wiring.

Then run the complete existing test suite.

The implementation is not successful unless the complete suite passes.

## Required Architecture Report

Write:

docs/architecture/validation-evidence-core-wiring.json

The report must be strict valid JSON and include at least:

{
  "mission_id": "validation-evidence-core-wiring-approved-20260813063308",
  "implementation_completed": true,
  "core_modified": true,
  "authorized_core_path": "agent/ai/mission_runner.py",
  "core_maintenance_marker_used": true,
  "core_protection_preserved": true,
  "validator_authority_preserved": true,
  "allowlist_preserved": true,
  "bounded_retry_preserved": true,
  "repeated_failure_detection_preserved": true,
  "checkpoint_identity_preserved": true,
  "execution_identity_preserved": true,
  "provider_independence": true,
  "targeted_tests_passed": true,
  "full_test_suite_passed": true,
  "manual_merge_required": true,
  "remaining_work": ""
}

## Completion Rules

Do not merge this mission into main automatically.

The repository policy requires manual review and merge for Core changes.

Commit the completed implementation to the mission branch only.

Do not modify infrastructure.

Do not restart services.

Do not alter production runtime data.
