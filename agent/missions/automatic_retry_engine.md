Mission: Build Production Automatic Retry Engine

Goal

Implement a safe Automatic Retry Engine for the MITIGATE AI autonomous development platform.

The engine must analyze failed generation, compilation, validation, and unittest results and prepare structured corrective feedback for a subsequent AI generation attempt.

Requirements

- Support a configurable maximum number of attempts
- Default maximum attempts must be 3
- Never allow an unlimited retry loop
- Track every attempt independently
- Record attempt number, failure category, error summary, test failures, validation failures, and timestamps
- Classify failures as generation, parsing, policy, compilation, validation, testing, provider, Git, or unknown
- Determine whether a failure is retryable
- Generate deterministic corrective instructions for retryable failures
- Preserve the original mission requirements in every retry
- Include only relevant error context in corrective instructions
- Limit stored error output to a configurable safe size
- Avoid sending secrets, environment values, tokens, credentials, or API keys to an AI provider
- Detect and redact common secret patterns
- Stop immediately on security-policy violations
- Stop immediately on dirty repository state
- Stop immediately on authentication, authorization, billing, or unavailable-provider failures
- Stop when maximum attempts are exhausted
- Return a structured final retry report
- Support successful completion before maximum attempts
- Python 3.12 compatible
- Fully typed Python
- English source code and comments only
- Produce detailed logs
- Use Python standard library unittest only
- Do not add new dependencies

Retry Policy

- Compilation failures are retryable
- Deterministic validation failures are retryable
- Unittest failures and errors are retryable
- Invalid AI JSON output is retryable
- Missing required deliverables are retryable
- Security-policy violations are not retryable
- Unsafe path violations are not retryable
- Secret exposure is not retryable
- Dirty repository state is not retryable
- Git branch or repository integrity failures are not retryable
- Provider authentication and billing errors are not retryable
- Maximum retry attempts must never exceed the configured limit

Safety Rules

- Never modify repository files directly
- Never run Git commands
- Never commit, merge, push, reset, clean, checkout, or switch branches
- Never execute generated code
- Never execute arbitrary shell commands
- Never read .env contents
- Never reveal secret values
- Never automatically merge into main
- Never silently ignore failed validation
- Never declare success unless validation and tests succeeded

Required Models

Create typed models for:

- RetryConfiguration
- FailureCategory
- FailureContext
- RetryAttempt
- RetryDecision
- RetryReport

Required Public Behavior

- Evaluate a failure and determine whether it is retryable
- Build safe corrective feedback for the next AI attempt
- Record successful and failed attempts
- Report attempts used and attempts remaining
- Produce a final status of succeeded, exhausted, blocked, or failed
- Serialize reports into deterministic dictionaries

Testing Requirements

- Test successful completion on the first attempt
- Test successful completion after one retry
- Test maximum-attempt exhaustion
- Test that security failures are never retried
- Test that provider authentication and billing failures are never retried
- Test that unittest failures are retryable
- Test that compilation failures are retryable
- Test secret redaction
- Test error-output truncation
- Test deterministic report serialization
- Test that the configured maximum attempt count is always enforced
- All existing and newly generated unittest tests must pass

Deliverables

agent/ai/retry_engine.py
agent/tests/test_retry_engine.py

Additional Acceptance Criteria

- safe_error_bytes must support small positive values used in tests, including 50.
- Reject only zero or negative safe_error_bytes values.
- Truncation must be deterministic and must never exceed the configured byte limit.
- Truncation must preserve valid UTF-8 output.
- Secret redaction must occur before truncation.
- All existing and newly generated unittest tests must pass.
