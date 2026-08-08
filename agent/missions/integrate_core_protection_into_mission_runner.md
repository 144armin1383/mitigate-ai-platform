CORE_MAINTENANCE_APPROVED

Mission: Integrate Core Protection into Mission Runner

Goal

Integrate the existing repository-controlled Core Protection Policy into Mission Runner with the smallest possible change.

This is an explicitly approved core-maintenance mission.

Modify only:

- agent/ai/mission_runner.py

Do not modify:

- agent/policies/core_protection.py
- agent/policies/core_lock_manifest.json
- agent/tests/test_core_protection.py
- agent/tests/test_portable_agent_recovery.py
- any other production module
- requirements.txt

Do not add dependencies.

# Deliverables

- agent/ai/mission_runner.py

# End Deliverables

Integration Contract

Mission Runner must enforce Core Protection before any generated file is written.

Use the existing policy implementation from:

agent.policies.core_protection

Use the repository-controlled manifest:

agent/policies/core_lock_manifest.json

Do not duplicate protection logic inside Mission Runner.

Minimal Integration

Add only the smallest necessary integration.

Before writing each generated file:

1. normalize and validate the generated path using existing Mission Runner path-safety logic
2. load the Core Protection manifest through the existing policy API
3. validate the target path using the original mission source text
4. if denied:
   - abort before file write
   - raise MissionError
   - include only deterministic safe failure code:
     - CORE_PATH_LOCKED
     - CANONICAL_TEST_LOCKED
5. if allowed:
   - continue existing generated-file validation and write flow

Mission Source Authority

Approval markers must be read only from the original repository-controlled mission file.

Do not accept approval markers from:

- AI-generated output
- environment variables
- command-line arguments
- generated files
- provider responses

Core Maintenance Behavior

Because this mission contains CORE_MAINTENANCE_APPROVED, it may modify:

agent/ai/mission_runner.py

For any mission that modifies protected core paths with valid authorization:

- preserve mission branch isolation
- do not auto-merge
- keep manual merge required
- require normal validation
- require full repository unittest suite
- require canonical recovery test gate

Canonical Test Behavior

CORE_MAINTENANCE_APPROVED alone must NOT permit modification of:

agent/tests/test_portable_agent_recovery.py

Canonical test modification still requires both:

CORE_MAINTENANCE_APPROVED
TEST_CONTRACT_MAINTENANCE_APPROVED

Failure Safety

Do not expose:

- mission source text
- generated file content
- provider response
- credentials
- secrets
- environment values

A blocked write should produce a safe failure similar to:

MissionError: CORE_PATH_LOCKED

or:

MissionError: CANONICAL_TEST_LOCKED

Do not silently skip denied writes.

Fail Closed

If the protection manifest:

- cannot be loaded
- is malformed
- has unsupported schema
- causes an unexpected protection error

Mission Runner must fail closed for generated writes.

Do not fall back to unprotected behavior.

Regression

Preserve all existing Mission Runner behavior for unprotected paths.

Do not redesign:

- branch creation
- AI generation
- deliverable extraction
- forbidden-content validation
- test validation
- Git push behavior
- cleanup behavior

Do not introduce auto-merge.

Verification Requirements

After implementation all existing tests must pass.

The following must specifically remain green:

- agent/tests/test_core_protection.py
- agent/tests/test_portable_agent_recovery.py

Manual merge remains required for this core change.
