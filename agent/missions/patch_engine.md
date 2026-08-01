Mission: Build Production Patch Engine

Goal

Implement a production-quality Patch Engine for the MITIGATE AI platform.

Requirements

- Parse unified diff patches
- Validate patch syntax
- Support dry-run mode
- Allow only repository-relative paths
- Prevent path traversal
- Reject absolute paths
- Create automatic backups
- Apply updates atomically
- Roll back on any failure
- Produce detailed execution logs
- 100% typed Python
- English only
- Unit tests
- Python 3.12 compatible

Rules

- Never modify existing public APIs.
- Never expose secrets.
- Never merge into main.
- Work on an isolated Git branch.
- Commit and push only if all tests pass.

Deliverables

agent/git/patch_engine.py
agent/tests/test_patch_engine.py

Additional Acceptance Criteria

- Correctly support new-file patches using unified diff hunks such as @@ -0,0 +1,N @@.
- Validate and reject absolute paths before attempting to apply patch hunks.
- Path-security validation must take precedence over file-content validation.
- Unit tests must use syntactically valid unified diff examples.
- All existing and newly generated unittest tests must pass.
