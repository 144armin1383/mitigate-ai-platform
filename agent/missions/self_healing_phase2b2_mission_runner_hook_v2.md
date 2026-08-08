Mission: Self-Healing Phase 2B-2 Mission Runner Hook v2

CORE_MAINTENANCE_APPROVED

Goal

Integrate the existing MissionRepairAdapter into Mission Runner with the smallest
possible Core change.

Mission Runner must remain the top-level mission lifecycle owner, while all
bounded repair retry behavior remains delegated to:

MissionRepairAdapter
→ IntegrationCoordinator

Do not create another retry loop in Mission Runner.

# Deliverables

- agent/ai/mission_runner.py
- agent/tests/test_mission_runner_self_healing.py

# End Deliverables

Architecture

Current normal flow:

generation
→ write generated files
→ validate generated files
→ commit and push

New flow:

generation
→ write generated files
→ validate generated files
→ if validation succeeds:
     commit and push normally
→ if validation fails with a repairable validation failure:
     invoke MissionRepairAdapter
     → generate repair
     → apply repair
     → revalidate through IntegrationCoordinator
     → maximum 3 attempts total
→ if repair succeeds:
     commit and push
→ if exhausted or blocked:
     Mission fails safely

Mission Runner must NOT implement its own repair-attempt loop.

IntegrationCoordinator remains the single retry authority.

Core Safety

Preserve all existing:

- clean repository requirement
- main branch requirement
- isolated mission branch creation
- deliverable allowlist
- generated-file validation
- Core Lock validation
- canonical test protection
- full unittest validation
- atomic writes
- commit/push behavior
- failed mission cleanup

Do not weaken any existing Core Protection behavior.

MissionRepairAdapter

Import and use:

agent.repair.mission_adapter.MissionRepairAdapter

The adapter must receive injected callbacks only.

Validation Callback

Create a callback that runs the existing:

validate_generated_files(...)

behavior and converts success/failure into adapter-compatible outcome.

Do not duplicate test-running logic elsewhere.

Generation Callback

Repair generation must use the existing AI generation infrastructure.

The repair request must be translated into a repair-specific generation prompt
that includes only:

- mission objective
- safe failure summary
- attempt number
- allowed paths
- denied paths
- validation requirement

Do not include raw unsanitized exception output.

The generated repair must still pass:

validate_generated_file
write protection
Core Lock protection
deliverable allowlist

Apply Callback

Applying a repair must reuse the existing safe generated-file validation/write
path.

Do not bypass:

validate_generated_file
validate_mission_write
Core Lock
deliverable allowlist

Repair output may only modify original mission deliverables.

No automatic expansion of allowed paths.

Failure Classification

Self-Healing may be invoked for repairable generated-code validation failures,
including:

- Python compilation failure
- unittest failure
- generated implementation validation failure

Self-Healing must NOT proceed for:

- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- CORE_PROTECTION_UNAVAILABLE
- repository safety violation
- unsafe deliverable path
- provider authentication failure
- provider unavailable
- forbidden generated content
- mission path escape
- branch safety failure
- Git safety failure

These must remain terminal.

Failure Cleanup

If Self-Healing becomes blocked or exhausted:

- existing recover_failed_mission behavior must still run
- no failed generated files remain
- no commit is created
- no push occurs

Successful Repair

After successful repair and revalidation:

- use the existing commit_and_push path exactly once
- do not create intermediate repair commits
- do not push failed attempts
- final branch contains only validated final mission output

Attempt Limit

Exactly 3 repair attempts maximum.

This limit must come from MissionRepairAdapter / IntegrationCoordinator.

Mission Runner itself must contain no:

for attempt in ...
while retry ...
manual retry counter loop

Security

Never expose raw secret-bearing validation diagnostics to the generation provider.

Use safe summarized failure text.

Do not weaken forbidden-content scanning.

Do not weaken Core Lock.

Do not emit privileged maintenance markers into generated code.

Tests

Use unittest only.

Create zero-skip tests covering at least:

1. normal mission validation success does not invoke repair adapter
2. compilation failure invokes self-healing
3. unittest failure invokes self-healing
4. repair succeeds after one attempt
5. repair succeeds after second attempt
6. repair succeeds after third attempt
7. no fourth repair attempt
8. exhausted repair fails mission
9. blocked Core failure never invokes generation repair
10. canonical test lock never invokes repair
11. Core protection unavailable never invokes repair
12. forbidden generated content never invokes repair
13. provider unavailable never invokes repair
14. successful repair commits once
15. successful repair pushes once
16. failed repair commits zero times
17. failed repair pushes zero times
18. failed repair triggers recovery cleanup
19. repair generation receives only allowed paths
20. denied paths preserved
21. repair cannot add new deliverable
22. repair write still passes Core Lock
23. validation callback reuses existing validation function
24. Mission Runner contains no independent retry loop
25. existing normal mission behavior remains unchanged
26. raw secret validation text is not passed to repair generation
27. full repository tests remain passing

Acceptance

- new Mission Runner self-healing tests: zero failures/errors/skips
- Mission Adapter tests remain passing
- Phase 2A tests remain passing
- Phase 1 tests remain passing
- Core Protection tests remain passing
- Portable Recovery tests remain passing
- full repository unittest suite remains passing

Do not modify:

- agent/repair/mission_adapter.py
- agent/repair/integration.py
- agent/repair/repair_loop.py
- agent/policies/core_protection.py
- agent/policies/core_lock_manifest.json

TEST CONTRACT CORRECTION — RETRY LOOP DETECTION

The previous no-independent-retry-loop test was too broad.

Mission Runner already contains legitimate ordinary loops for:

- parsing mission lines
- validating generated entries
- checking forbidden fragments
- processing generated files
- printing generated outputs

These loops are not self-healing retry loops.

The test MUST NOT reject generic for/while statements anywhere in mission_runner.py.

Instead, verify specifically that Mission Runner does not implement its own
self-healing attempt lifecycle.

The test should reject only patterns semantically equivalent to:

- a local repair-attempt counter
- a local range loop over repair attempts
- a while loop controlling self-healing retries
- manual increment of self-healing retry state
- independent retry termination logic

Behaviorally, repair attempts must be controlled only through:

MissionRepairAdapter
→ IntegrationCoordinator

Ordinary pre-existing loops must remain allowed.

All other Phase 2B-2 requirements remain unchanged.
