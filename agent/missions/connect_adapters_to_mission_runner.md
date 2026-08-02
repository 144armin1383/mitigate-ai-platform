Mission: Connect Engine Adapters to Mission Runner

Goal

Integrate the existing Engine Adapter Layer into the existing Mission Runner with minimal, controlled changes.

Existing Components

- agent/ai/mission_runner.py
- agent/ai/engine_adapters.py
- agent/ai/retry_engine.py
- agent/validators/validation_engine.py
- agent/git/patch_engine.py
- agent/git/review_engine.py
- agent/ai/code_generator.py
- agent/ai/prompt_builder.py

Core Requirement

Do not rewrite Mission Runner.

Modify only the smallest necessary sections so Mission Runner uses the existing adapters through dependency injection and preserves all current behavior.

Integration Requirements

- Import and use RetryAdapter
- Import and use ValidationAdapter
- Import and use PatchAdapter
- Import and use GitReviewAdapter
- Do not instantiate RetryEngine, ValidationEngine, PatchEngine, or GitReviewEngine directly inside Mission Runner
- Preserve all existing mission loading, branch creation, generation, allowlist validation, file writing, test execution, commit, and push behavior
- Preserve existing public functions and command-line behavior
- Preserve existing one-attempt mission behavior
- Do not automatically merge into main
- Do not change mission file format
- Do not add new dependencies
- Do not modify requirements.txt
- Python 3.12 compatible
- Fully typed Python
- English source code and comments only
- Use Python standard library unittest only

Retry Integration

- Use RetryAdapter for retry decisions and corrective feedback
- Default maximum attempts must be 3
- Support --max-attempts with a valid range from 1 to 5
- Retry only retryable generation, parsing, compilation, validation, and unittest failures
- Stop immediately on blocked or non-retryable failures
- Preserve the original mission text and deliverable allowlist on every attempt
- Never expose secrets or unbounded logs in retry feedback

Validation Integration

- Use ValidationAdapter for generated-file and test validation
- Validation failure must prevent commit and push
- Structured validation errors must be passed safely to RetryAdapter
- Never bypass validation

Patch Integration

- Use PatchAdapter only where unified diff application is required
- Preserve dry-run, path protection, atomic update, backup, and rollback behavior
- Never allow paths outside the repository
- Never modify unrelated files

Git Review Integration

- Use GitReviewAdapter before commit and push
- High-risk and critical findings must prevent automatic commit and push
- A manual_review or reject recommendation must stop the mission safely
- Low-risk approve results may proceed
- Never modify Git state through the review adapter

Compatibility Requirements

- Keep python -m ai.mission_runner mission_name working
- Add support for python -m ai.mission_runner mission_name --max-attempts 3
- Existing successful missions must continue to work
- Existing tests must remain unchanged unless a narrowly scoped compatibility update is necessary
- Do not remove existing safety checks
- Do not weaken forbidden-content checks
- Do not weaken path allowlisting
- Do not use git reset, git clean, checkout, restore, or automatic merge operations

Failure Cleanup

- Failed attempts must restore any pre-existing deliverable content and permissions
- New deliverables from failed attempts must be removed
- Unrelated files must remain untouched
- Final failure must leave the working tree clean
- All cleanup must operate only on the exact deliverable allowlist

Testing Requirements

- Test adapter construction and dependency injection
- Test success on first attempt
- Test success after one retry
- Test invalid JSON retry
- Test compilation failure retry
- Test validation failure retry
- Test unittest failure retry
- Test security failure stops immediately
- Test provider authentication and billing failures stop immediately
- Test Git Review high-risk result blocks commit
- Test Git Review critical result blocks commit
- Test Git Review approve result allows completion
- Test cleanup of new deliverables
- Test restoration of pre-existing deliverables
- Test unrelated files remain unchanged
- Test default max attempts equals 3
- Test command-line limits from 1 through 5
- Test final failure leaves the repository clean
- Test existing mission behavior remains compatible
- All existing and newly generated unittest tests must pass

Deliverables

agent/ai/mission_runner.py
agent/tests/test_mission_runner_adapters.py
