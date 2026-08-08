Mission: Self-Healing Phase 2B-2 Mission Runner Hook v3

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

PHASE 2B-2 V3 — RUNTIME IMPORT AND TESTABILITY CONTRACT

This v3 supersedes v2 for MissionRepairAdapter import behavior.

MissionRepairAdapter MUST be available as a MODULE-LEVEL attribute of
agent/ai/mission_runner.py.

Tests must be able to patch:

agent.ai.mission_runner.MissionRepairAdapter

Do NOT import MissionRepairAdapter only inside run_mission or another function.

RUNTIME IMPORT COMPATIBILITY

Mission Runner is used in two package contexts:

1. From inside agent/:

python -m ai.mission_runner

where repair is available as a top-level package.

2. From repository-root unittest/import contexts:

agent.ai.mission_runner

where agent.repair is available.

The module-level import must support both contexts safely.

Use a narrow compatibility import pattern.

Preferred semantic behavior:

try the normal runtime import:

from repair.mission_adapter import MissionRepairAdapter

If and only if the top-level repair package itself is unavailable, fall back to:

from agent.repair.mission_adapter import MissionRepairAdapter

Do NOT suppress unrelated ModuleNotFoundError exceptions raised from inside
mission_adapter or its dependencies.

Do NOT use a broad except Exception.

MissionRepairAdapter must exist in mission_runner module globals after import.

TEST REQUIREMENTS

Add explicit tests proving:

1. mission_runner module exposes MissionRepairAdapter
2. patch("agent.ai.mission_runner.MissionRepairAdapter") succeeds
3. Mission Runner import works in repository-root test context
4. existing runtime invocation remains compatible with:
   python -m ai.mission_runner
5. normal successful mission does not instantiate repair adapter
6. repairable validation failure does instantiate repair adapter
7. terminal Core/security failures do not instantiate repair adapter

SELF-HEALING HOOK

Keep the Phase 2B-2 architecture:

normal generation
→ safe write
→ validation

If validation passes:
→ existing commit_and_push exactly once

If validation fails with a repairable generated-code validation failure:
→ MissionRepairAdapter
→ IntegrationCoordinator owns bounded retries
→ repair generation
→ safe repair apply
→ revalidation

Mission Runner MUST NOT contain its own repair retry loop.

REPAIR GENERATION

Repair generation must reuse the existing CodeGenerator/openai_provider path.

The repair-generation callback must receive only safe bounded context:

- mission objective
- sanitized failure summary
- repair attempt number
- original allowed deliverables
- denied paths
- validation requirement

Do not send raw CalledProcessError output, raw test logs containing credentials,
or raw exception objects to the provider.

REPAIR APPLY

Repair output must pass through the same safety boundaries as initial generation:

- parse_generation
- validate_generated_file
- deliverable allowlist
- Core Lock validation
- forbidden-content checks
- atomic file write

Repair generation may modify only the original mission deliverables.

No new deliverables may be introduced.

TERMINAL FAILURES

Do not invoke Self-Healing for:

- CORE_PATH_LOCKED
- CANONICAL_TEST_LOCKED
- CORE_PROTECTION_UNAVAILABLE
- forbidden generated content
- unsafe or escaping deliverable path
- repository not clean
- wrong starting branch
- mission path escape
- provider unavailable
- provider authentication intervention
- Git safety failure

VALIDATION FAILURE

Compilation and unittest failures after safe file writing are repairable.

Do not treat all exceptions as repairable.

RETRY AUTHORITY

Exactly one retry authority must exist:

MissionRepairAdapter
→ IntegrationCoordinator

Mission Runner must not contain:

- repair_attempt loops
- retry counters
- while-retry logic
- manual three-attempt orchestration

Existing unrelated for-loops in mission_runner.py are valid and must remain allowed.

SUCCESS / FAILURE

On successful Self-Healing:

- final files must pass full validation
- commit_and_push runs once
- no intermediate failed repair commit
- no failed repair push

On blocked or exhausted Self-Healing:

- raise MissionError
- outer existing failure handler runs
- recover_failed_mission remains authoritative
- no commit
- no push

TEST SOURCE CONTRACT

Use unittest only.
No pytest.
No skips.

Do not create self-contradictory source-scanning tests.

Do not reject ordinary existing for-loops.

Do not include repository-forbidden dangerous call literals in generated test
source.

ACCEPTANCE

- new Mission Runner Self-Healing tests: zero failures/errors/skips
- MissionRepairAdapter exposed at module scope
- runtime package compatibility preserved
- adapter tests remain passing
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
