Mission: Integrate Automatic Retry Engine into Mission Runner

Goal

Integrate the existing Automatic Retry Engine into the existing autonomous Mission Runner so retryable mission failures can be corrected automatically without manual intervention.

Existing Components

- agent/ai/mission_runner.py
- agent/ai/retry_engine.py
- agent/ai/code_generator.py
- agent/ai/prompt_builder.py
- agent/validators/validation_engine.py
- agent/git/patch_engine.py
- agent/git/review_engine.py

Requirements

- Integrate RetryEngine into the Mission Runner execution flow
- Default maximum attempts must be 3
- Allow maximum attempts to be configured through a command-line option
- Keep all attempts on the same isolated mission branch
- Preserve the original mission requirements on every attempt
- Preserve the exact deliverable allowlist on every attempt
- Capture generation, JSON parsing, deliverable validation, compilation, validation, and unittest failures
- Convert failures into typed FailureContext objects
- Ask RetryEngine whether each failure is retryable
- Build corrective feedback through RetryEngine
- Include corrective feedback in the next OpenAI generation request
- Remove all generated deliverable files from a failed attempt before retrying
- Rescan the repository before every new generation attempt
- Never remove or modify committed repository files during retry cleanup
- Never use git reset, git clean, checkout, restore, or branch switching for retry cleanup
- Retry cleanup must only affect the exact mission deliverable allowlist
- Stop immediately when RetryEngine marks a failure as blocked or non-retryable
- Stop immediately on security-policy, unsafe-path, dirty-repository, Git-integrity, provider-authentication, authorization, billing, or unavailable-provider failures
- Stop when the configured maximum attempts are exhausted
- Commit and push only after all compilation, validation, and unittest checks pass
- Produce a deterministic final retry report
- Log every attempt number, failure category, retry decision, and final status
- Never automatically merge into main
- Maintain compatibility with existing successful one-attempt missions
- Python 3.12 compatible
- Fully typed Python
- English source code and comments only
- Use Python standard library unittest only
- Do not add new dependencies
- Do not modify requirements.txt

Command-Line Behavior

Support:

python -m ai.mission_runner mission_name

and:

python -m ai.mission_runner mission_name --max-attempts 3

Rules:

- The default must be 3 attempts
- Reject max-attempts below 1
- Apply a safe upper limit of 5 attempts
- Reject max-attempts above 5
- Existing mission-name behavior must remain compatible

Retry Prompt Requirements

Every retry request must include:

- The original mission text
- The original execution plan
- The exact deliverable allowlist
- The previous failure category
- A redacted and size-limited error summary
- Failed test names where available
- Clear corrective instructions
- A statement that all previous mission constraints still apply
- A requirement to return the complete JSON files payload again

The retry request must never include:

- API keys
- Tokens
- Passwords
- Credentials
- Environment-variable values
- .env contents
- Unrelated logs
- Unbounded error output

Failure Handling

Retryable:

- Invalid AI JSON
- Missing required deliverables
- Generated Python syntax errors
- Compilation failures
- Deterministic validation failures
- Unittest failures
- Unittest errors

Non-Retryable:

- Security-policy violations
- Forbidden generated content
- Unsafe or escaping file paths
- Secret exposure
- Dirty repository state
- Git repository or branch integrity failures
- Provider authentication failures
- Provider authorization failures
- Provider billing or quota failures
- Provider unavailable failures
- Invalid Mission Runner configuration

Cleanup Requirements

- Before each retry, delete only files listed in the mission deliverable allowlist that were generated during the current mission run
- Never delete the mission file
- Never delete existing committed versions of deliverable files without restoring their original content
- If a deliverable existed before the mission, preserve its original bytes and permissions and restore it before retrying or failing
- If a deliverable was new, remove it before retrying or failing
- Cleanup must be atomic and deterministic
- Final failure must leave the working tree clean

Testing Requirements

- Test success on the first attempt
- Test success after one retry
- Test invalid JSON followed by successful retry
- Test compilation failure followed by successful retry
- Test unittest failure followed by successful retry
- Test maximum-attempt exhaustion
- Test non-retryable security failure stops immediately
- Test provider authentication failure stops immediately
- Test cleanup of newly generated deliverables between attempts
- Test restoration of pre-existing deliverable files between attempts
- Test preservation of file permissions where supported
- Test that unrelated files are never changed or deleted
- Test final failure leaves the working tree clean
- Test default max-attempts equals 3
- Test CLI rejects values below 1 and above 5
- Test existing one-attempt successful mission behavior remains compatible
- All existing and newly generated unittest tests must pass

Additional Acceptance Criteria

- Absolute paths that resolve inside the repository root are valid.
- Normalize repository-internal absolute paths into repository-relative paths before validation.
- Reject only absolute paths that resolve outside the repository root.
- Preserve all existing path traversal protections.
- Existing retry cleanup behavior must remain unchanged.
- All existing and newly generated unittest tests must pass.
Deliverables

agent/ai/mission_runner.py
agent/tests/test_mission_runner_retry.py
