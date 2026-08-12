# MITIGATE Autonomous Development Reliability and Self-Healing

Mission ID: autonomous-self-healing-hardening-20260812200249
Request ID: autonomous-self-healing-hardening-20260812200249
Task Type: backend

## Mission Goal

Upgrade MITIGATE AI so routine autonomous engineering failures are
diagnosed, repaired, revalidated, checkpointed, and resumed by the Agent
without routine human SSH intervention.

The Agent must perform the repository inspection, architecture decision,
implementation, tests, validation, Git work, and durable reporting itself.

Human involvement must be reserved for genuinely sensitive approval
boundaries.

## Current Evidence

Recent autonomous development exposed real reliability gaps:

1. unittest validation failed but repair attempts did not receive sufficiently
   useful structured diagnostics;

2. Self-Healing repeated repairs until exhaustion without learning enough
   from previous failed attempts;

3. harmless trailing whitespace survived generation and required manual
   cleanup despite all behavioral tests passing;

4. a safety scan falsely interpreted a test-only mock reference to
   time.sleep as production sleep behavior;

5. failed generated files could be cleaned before useful diagnostic evidence
   was fully preserved;

6. shell / SSH disconnects must never be part of mission execution
   correctness;

7. branch/worktree residue and failed mission branches should be recoverable
   and inspectable automatically.

These are infrastructure reliability problems.

Fix them natively.

## Non-Negotiable Safety Principle

The Agent MUST improve diagnosis and repair.

The Agent MUST NOT make itself "more autonomous" by weakening safety.

Never automatically:

- disable repository validation
- suppress failed tests
- delete failing tests simply to pass validation
- weaken path allowlists
- weaken protected-Core controls
- disable checkpointing
- disable idempotent execution
- disable audit logs
- bypass human approval boundaries
- force-push main
- rewrite Git history
- delete user work
- mutate production data to make tests pass
- expose credentials or secrets
- reduce security checks
- install or activate Ruflo
- introduce mandatory external runtime dependencies
- become dependent on one model/provider

If safe repair requires one of those actions:

fail closed,
preserve evidence,
produce a precise escalation report,
and request human approval.

## Autonomous Repair Classification

Inspect existing:

- mission runner
- autonomous controller
- validation engine
- self-healing / repair loop
- failure capture
- checkpoint store
- MissionQueue
- execution reporting
- lifecycle dispatch
- retry classification
- retry budgets
- Git branch/worktree management
- repository guardrails

Create or extend a deterministic repair taxonomy including at minimum:

### Automatically repairable

- trailing whitespace
- deterministic formatting defects
- safe generated-file syntax defects
- straightforward unittest assertion failures where diagnostic evidence
  identifies the defect
- missing required report fields
- safe incomplete generated artifacts
- stale temporary worktree cleanup
- stale temporary branch recovery
- interrupted mission continuation
- transient provider failure
- retryable model/API failure
- deterministic validation mismatch
- safe false-positive validation where the difference between test code and
  production behavior can be proven structurally

### Human escalation required

- protected Core modification that is not already explicitly authorized
- destructive production operation
- security boundary change
- compliance boundary change
- secret/credential handling change
- database destructive migration
- Git history rewrite
- infrastructure replacement
- unresolved ambiguity with material operational risk
- exhausted bounded repair budget

## Diagnostic Capture Requirement

A repair attempt must receive the useful diagnostic evidence from the
previous validation attempt.

Capture sanitized structured information including where available:

- validation command
- return code
- failed test names
- assertion/error class
- bounded stdout
- bounded stderr
- traceback summary
- changed files
- validation phase
- repair attempt number
- previous repair decision
- previous repair result

Do not leak secrets.

Do not persist unbounded command output.

Diagnostics must be useful enough that repair attempt N+1 can learn from
attempt N.

## Failure Artifact Preservation

Before failed generated files are cleaned or worktrees are reset, preserve a
durable bounded failure artifact containing:

- mission_id
- execution_id
- attempt
- failing validation
- sanitized diagnostics
- generated file list
- diff summary
- repair classification
- repair recommendation
- checkpoint reference
- timestamp

Failure evidence must survive:

- worker restart
- SSH disconnect
- mission cleanup

## Bounded Self-Healing

No infinite loops.

Use bounded deterministic repair budgets.

Repair state must be durable.

A restart must not reset the repair budget.

Each attempt must know:

- total repair budget
- attempts used
- attempts remaining
- previous failure class
- previous proposed repair
- previous validation result

Repeated identical repairs without new evidence must be detected and stopped.

## Validation Repair Pipeline

Implement a safe pipeline conceptually equivalent to:

generate
-> validate
-> capture diagnostics
-> classify
-> repair
-> validate again
-> checkpoint
-> continue

If validation succeeds:

continue normal mission delivery.

If repair budget is exhausted:

preserve all evidence,
mark blocked/exhausted correctly,
produce actionable escalation.

## Formatting Repair

Simple deterministic repository hygiene such as trailing whitespace should
be corrected automatically before final validation.

Do not require a model call where a deterministic local repair is sufficient.

## False-Positive Guardrail Handling

Do NOT weaken guardrails.

Improve guardrail evaluation so test-only references are not automatically
treated as production behavior where this can be proven safely.

Example:

a unit test mocking time.sleep must not be equivalent to production code
calling time.sleep.

This must be solved through scope-aware validation, not guardrail removal.

## Git / Worktree Reliability

Autonomous missions must safely manage:

- mission branches
- worktrees
- interrupted worktrees
- stale local branches
- unpushed validated commits
- failed repair branches

Do not delete potentially valuable failed work until durable diagnostic
evidence exists.

Never touch unrelated user branches.

Never force-push main.

## SSH Independence

Mission correctness must never depend on an interactive PuTTY/SSH session.

Existing background worker and durable checkpoint architecture should remain
the execution authority.

Long-running autonomous work must survive interactive session loss.

Do not create a second worker runtime.

## Provider Independence

Self-healing must remain model/provider independent.

Provider-specific error adapters are allowed only behind native normalized
contracts.

No mandatory Ruflo dependency.

No mandatory single-vendor AI dependency.

## Existing Runtime Preservation

Preserve:

- MissionQueue authority
- retry_backoff_policy
- durable_checkpointing
- flowspec_v1
- idempotent_execution
- current worker behavior
- runtime API behavior
- technology registry history
- checkpoint history
- existing security boundaries

## Core Change Policy

First attempt implementation through safe extension points.

If a protected Core modification is truly required to make diagnostic
propagation operational:

DO NOT bypass protection.

Produce an explicit Core Change Proposal containing:

- exact file
- exact class/function
- reason
- smallest possible change
- tests
- rollback
- security impact
- compatibility impact

If repository policy already has an authorized and audited Core-change
workflow, use that workflow only if it preserves all existing protections.

Never disable CORE_PATH_LOCKED merely to proceed.

## Tests

Implement comprehensive standard-library unittest coverage.

Include at minimum:

- sanitized unittest diagnostics propagate into repair
- failed test name preserved
- bounded stdout/stderr capture
- secret redaction
- trailing whitespace deterministic repair
- formatting repair does not modify semantics
- repeated identical repair detection
- bounded repair exhaustion
- durable repair budget
- restart-safe repair state
- failure artifact preservation
- test-only sleep mock not treated as production sleep
- real production sleep remains detectable
- transient provider classification
- non-retryable failure classification
- worktree recovery
- branch recovery
- no force push
- no main history rewrite
- no guardrail weakening
- no checkpoint weakening
- no idempotency weakening
- provider independence
- SSH independence contract

Run targeted tests.

Then run the complete repository test suite.

Run git diff --check.

## Deliverables

The Agent must determine the smallest safe native architecture.

Prefer extension components.

Create a durable report at:

docs/architecture/autonomous-self-healing-hardening.json

The report must include:

- mission_id
- architecture
- implementation_status
- operational_status
- files_created
- files_modified
- core_change_required
- exact_core_change_target
- diagnostic_capture_status
- failure_artifact_status
- bounded_repair_status
- restart_recovery_status
- git_recovery_status
- formatting_repair_status
- guardrail_scope_awareness_status
- provider_independence
- external_runtime_dependency
- full_test_result
- production_runtime_data_changed
- safety_boundaries_preserved
- remaining_work

## Success Criteria

Routine recoverable autonomous engineering failures can normally be:

diagnosed
-> repaired
-> revalidated
-> resumed

without human SSH intervention.

Sensitive changes still fail closed and request human approval.

Infrastructure safety is preserved.

No Ruflo runtime dependency is introduced.

## Git Delivery

Use the Agent mission branch.

Commit validated changes.

Push the branch.

If all repository safety conditions for automatic merge are satisfied,
use the existing safe merge path.

Otherwise leave the validated branch ready for human review with a precise
report.

Never force push.
