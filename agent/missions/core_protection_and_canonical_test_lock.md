Mission: Build Core Protection and Canonical Test Lock

Goal

Protect the MITIGATE AI core and canonical recovery tests from modification by normal autonomous missions.

Core changes must be denied by default.

Only explicitly approved core-maintenance missions may modify protected core files, and canonical tests must remain protected unless an explicit test-contract maintenance mode is approved.

Security and reliability are more important than convenience.

Scope

Create a dedicated protection layer and integrate it into Mission Runner write validation.

Do not redesign existing core logic.
Do not change business behavior.
Do not change provider selection.
Do not change runtime behavior.
Do not change recovery behavior.
Do not modify canonical recovery test contents.
Do not add dependencies.
Use Python standard library only.
Fully compatible with Python 3.12.

Deliverables

- agent/policies/core_protection.py
- agent/policies/core_lock_manifest.json
- agent/tests/test_core_protection.py
- agent/ai/mission_runner.py

Protected Core Policy

Normal missions must not modify, create, rename, or delete files under these protected areas:

- agent/ai/
- agent/runtime/
- agent/api/
- agent/orchestrator/
- agent/autonomy/
- agent/memory/
- agent/bootstrap/
- agent/policies/

Exception:

The new protection implementation itself may be created during this mission.

After installation, normal missions must treat these paths as protected.

Canonical Test Lock

The following test must be explicitly protected:

- agent/tests/test_portable_agent_recovery.py

Also support additional canonical test paths declared in the manifest.

Normal missions must not:

- overwrite
- delete
- rename
- regenerate
- replace
- truncate

canonical tests.

Protection Manifest

Create:

agent/policies/core_lock_manifest.json

It must define at minimum:

- schema_version
- protected_core_paths
- canonical_test_paths
- core_maintenance_marker
- test_contract_maintenance_marker
- manual_merge_required_for_core_changes
- full_suite_required_for_core_changes
- recovery_gate_required_for_core_changes

Use safe, explicit marker names:

CORE_MAINTENANCE_APPROVED
TEST_CONTRACT_MAINTENANCE_APPROVED

Default Policy

If a generated file target matches a protected core path:

- deny by default
- raise a safe deterministic error
- failure code: CORE_PATH_LOCKED

If a generated file target matches a canonical test path:

- deny by default
- raise a safe deterministic error
- failure code: CANONICAL_TEST_LOCKED

Do not silently ignore attempted writes.

Explicit Core Maintenance Override

A mission may modify protected core paths only when the mission text contains the exact explicit marker:

CORE_MAINTENANCE_APPROVED

The marker must not be inferred from natural-language intent.

The marker must be present explicitly in the mission source.

Even when the marker is present:

- canonical tests remain locked unless separate test-contract marker is present
- full repository tests are required
- canonical recovery tests are required
- automatic merge must not occur
- branch must remain unmerged for manual review

Explicit Canonical Test Override

A canonical test may only be modified when mission text contains:

TEST_CONTRACT_MAINTENANCE_APPROVED

This mode must also require:

CORE_MAINTENANCE_APPROVED

Therefore test-contract modification requires both markers.

Normal feature missions can never alter canonical tests.

Mission Runner Integration

Integrate the protection check before any generated file is written.

Protection check must occur after path normalization but before file write.

It must inspect:

- normalized relative target path
- mission source text
- lock manifest

Do not use environment variables to bypass locks.

Do not use command-line flags to bypass locks.

Do not allow generated output to grant itself permission.

Only the original repository-controlled mission source may contain approval markers.

Path Safety

Protection must correctly handle:

- relative paths
- redundant ./ segments
- path traversal attempts
- mixed separators where applicable
- exact file matches
- nested protected directories

Examples that must be blocked:

agent/ai/mission_runner.py
./agent/ai/mission_runner.py
agent/bootstrap/env.example
agent/memory/example.py
agent/tests/test_portable_agent_recovery.py

Path traversal must not bypass protection.

Core Maintenance Safety

When a core-maintenance marker is present:

- modification may proceed only on a mission branch
- Mission Runner must not auto-merge
- Mission Runner must not directly modify main
- final result must explicitly report manual merge required

Do not introduce automatic merging.

Canonical Test Integrity

Implement a manifest helper that can report whether a path is:

- unprotected
- protected_core
- canonical_test

Provide deterministic public functions suitable for tests.

Suggested public API

- CoreProtectionPolicy
- CoreProtectionConfig
- ProtectionDecision
- ProtectionReason
- load_core_lock_manifest
- classify_protected_path
- validate_mission_write
- core_protection_status

Exact implementation names may vary slightly if necessary, but keep the interface simple and deterministic.

No Hash-Based False Security Requirement

Do not rely only on stored file hashes to protect the core.

Path-level policy is mandatory.

Optional hashes may be included only as an integrity signal, not as the primary lock mechanism.

Failure Behavior

Protection failures must:

- fail closed
- use deterministic error codes
- avoid raw traceback persistence
- avoid exposing full mission text
- avoid exposing generated content
- avoid exposing protected configuration

Test Requirements

Create comprehensive unittest coverage using standard library only.

Tests must include:

1. normal mission cannot modify agent/ai/
2. normal mission cannot modify agent/runtime/
3. normal mission cannot modify agent/autonomy/
4. normal mission cannot modify agent/memory/
5. normal mission cannot modify agent/bootstrap/
6. normal mission cannot modify agent/policies/
7. normal mission cannot modify canonical recovery test
8. non-core project/site path remains allowed
9. CORE_MAINTENANCE_APPROVED permits protected core path
10. core marker alone does not permit canonical test modification
11. TEST_CONTRACT_MAINTENANCE_APPROVED alone does not permit canonical test modification
12. both markers permit canonical test modification
13. traversal cannot bypass protection
14. ./ normalization cannot bypass protection
15. unknown manifest fields rejected where appropriate
16. malformed manifest rejected
17. deterministic classification
18. input objects not mutated
19. no environment-variable bypass
20. normal mission behavior outside protected paths unchanged

Mission Runner Regression

All existing tests must continue to pass.

Canonical Recovery Gate

The following test must continue to pass with zero skip:

agent/tests/test_portable_agent_recovery.py

Do not modify that file.

Repository Safety

Do not leave temporary files in repository root.

Do not modify unrelated files.

Do not weaken existing forbidden-content validation.

Do not weaken path allowlists.

Do not weaken recovery protections.

Do not weaken Git branch isolation.

Manual Merge Policy

This mission itself is allowed to modify agent/ai/mission_runner.py because this mission is the initial installation of core protection.

After this feature is installed, future normal missions must be subject to the lock.

Generated implementation must not merge itself into main.

All existing unittest tests must pass.

