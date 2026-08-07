Mission: Build Persistent Project Memory and AI Handoff Tests

Goal

Create a comprehensive unittest suite for the existing Persistent Project Memory and AI Handoff production module.

Scope

- Generate test code only.
- Do not modify agent/memory/project_memory_manager.py.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use Python standard library unittest only.
- Fully compatible with Python 3.12.
- Do not execute Git, shell, network, provider, deployment, or destructive operations.

Module Under Test

- agent.memory.project_memory_manager.ProjectMemoryConfig
- agent.memory.project_memory_manager.ProjectMemoryStore
- agent.memory.project_memory_manager.ProjectMemoryManager
- agent.memory.project_memory_manager.MemoryRecord
- agent.memory.project_memory_manager.DecisionRecord
- agent.memory.project_memory_manager.WorkRecord
- agent.memory.project_memory_manager.IssueRecord
- agent.memory.project_memory_manager.HandoffBundle
- agent.memory.project_memory_manager.HandoffStatus
- agent.memory.project_memory_manager.MemoryRecordType
- agent.memory.project_memory_manager.build_project_memory_manager
- agent.memory.project_memory_manager.project_memory_status

Testing Environment

Use deterministic fakes for:

- ProjectMemoryStore
- clock
- identifier generator
- event sink
- export interface

General Rules

- Use unittest and unittest.mock.
- Use TemporaryDirectory where required.
- Do not modify sys.path.
- Use repository-root imports.
- Do not use dynamic code execution.
- Do not use dynamic imports.
- Do not use subprocess, os.system, shell execution, pickle, shelve, or marshal.
- Tests must use bounded waits.
- Tests must never hang.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Configuration Tests

Test:

- default configuration
- invalid record-size limit
- invalid retention values
- invalid schema version
- unknown fields
- immutable configuration
- safe defaults

Memory Record Tests

Test:

- stable record identifier
- project ownership
- append-only behavior
- duplicate write idempotency
- cross-project reference rejection
- safe superseding record
- historical record remains queryable
- circular supersedes rejection
- deterministic serialization
- record input not mutated

Memory Record Type Tests

Validate supported record types including:

- project_snapshot
- architecture_decision
- development_decision
- completed_work
- pending_work
- failed_attempt
- known_issue
- deployment_event
- autonomous_run_summary
- validation_summary
- provider_usage_summary
- security_constraint
- operational_constraint
- project_preference
- next_action
- handoff_note
- migration_note
- rollback_note
- incident_summary

Architecture Decision Tests

Test:

- proposed decision
- accepted decision
- rejected decision
- deprecated decision
- superseded decision
- rationale preservation
- alternatives preservation
- consequences preservation
- accepted decisions remain queryable
- superseding does not delete original
- circular supersedes rejected
- private notes excluded from handoff

Work Record Tests

Test:

- planned
- in_progress
- completed
- blocked
- failed
- cancelled
- rolled_back
- branch preservation
- commit preservation
- changed-file preservation
- test count preservation
- retry count preservation
- risk level preservation
- approval state preservation
- related run/plan/mission identifiers
- input not mutated

Failed Attempt Tests

Test:

- safe failure code
- safe summary
- retryable state
- retries used
- lessons learned
- do_not_repeat
- alternative next action
- no raw traceback
- no provider raw response
- no full environment
- no full user prompt
- no uploaded content

Known Issue Tests

Test:

- open
- monitoring
- mitigated
- resolved
- accepted_risk
- low severity
- medium severity
- high severity
- critical severity
- first_seen_at
- last_seen_at
- affected components
- workaround
- planned fix
- related records

Project Preference Tests

Test durable safe preferences for:

- development workflow
- auto-merge policy
- approval boundaries
- reporting preferences
- deployment restrictions
- repository conventions
- testing requirements
- performance priorities
- SEO priorities
- maintenance priorities
- provider-neutral execution
- portability requirements
- self-update policy
- rollback requirements

Automatic Capture Tests

Test safe capture from:

- successful development run
- blocked development run
- failed development run
- execution report
- final report
- deployment outcome
- validation outcome
- rollback
- approval decision
- architecture decision
- provider/model usage summary

Verify:

- secrets redacted
- equivalent records deduplicated
- raw provider response excluded
- full user message excluded
- safe identifiers preserved

Project Snapshot Tests

Test:

- deterministic snapshot
- source record references
- schema version
- generation timestamp
- current architecture
- current deployment state
- current constraints
- pending work
- known issues
- recent completed work
- latest autonomous run
- next actions
- historical records preserved
- snapshot rebuild consistency

Handoff Bundle Tests

Verify generated handoff contains:

- schema_version
- bundle_id
- generated_at
- project_id
- project_summary
- architecture_summary
- accepted_architecture_decisions
- active_constraints
- development_policy
- security_policy_summary
- deployment_policy_summary
- portability_policy
- provider-neutral operating instructions
- completed_work
- pending_work
- blocked_work
- known_issues
- failed_attempts_to_avoid
- current_branch_state
- latest_validation_summary
- latest_test_summary
- latest_deployment_summary
- recent_autonomous_run_summaries
- next_recommended_actions
- required_approvals
- warnings
- record_references

Handoff Continuity Tests

Verify a new agent with no prior context can determine from the handoff:

- project purpose
- current architecture
- completed work
- authoritative decisions
- prior failed approaches
- do-not-repeat actions
- current running state
- incomplete work
- approval boundaries
- authoritative repository paths
- provider-neutral continuation instructions
- migration continuation instructions

Handoff Status Tests

Test:

- current
- stale
- incomplete
- blocked
- invalid

Mark stale when:

- newer development records exist
- newer accepted decision exists
- deployment changed
- known issue materially changed
- pending work materially changed

Export Tests

Validate safe repository-oriented exports for logical paths:

- agent/memory/state/<project_id>/snapshot.json
- agent/memory/state/<project_id>/handoff.json
- agent/memory/state/<project_id>/HANDOFF.md
- agent/memory/state/<project_id>/decisions/
- agent/memory/state/<project_id>/work/
- agent/memory/state/<project_id>/issues/

Verify:

- no direct Git execution
- deterministic JSON
- provider-neutral format
- versioned schema
- no credentials
- no authorization headers
- no unrestricted paths
- stable human-readable Markdown handoff

Storage Tests

Test injected store contracts:

- append_record
- get_record
- list_records
- find_by_type
- find_related
- get_latest_snapshot
- write_snapshot
- export_handoff
- load_handoff
- health

Test:

- atomic write contract
- project isolation
- duplicate write protection
- corruption-safe read failure
- bounded record size
- append-only history
- no secrets

Search Tests

Test project-scoped search by:

- title
- summary
- type
- identifier
- tag
- component name
- safe failure code
- status

Verify no cross-project leakage.

Retention Tests

Verify configurable retention for:

- detailed recent records
- historical summaries
- provider usage summaries
- validation summaries
- autonomous run summaries

Never delete automatically:

- accepted architecture decisions
- security constraints
- deployment rollback records
- critical incidents
- preserve-marked records
- authoritative handoff records

Redaction Tests

Recursively redact sensitive keys including:

- password
- secret
- token
- api_key
- authorization
- credential
- private_key
- access_key
- refresh_token
- session
- cookie

Verify values become "[redacted]".

Verify sensitive values are not retained as:

- hashes
- encoded strings
- summaries
- metadata copies

Concurrency Tests

Test:

- concurrent duplicate capture
- concurrent snapshot generation
- concurrent handoff generation
- consistent export view
- no deadlock
- no duplicate record creation
- bounded locking
- no leaked threads

Event Tests

Test safe events:

- memory_record_created
- memory_record_superseded
- memory_capture_completed
- memory_capture_failed
- project_snapshot_created
- handoff_generated
- handoff_marked_stale
- handoff_loaded
- handoff_validation_failed
- memory_export_completed
- memory_export_failed

Verify events contain only:

- project_id
- safe record identifiers
- record type
- handoff status
- counts
- timestamps
- safe failure codes

Security Tests

Verify no:

- secret persistence
- raw exception persistence
- raw provider responses
- full prompt persistence
- uploaded-content persistence
- authorization-header persistence
- unrestricted path persistence
- dynamic execution
- direct Git execution
- direct deployment execution

Repository Safety

- Do not create persistent temporary files in repository root.
- Clean up all temporary resources.
- Do not modify unrelated files.
- Tests must leave a clean working tree when started from a clean checkout.

Deliverables

- agent/tests/test_project_memory_manager.py
