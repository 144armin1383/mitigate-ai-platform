Mission: Build Persistent Project Memory and AI Handoff Core

Goal

Create a production-only persistent project memory and handoff subsystem for the Mitigate AI platform.

The subsystem must preserve durable project knowledge, decisions, completed work, pending work, known issues, failed attempts, architecture choices, deployment state, autonomous-run outcomes, and next actions so that another AI model, provider, process, or deployment can continue work safely without rediscovering prior context.

Scope

- Generate production code only.
- Do not generate tests in this mission.
- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Fully typed and compatible with Python 3.12.
- Do not execute Git, shell, network, provider, deployment, or destructive operations directly.
- Use injected storage, clock, identifier, and event interfaces.
- Do not persist secrets or raw sensitive payloads.

Existing Components

Integrate with existing public interfaces where applicable:

- AutonomousDevelopmentSupervisor
- ExecutionReportWriter
- RuntimeService
- ProjectRegistry
- ProviderUsageLedger
- run-state stores
- execution reports
- validation results
- deployment reports

Do not reimplement those components.

Public Interface

Provide:

- ProjectMemoryConfig
- ProjectMemoryStore
- ProjectMemoryManager
- MemoryRecord
- DecisionRecord
- WorkRecord
- IssueRecord
- HandoffBundle
- HandoffStatus
- MemoryRecordType
- build_project_memory_manager(config, dependencies=None)
- project_memory_status(manager)

Generated file:

- agent/memory/project_memory_manager.py

Memory Record Types

Support:

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

Memory Rules

- Records must be append-only by default.
- Historical records must not be silently rewritten.
- Corrections must create a superseding record.
- Every record must have a stable identifier.
- Every record must belong to exactly one project.
- Records may reference prior records.
- References must remain project-scoped.
- Cross-project references must be rejected.
- Duplicate record submissions must be idempotent.

Project Memory

Maintain durable project-level memory including:

- project_id
- project_name
- project purpose
- current architecture
- active components
- current runtime state
- current deployment state
- current Git branch policy
- current provider configuration summary
- current model-routing policy summary
- current security constraints
- current operational constraints
- current development priorities
- current known issues
- current pending work
- most recent completed work
- most recent autonomous run
- most recent deployment
- next recommended actions

Do not store actual provider API keys, tokens, passwords, private keys, or authorization headers.

Architecture Decision Records

Support durable ADR-style records containing:

- decision_id
- project_id
- title
- context
- decision
- rationale
- alternatives_considered
- consequences
- status
- supersedes
- related_records
- created_at
- created_by
- metadata

Decision status:

- proposed
- accepted
- superseded
- rejected
- deprecated

Rules:

- Accepted decisions must remain historically queryable.
- Superseding a decision must not delete the original.
- Circular supersedes references must be rejected.
- Private notes must not appear in public handoff bundles.

Work Records

Support:

- work_id
- project_id
- title
- summary
- objective
- status
- branch
- commits
- changed_files
- tests_run
- tests_passed
- tests_failed
- tests_skipped
- retry_count
- risk_level
- approval_state
- started_at
- completed_at
- related_run_id
- related_plan_id
- related_mission_ids
- warnings
- next_action
- metadata

Work status:

- planned
- in_progress
- completed
- blocked
- failed
- cancelled
- rolled_back

Failed Attempt Records

Preserve enough information to prevent repeated failed approaches.

Support:

- attempted_action
- safe_failure_code
- failure_category
- safe_summary
- retryable
- retries_used
- root_cause_summary when safely known
- lessons_learned
- do_not_repeat
- alternative_next_action
- related_work_id
- related_mission_id

Never persist:

- raw traceback
- provider raw output
- credentials
- full environment
- full user prompt
- uploaded content

Known Issues

Support:

- issue_id
- title
- severity
- status
- safe_description
- first_seen_at
- last_seen_at
- affected_components
- workaround
- planned_fix
- related_records

Issue status:

- open
- monitoring
- mitigated
- resolved
- accepted_risk

Severity:

- low
- medium
- high
- critical

Project Preferences and Constraints

Support durable non-secret operational preferences such as:

- preferred development workflow
- auto-merge policy
- approval boundaries
- reporting preferences
- deployment restrictions
- repository conventions
- testing requirements
- performance priorities
- SEO priorities
- maintenance priorities
- provider-neutral execution preference
- portability requirements
- self-update policy
- rollback requirements

Do not store sensitive personal information.

Automatic Memory Capture

The manager must support safe capture from:

- successful development runs
- blocked development runs
- failed development runs
- execution reports
- final reports
- deployment outcomes
- validation outcomes
- rollback events
- approval decisions
- architectural decisions
- provider/model usage summaries

Automatic capture must:

- redact secrets
- summarize rather than copy raw payloads
- preserve safe identifiers
- deduplicate equivalent records
- never persist raw provider responses
- never persist full user messages

Handoff Bundle

Generate a deterministic, machine-readable and human-readable HandoffBundle.

The handoff must allow another AI/provider/process to continue the project safely.

Include:

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

Handoff must explicitly tell the next AI:

- what has already been completed
- what must not be repeated
- what assumptions are currently valid
- what decisions are authoritative
- what remains incomplete
- what must require human approval
- where the source of truth lives
- how to resume safely

Portable Source of Truth

GitHub/repository content is the portable source of truth for non-secret system knowledge.

The memory system must support exporting safe memory into repository-managed files through an injected export interface.

Recommended logical export structure:

- agent/memory/state/<project_id>/snapshot.json
- agent/memory/state/<project_id>/handoff.json
- agent/memory/state/<project_id>/HANDOFF.md
- agent/memory/state/<project_id>/decisions/
- agent/memory/state/<project_id>/work/
- agent/memory/state/<project_id>/issues/

The production manager must not execute Git itself.

Exports must:

- contain no secrets
- be deterministic
- be portable between providers
- be parseable without proprietary services
- use versioned schemas
- support backward-compatible reading where practical

Storage

Use an injected ProjectMemoryStore interface.

Support:

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

Storage rules:

- atomic writes
- deterministic JSON
- corruption-safe reads
- project isolation
- idempotent duplicate writes
- append-only history
- bounded record sizes
- no unrestricted filesystem paths
- no secrets

Snapshotting

Support periodic project snapshots.

A snapshot must include current derived state while preserving historical records separately.

Snapshots must:

- be deterministic
- be rebuildable from history where practical
- identify source records
- identify schema version
- identify generation time
- not delete history

Handoff Status

Support:

- current
- stale
- incomplete
- blocked
- invalid

Mark handoff stale when:

- newer development records exist
- newer accepted decisions exist
- deployment state changed
- known issue state changed
- pending work changed materially

Memory Search

Support deterministic project-scoped search over safe fields:

- title
- summary
- type
- identifiers
- tags
- component names
- safe failure codes
- status

Do not implement semantic vector search in this mission.
Do not add external databases or embeddings.

Retention

Support configurable retention for:

- recent detailed records
- historical summaries
- provider usage summaries
- validation summaries
- autonomous run summaries

Never automatically delete:

- accepted architecture decisions
- security constraints
- deployment rollback records
- critical incidents
- records marked preserve
- authoritative handoff records

Redaction

Sensitive keys must be redacted recursively.

Examples:

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

Use "[redacted]" where retaining the key is useful.

Do not preserve sensitive values in hashes or encoded form.

Concurrency

- Public methods must be thread-safe.
- Duplicate captures must remain idempotent.
- Snapshot generation must not deadlock.
- Export must operate on a consistent view.
- Do not call re-entrant dependencies while holding non-reentrant locks.
- No unbounded waits.
- No leaked threads.

Events

Emit safe events for:

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

Events may contain only:

- project_id
- safe record identifiers
- record type
- handoff status
- counts
- timestamps
- safe failure codes

Final AI Handoff Requirements

The generated handoff must be sufficient for a new AI agent with no prior conversation history to understand:

1. what the project is
2. what architecture currently exists
3. what has already been built
4. what major decisions were made
5. what failed previously
6. what must not be repeated
7. what is currently running
8. what remains to be done
9. what requires approval
10. what Git/repository paths are authoritative
11. how to continue using a different AI provider
12. how to preserve project continuity after migration

Security

- No secret persistence.
- No raw exception persistence.
- No provider raw response persistence.
- No full prompt persistence.
- No uploaded-content persistence.
- No authorization header persistence.
- No unrestricted path persistence.
- No dynamic code execution.
- No dynamic imports.
- No subprocess.
- No os.system.
- No shell execution.
- No direct Git execution.
- No direct deployment execution.

Generated File Safety

- Do not import ast, importlib, subprocess, pty, pickle, shelve, or marshal.
- Do not use eval, exec, or compile.
- Do not use os.system.
- Generated code must not contain forbidden function-call patterns checked by Mission Runner.
- Generated code must pass py_compile.
- All existing unittest tests must pass.

Deliverables

- agent/memory/project_memory_manager.py
