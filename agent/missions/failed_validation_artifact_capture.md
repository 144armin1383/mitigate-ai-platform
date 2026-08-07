Mission: Preserve Failed Validation Artifacts Safely

Goal

Add a safe diagnostic artifact-capture mechanism to Mission Runner so that generated files can be inspected and pinned when generation succeeds but repository validation/tests fail.

Modify only:

- agent/ai/mission_runner.py

Do not modify tests.
Do not modify requirements.txt.
Do not add dependencies.
Use Python standard library only.
All existing unittest tests must pass.

Core Requirement

When a mission:

1. successfully parses the AI generation response,
2. successfully passes generated-path and forbidden-content validation,
3. successfully writes generated files,
4. but later fails during validate_generated_files because py_compile, unittest, or another post-write repository validation fails,

Mission Runner must preserve copies of the generated files outside the repository before rollback/cleanup.

Artifact Location

Use a path under:

/tmp/mitigate-ai-failed-validation/

Create a unique subdirectory using safe values derived from:

- mission name
- timestamp or unique run identifier

Example conceptual structure:

/tmp/mitigate-ai-failed-validation/
  portable_agent_recovery_tests-20260807T160000/
    agent/
      tests/
        test_portable_agent_recovery.py
    manifest.json

Security Boundary

Do NOT preserve generated content when failure occurs during:

- generated path allowlist validation
- forbidden-content validation
- secret detection
- generation JSON parsing
- any validation that occurs before generated files have been approved for writing

In particular, if validate_generated_file rejects content as forbidden, that content must NOT be persisted anywhere.

Artifact capture is allowed only after generated files have already passed the Mission Runner content-safety checks.

Repository Safety

Artifacts must never be stored inside repository root.

Do not create:

- tmp directories in repository root
- debug files in repository root
- backup copies in agent/
- untracked diagnostic files inside Git working tree

Use /tmp only.

Preserve Clean Working Tree

Mission Runner must preserve its existing repository rollback/cleanup behavior.

After a failed mission:

- repository state must remain clean according to existing policy
- diagnostic copies remain only under /tmp

Manifest

Write a small JSON manifest beside captured files containing safe metadata only:

- mission name
- capture timestamp
- generated relative paths
- validation stage
- exception class name
- safe short failure category

Do not include:

- AI raw response
- prompts
- provider responses
- environment values
- authorization data
- access values
- raw exception payloads containing sensitive content

Do not persist full exception text unless it has already been sanitized by existing safe-error handling.

Public Behavior

Do not change:

- mission success semantics
- branch semantics
- Git push behavior
- validation requirements
- forbidden-content rules
- generated path allowlists
- test execution behavior

This is diagnostic preservation only.

Logging

On a post-write validation failure where artifacts are captured, log one safe informational/error line containing only the artifact directory path.

Example concept:

Failed validation artifacts preserved at: /tmp/mitigate-ai-failed-validation/<safe-run-id>

Do not log generated file contents.

Implementation Safety

Do not use:

- shell execution
- os.system
- eval
- exec
- dynamic imports
- network calls

Use pathlib, shutil, json, datetime, uuid, and other Python standard-library facilities as appropriate.

Regression Requirement

All existing unittest tests must pass.

Deliverables

- agent/ai/mission_runner.py
