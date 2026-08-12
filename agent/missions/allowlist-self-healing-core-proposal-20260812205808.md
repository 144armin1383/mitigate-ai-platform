# MITIGATE Allowlist Self-Healing Core Change Proposal

Mission ID: allowlist-self-healing-core-proposal-20260812205808
Request ID: allowlist-self-healing-core-proposal-20260812205808
Task Type: documentation

## Objective

Perform a repository-grounded architecture analysis for the minimum safe
Core change required to make generated-path allowlist failures participate
in MITIGATE's bounded autonomous Self-Healing lifecycle.

This mission is PROPOSAL ONLY.

Do NOT modify production Python code.

Do NOT modify protected Core.

Do NOT implement the proposed change.

## Confirmed Existing State

The following native pure component already exists on main:

agent/repair/allowlist_recovery.py

It safely provides deterministic classification and recovery guidance for:

- outside_allowlist
- repository_escape
- absolute_path
- protected_core
- malformed_path
- repeated_invalid_path

It does NOT mutate allowlists.

It does NOT expand deliverables.

It does NOT write filesystem state.

## Confirmed Runtime Architecture

Inspect current main carefully.

Specifically inspect:

- agent/ai/mission_runner.py
- agent/repair/mission_adapter.py
- agent/repair/integration.py
- agent/repair/repair_loop.py
- agent/repair/failure_capture.py
- agent/repair/allowlist_recovery.py
- Core protection policy
- mission tests
- repair tests

Verify this architecture observation:

Generated file paths are currently validated inside the generated-file
write path.

A path outside mission deliverables raises a MissionError before the normal
subprocess-backed validation Self-Healing lifecycle is entered.

The current bounded Self-Healing integration handles generated code
validation failures such as Python compilation or unittest failures, but
path-policy rejection occurs earlier.

Determine whether this observation is correct from repository code.

## Primary Architecture Question

What is the SMALLEST safe change that makes:

Generated path outside allowlist

flow through:

classify_generated_path(...)
-> structured recovery evidence
-> bounded MissionRepairAdapter retry
-> regenerated complete deliverable set
-> existing validator re-check
-> normal mission continuation

while keeping the existing validator authoritative?

## Critical Safety Requirement

The proposed architecture MUST NOT:

- weaken validate_generated_file
- weaken write_generated_files safety
- broaden deliverables automatically
- mutate allowlists
- silently remap generated paths
- disable CORE_PATH_LOCKED
- suppress MissionError
- bypass validation
- create unlimited retry loops
- reset retry budgets
- disable checkpointing
- disable idempotent execution
- create another mission execution authority
- change production data
- force push
- add Ruflo runtime dependency
- add mandatory external runtime dependency

## Required Analysis

Determine exactly where the path-policy exception must be intercepted.

Compare at least these possibilities:

1. inside validate_generated_file
2. around write_generated_files
3. inside generation_callback / apply_callback
4. inside MissionRepairAdapter
5. through a new non-Core adapter
6. through a minimal protected Core integration hook

Explain why the selected design is the smallest safe option.

## Existing Validator Authority

The existing path validator must remain the final authority.

The classifier must not turn an invalid path into a valid path.

Instead the classifier should only create structured diagnostics that allow
the NEXT bounded model generation attempt to regenerate using exact mission
deliverables.

## Proposed Failure Flow

Design the exact expected control flow.

It should conceptually resemble:

initial generation
-> parse generation
-> attempt generated-file validation
-> path rejection detected
-> classify rejected path
-> create bounded structured repair evidence
-> invoke existing bounded repair authority
-> next generation receives exact allowed deliverables + rejected path +
   fingerprint + recovery instruction
-> generated output validated again by existing validator
-> continue only if valid

The proposal must identify who owns:

- retry state
- retry count
- repair budget
- path validation
- generation
- file writing
- checkpoint identity
- execution identity
- audit trail

There must be no duplicate authority.

## Repeated Invalid Path

Design how repeated equivalent path failures use the existing deterministic
fingerprint from allowlist_recovery.

Repeated ineffective attempts must consume the existing bounded repair budget
and eventually fail closed.

Do not create an additional independent retry counter unless absolutely
required.

## Diagnostic Requirements

The next repair attempt should receive bounded structured data including:

- rejected_path
- classification
- allowed_paths
- safely_repairable
- human_approval_required
- repeated_invalid_path
- fingerprint
- recovery_instruction

Do not expose secrets.

## Protected Core Assessment

Determine explicitly:

core_change_required = true / false

If true, identify exactly:

- file
- class/function
- approximate code region
- minimal behavior change
- why an external non-Core helper alone is insufficient

The preferred design should keep most logic in:

agent/repair/allowlist_recovery.py

or another existing non-Core repair component.

The protected Core change should ideally only route existing information
into the repair layer rather than own new business logic.

## Test Plan

Provide the exact test plan required before approving implementation.

Include at minimum:

- outside allowlist triggers bounded recovery
- next attempt receives exact deliverables
- valid generated path remains unchanged
- protected Core path fails closed
- traversal fails closed
- repeated invalid path is detected
- repair budget remains bounded
- existing unittest Self-Healing remains unchanged
- existing compilation Self-Healing remains unchanged
- validator remains authoritative
- no allowlist expansion
- no silent remapping
- checkpoint identity preserved
- idempotent execution preserved
- provider independence
- full existing test suite
- strict JSON report validation

## Rollback Plan

Specify exact rollback behavior if the implementation later causes problems.

Prefer a single-commit revert or isolated hook removal.

## Risk Assessment

Classify implementation risk:

- low
- medium
- high

Explain:

- runtime risk
- mission safety risk
- regression risk
- security risk
- rollback complexity

## Human Approval Boundary

The final proposal must state whether this change should require explicit
human approval before implementation.

Do not interpret this mission itself as approval to modify Core.

## Report

Create exactly:

docs/architecture/allowlist-self-healing-core-change-proposal.json

The report must contain:

- mission_id
- architecture_observation_confirmed
- current_failure_stage
- current_self_healing_entry_stage
- gap_confirmed
- recommended_design
- core_change_required
- exact_core_change_target
- exact_function_targets
- non_core_components_reused
- proposed_control_flow
- validator_authority
- retry_authority
- repair_budget_authority
- checkpoint_authority
- execution_authority
- audit_authority
- allowlist_mutation
- allowlist_expansion
- core_protection_weakened
- provider_independence
- external_runtime_dependency
- production_runtime_data_changed
- test_plan
- rollback_plan
- implementation_risk
- human_approval_required
- implementation_deliverables
- remaining_work

Required invariants:

validator_authority = "existing_generated_file_validator"
allowlist_mutation = false
allowlist_expansion = false
core_protection_weakened = false
provider_independence = true
external_runtime_dependency = false
production_runtime_data_changed = false
human_approval_required = true

## Deliverables

docs/architecture/allowlist-self-healing-core-change-proposal.json

## Validation

The generated report MUST pass strict JSON parsing using standard json.loads.

No production Python files may change.

Run git diff --check.

## Git

Use Agent mission branch.

Commit the validated report.

Push the branch.

Do not merge to main.

Do not modify Core.

Never force push.
