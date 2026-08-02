Mission: Build Engine Adapter Layer

Goal

Create a compatibility adapter layer between the existing Mission Runner and the existing Retry, Validation, Patch, and Git Review engines.

Existing Components

- agent/ai/mission_runner.py
- agent/ai/retry_engine.py
- agent/validators/validation_engine.py
- agent/git/patch_engine.py
- agent/git/review_engine.py

Requirements

- Do not rewrite Mission Runner
- Do not change existing public APIs
- Create small typed adapters around existing engines
- Keep each adapter side-effect free unless the wrapped engine already performs that action
- Preserve all existing security behavior
- Preserve all existing tests
- Python 3.12 compatible
- Fully typed Python
- English source code and comments only
- Use Python standard library unittest only
- Do not add dependencies
- Do not modify requirements.txt

Retry Adapter

- Wrap RetryEngine
- Construct RetryConfiguration correctly
- Construct FailureContext correctly
- Expose a simple evaluate method
- Return a normalized result containing retryable, blocked, reason, feedback, attempts_used, and attempts_remaining
- Preserve secret redaction and truncation behavior
- Never retry non-retryable failures

Validation Adapter

- Wrap ValidationEngine
- Accept repository root, selected files, and run_tests
- Return a normalized structured result
- Include success, file validation counts, unittest counts, errors, and logs
- Never modify repository files

Patch Adapter

- Wrap PatchEngine
- Accept unified diff input and repository root
- Support dry-run and apply modes
- Return normalized success, changed files, errors, and logs
- Preserve all path protections and rollback behavior

Git Review Adapter

- Wrap GitReviewEngine
- Accept repository root, base ref, and target ref
- Return normalized risk level, recommendation, changed files, findings, validation errors, and logs
- Never modify Git state

Unified Result Models

Create typed models for:

- AdapterStatus
- RetryAdapterResult
- ValidationAdapterResult
- PatchAdapterResult
- GitReviewAdapterResult

Testing Requirements

- Test correct construction of RetryEngine
- Test retryable and blocked retry decisions
- Test ValidationEngine success and failure normalization
- Test PatchEngine dry-run and apply normalization
- Test GitReviewEngine low, high, and critical risk normalization
- Test adapter error handling
- Test deterministic dictionary serialization
- Test that adapters do not modify unrelated files
- Test that existing engine behavior remains unchanged
- All existing and newly generated unittest tests must pass

Deliverables

agent/ai/engine_adapters.py
agent/tests/test_engine_adapters.py
