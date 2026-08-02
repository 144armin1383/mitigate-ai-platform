Mission: Connect Engine Adapters to Mission Runner

Goal

Integrate the existing Engine Adapter Layer into the existing Mission Runner with the smallest possible changes.

Existing Components

- agent/ai/mission_runner.py
- agent/ai/engine_adapters.py
- agent/ai/retry_engine.py
- agent/validators/validation_engine.py
- agent/git/patch_engine.py
- agent/git/review_engine.py
- agent/ai/code_generator.py
- agent/ai/prompt_builder.py

Core Requirements

- Do not rewrite Mission Runner.
- Modify only the minimum code necessary.
- Preserve all existing behaviour.
- Preserve backwards compatibility.

Adapter Integration

- Use RetryAdapter.
- Use ValidationAdapter.
- Use PatchAdapter.
- Use GitReviewAdapter.

Construction Rules

- ValidationAdapter must receive the active repository root.
- MissionRunner(repo_root=...) must pass the resolved repository root into ValidationAdapter.
- Do not instantiate ValidationEngine directly.
- Do not instantiate PatchEngine directly.
- Do not instantiate GitReviewEngine directly.
- Do not instantiate RetryEngine directly.

CLI Requirements

- Preserve all existing CLI behaviour.
- Support:

python -m ai.mission_runner mission_name

and

python -m ai.mission_runner mission_name --max-attempts 3

- --max-attempts must accept only values from 1 through 5.
- Invalid values must be handled using argparse parser errors.
- Invalid values must raise SystemExit.
- Never propagate ValueError directly from CLI parsing.

Retry Behaviour

- Retry only retryable failures.
- Never retry security violations.
- Never retry provider authentication failures.
- Never retry provider billing failures.
- Preserve original mission text.
- Preserve deliverable allowlist.
- Preserve cleanup behaviour.

Validation Behaviour

- ValidationAdapter performs validation.
- Validation failure blocks commit.
- Validation failure blocks push.

Git Review Behaviour

- GitReviewAdapter runs before commit.
- High risk blocks commit.
- Critical risk blocks commit.
- Approve allows completion.

Security

- Never weaken forbidden-content validation.
- Never weaken allowlist validation.
- Never allow paths outside repository.
- Never use git reset.
- Never use git clean.
- Never use git checkout.
- Never use git restore.
- Never auto merge into main.

Compatibility

- Existing successful missions must continue working.
- Existing tests must remain compatible.

Deliverables

agent/ai/mission_runner.py

agent/tests/test_mission_runner_adapters.py

Testing

- Adapter construction
- Dependency injection
- ValidationAdapter receives repo_root
- Retry success
- Retry after compilation failure
- Retry after unittest failure
- Retry after validation failure
- Security failure stops immediately
- Provider authentication stops immediately
- Git review blocks commit
- Git review approve completes mission
- Existing behaviour preserved
- Existing tests preserved
- CLI parsing
- Invalid --max-attempts raises SystemExit
- All tests pass

Acceptance Criteria

- ValidationAdapter is constructed using repo_root.
- argparse validates max-attempts.
- No ValueError escapes from CLI parsing.
- All existing and generated unittest tests pass.
- Working tree remains clean after failures.

Mandatory Testing Policy

- Use Python standard library unittest only.
- Never import pytest.
- Never use pytest fixtures, decorators, assertions, raises, monkeypatch, parametrize, or tmp_path.
- Never add pytest or any new test dependency.
- Never modify requirements.txt.
- Generated test files must be directly compatible with unittest discovery.
- The literal statement import pytest must never appear in generated files.
- All existing and newly generated unittest tests must pass.

Python Syntax Acceptance Criteria

- Every generated Python file must pass python -m py_compile before unittest execution.
- Multiline with statements must use valid parenthesized context-manager syntax or nested with statements.
- Never continue a with statement after a comma unless all context managers are enclosed in parentheses.
- Prefer contextlib.ExitStack when several mock.patch context managers are required.
- Generated unittest code must be syntactically valid on Python 3.12.
- All existing and newly generated unittest tests must pass.
