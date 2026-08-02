# Connect Adapters to Mission Runner

## Objective

Replace direct engine construction inside MissionRunner with the Engine Adapter Layer.

MissionRunner must communicate only through adapters and must never instantiate concrete engines directly.

The external behaviour of MissionRunner must remain unchanged.

---

## Acceptance Criteria

- MissionRunner must use CodeGeneratorAdapter.
- MissionRunner must use ValidationAdapter.
- MissionRunner must use PatchAdapter.
- MissionRunner must use GitReviewAdapter.
- MissionRunner must use RetryAdapter.
- No direct dependency on concrete engine implementations.
- Dependency Injection must remain supported.
- Existing retry behaviour must remain unchanged.
- Existing validation behaviour must remain unchanged.
- Existing patch behaviour must remain unchanged.
- Existing git review behaviour must remain unchanged.
- Existing public MissionRunner API must remain compatible.

---

## Deliverables

agent/ai/mission_runner.py

agent/tests/test_mission_runner_adapters.py

---

## Adapter Testing and Dependency Injection Acceptance Criteria

- Tests must inject fake or dummy adapters directly through the MissionRunner constructor.
- MissionRunner must preserve and use the exact injected adapter objects without replacing or recreating them.
- Never monkeypatch adapter classes after MissionRunner has already imported or instantiated them.
- Test doubles may define counters such as run_calls, review_calls, validation_calls, or apply_calls.
- Production RetryAdapter, PatchAdapter, ValidationAdapter and GitReviewAdapter must not expose test-only counters.
- Tests must never expect PatchAdapter.commit(), PatchAdapter.push(), PatchAdapter.commit_calls or PatchAdapter.push_calls because these are not public APIs.
- Existing Git commit and push behaviour must remain outside PatchAdapter.
- PatchAdapter must only perform patch apply and dry-run operations.
- Commit and push behaviour must be tested by mocking the existing commit boundary.
- Retry tests must inject a fake RetryAdapter returning deterministic retry decisions.
- Validation retry tests must inject a fake ValidationAdapter that fails once and then succeeds.
- Git review approval tests must inject a fake GitReviewAdapter returning risk=low and recommendation=approve.
- Git review rejection tests must inject a fake GitReviewAdapter returning risk=high, critical, reject or manual_review.
- Git review must execute after validation and before commit.
- Successful approval must produce a successful mission result.
- Retry after validation failure must succeed when validation later succeeds.
- Tests must use only unittest and unittest.mock.
- Generated tests must match the real public API of engine_adapters.py.
- All existing and newly generated unittest tests must pass.
