CORE_MAINTENANCE_APPROVED

Mission: Minimal Core Protection Integration

Goal

Make the smallest possible change to:

- agent/ai/mission_runner.py

Do not modify any other file.

# Deliverables

- agent/ai/mission_runner.py

# End Deliverables

Required change only

Use the existing module:

agent.policies.core_protection

and the existing manifest:

agent/policies/core_lock_manifest.json

Do not duplicate policy logic.

Current Mission Runner flow validates each generated file in write_generated_files() before writing it.

Integrate protection exactly there.

Implementation requirements

1. Import the existing policy helpers from agent.policies.core_protection.

2. Extend write_generated_files so it receives the original repository-controlled mission text.

3. For every generated file:

- first run the existing validate_generated_file(...)
- derive the normalized repository-relative path
- load the existing core lock manifest
- call validate_mission_write(relative_path, mission_text, config)

4. If decision.allowed is False:

raise MissionError(decision.code or "CORE_PATH_LOCKED")

Do not include generated content or mission text in the exception.

5. If allowed, continue the existing write behavior unchanged.

6. Update run_mission() so the original mission variable loaded by:

mission_path, mission = load_mission(mission_name)

is passed into write_generated_files(...).

The approval marker must therefore come only from the original mission file.

Do not inspect:

- generated output
- environment variables
- command line flags
- provider response

for authorization.

Fail closed

If the manifest cannot be loaded or the protection policy raises an unexpected error, generated writes must stop with a safe MissionError.

Do not fall back to unprotected writes.

Preserve everything else

Do not redesign or rewrite Mission Runner.

Preserve:

- create_branch
- parse_generation
- validate_generated_file
- forbidden content checks
- atomic file writes
- validate_generated_files
- full unittest execution
- commit_and_push
- cleanup behavior
- existing console output

Do not add auto-merge.

Do not modify canonical tests.

This mission is explicitly authorized to modify mission_runner.py because it contains:

CORE_MAINTENANCE_APPROVED

Return exactly one generated file:

agent/ai/mission_runner.py

All repository tests must pass.
