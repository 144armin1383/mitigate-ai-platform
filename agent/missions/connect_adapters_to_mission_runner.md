Mission: Connect Engine Adapters to Mission Runner

Goal

Connect the existing Engine Adapter Layer to Mission Runner with minimal and controlled changes.

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

- Do not completely rewrite Mission Runner.
- Modify only the minimum necessary sections.
- Preserve existing successful mission behavior.
- Preserve dependency injection.
- Preserve all current security checks.
- Preserve existing branch creation, file generation, validation, commit, and push behavior.
- Never merge automatically into main.

Adapter Construction

- MissionRunner must use RetryAdapter.
- MissionRunner must use ValidationAdapter.
- MissionRunner must use PatchAdapter.
- MissionRunner must use GitReviewAdapter.
- MissionRunner must not instantiate the wrapped concrete engines directly.
- ValidationAdapter must receive the active resolved repository root.
- PatchAdapter must receive the active resolved repository root.
- GitReviewAdapter must receive the active resolved repository root.
- RetryAdapter must receive the active max_attempts value.
- The default construction must use RetryAdapter(max_attempts=max_attempts).
- Dependency-injected adapters must be preserved and used exactly as provided.
- MissionRunner must never replace or recreate injected adapters.

Command-Line Behavior

- Preserve support for:

python -m ai.mission_runner mission_name

- Add support for:

python -m ai.mission_runner mission_name --max-attempts 3

- The default maximum attempts value must be 3.
- Values from 1 through 5 must be accepted.
- Invalid values must be handled through argparse.
- Invalid values must raise SystemExit.
- ValueError must not escape from command-line parsing.

Retry Behavior

- Retry generation, parsing, compilation, validation, and unittest failures when RetryAdapter permits it.
- Stop immediately when RetryAdapter returns blocked or non-retryable.
- Preserve the original mission text and exact deliverable allowlist on every attempt.
- Never expose secrets or unlimited logs in retry feedback.
- Provider authentication, authorization, billing, security, unsafe-path, and secret-exposure failures must stop immediately.

Validation Behavior

- ValidationAdapter must validate generated files and tests.
- Validation failure must prevent commit and push.
- A retryable validation failure may be retried.
- Successful validation must proceed to Git review.

Patch Behavior

- PatchAdapter must only perform unified-diff dry-run or apply operations.
- PatchAdapter must not be responsible for Git commit or push.
- Preserve path protections, rollback, and atomic update behavior.
- Never modify unrelated files.

Git Review Behavior

- GitReviewAdapter must run after successful validation and before commit or push.
- Risk low with recommendation approve may proceed.
- Risk high or critical must block commit and push.
- Recommendation manual_review or reject must block commit and push.
- A successful mission must never bypass Git review.

Cleanup Behavior

- New deliverables from a failed attempt must be removed.
- Pre-existing deliverables must be restored with their original bytes and permissions.
- Unrelated files must remain unchanged.
- Final failure must leave the working tree clean.
- Cleanup must only affect the exact deliverable allowlist.

Testing Policy

- Use Python standard library unittest only.
- Use unittest.mock for mocks.
- Never import or use pytest.
- Never add new testing dependencies.
- Never modify requirements.txt.
- Every generated Python file must pass py_compile.
- Multiline with statements must use valid Python 3.12 syntax.
- Tests must reflect the real public APIs in agent/ai/engine_adapters.py.

Adapter Test Requirements

- Inject fake adapters directly through the MissionRunner constructor.
- Preserve the exact injected adapter objects.
- Fake adapters may contain test counters.
- Production adapters must not be expected to contain test-only counters.
- Never expect PatchAdapter.commit, PatchAdapter.push, commit_calls, or push_calls.
- Test Git operations by mocking the existing commit-and-push boundary.
- Test successful completion on the first attempt.
- Test successful completion after retry.
- Test compilation, validation, and unittest retry behavior.
- Test provider and security failures stop immediately.
- Test Git review approval and blocking results.
- Test repository-root and max-attempts propagation.
- Test cleanup and restoration behavior.
- Test existing Mission Runner compatibility.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/ai/mission_runner.py
- agent/tests/test_mission_runner_adapters.py
