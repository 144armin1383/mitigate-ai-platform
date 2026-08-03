Mission: Build Autonomous Development Supervisor Core

Goal

Create the production-only autonomous development supervisor that coordinates planning, mission creation, mission execution, validation, bounded retries, Git branch workflows, approval boundaries, and final reporting for multiple projects.

Scope

- Generate production code only.
- Do not generate tests in this mission.
- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Fully typed and compatible with Python 3.12.
- Do not execute real shell commands, Git commands, network requests, provider calls, deployments, or destructive operations directly.
- All external operations must use injected interfaces.
- Do not automatically merge into main in this mission.
- Do not automatically deploy to production in this mission.

Existing Components

Use existing public interfaces where applicable:

- RuntimeService
- UnifiedRequestFlowService
- PlannerQueueFlowCoordinator
- PlanValidatorMissionBuilder
- QueueEnqueueCoordinator
- ExecutionOutcomeCoordinator
- ExecutionReportWriter
- ProviderUsageLedger
- ProviderRateLimiter
- ProviderBudgetLimitEvaluator
- ProjectRegistry
- Mission Runner
- Validation Engine
- Retry Engine
- Private Admin API

Do not reimplement existing orchestration components.

Public Interface

Provide:

- AutonomousDevelopmentConfig
- AutonomousDevelopmentSupervisor
- DevelopmentRequest
- DevelopmentRunResult
- DevelopmentRunStatus
- RiskLevel
- ApprovalDecision
- build_autonomous_development_supervisor(config, dependencies=None)
- supervisor_status(supervisor)

Generated file:

- agent/autonomy/autonomous_development_supervisor.py

Development Request

Support:

- request_id
- project_id
- user_id
- title
- objective
- requirements
- constraints
- allowed_paths
- denied_paths
- requested_branch_name
- requested_base_branch
- requested_risk_level
- auto_merge_requested
- auto_deploy_requested
- max_cost
- deadline
- metadata

Rules:

- Inputs must not be mutated.
- Unknown fields must be rejected.
- Project ID and request ID must be non-empty.
- Objective must be non-empty.
- Paths must be repository-relative.
- Reject absolute paths, traversal, null bytes, and cross-project paths.
- Sensitive metadata values must be redacted from results and events.

Configuration

AutonomousDevelopmentConfig must support:

- default_base_branch
- maximum_plan_steps
- maximum_missions
- maximum_retry_attempts_per_mission
- maximum_total_retry_attempts
- maximum_parallel_missions
- maximum_run_seconds
- maximum_cost
- auto_merge_low_risk
- auto_merge_medium_risk
- auto_deploy_enabled
- require_approval_for_database_changes
- require_approval_for_secret_changes
- require_approval_for_dependency_changes
- require_approval_for_dns_changes
- require_approval_for_security_policy_changes
- require_approval_for_destructive_changes
- require_approval_for_production_deployment
- stop_on_security_failure
- stop_on_compliance_failure
- stop_on_budget_failure
- final_report_required

Defaults

- default_base_branch = main
- maximum_plan_steps = 50
- maximum_missions = 50
- maximum_retry_attempts_per_mission = 3
- maximum_total_retry_attempts = 10
- maximum_parallel_missions = 1
- maximum_run_seconds = 7200
- auto_merge_low_risk = false
- auto_merge_medium_risk = false
- auto_deploy_enabled = false
- all approval requirements = true
- all stop-on-critical-failure flags = true
- final_report_required = true

Run States

Support:

- created
- validating
- planning
- awaiting_approval
- preparing_branch
- generating_missions
- executing
- validating_results
- retrying
- ready_for_merge
- merging
- ready_for_deployment
- deploying
- completed
- blocked
- failed
- cancelled

State Rules

- State transitions must be deterministic.
- Invalid transitions must return safe failures.
- State changes must be thread-safe.
- Never acquire the same non-reentrant lock twice in one call chain.
- Concurrent duplicate execution for the same request ID must be idempotent.
- Only one active run per project and request ID may exist.
- Cancellation must be safe and idempotent.

Supervisor Lifecycle

Provide:

- submit(request)
- run(request)
- resume(run_id)
- cancel(run_id)
- approve(run_id, decision)
- reject(run_id, reason_code)
- status(run_id=None)
- latest_events(limit)
- final_report(run_id)
- close()

Rules:

- submit() registers a request without executing it.
- run() executes synchronously through allowed stages.
- resume() continues a blocked or approval-waiting run.
- approve() must not bypass validation.
- reject() must stop execution safely.
- close() must be idempotent.
- Support context-manager usage.
- Do not register global signal handlers.
- Do not register atexit hooks.

Planning Flow

1. Validate request and project.
2. Validate allowed and denied paths.
3. Resolve project configuration.
4. Assess risk.
5. Build deterministic planner input.
6. Call injected planner.
7. Validate plan using existing plan validation interfaces.
8. Convert plan steps into missions.
9. Determine approval requirements.
10. Continue only when approvals are satisfied.

Planning Rules

- Maximum plan size must be enforced.
- Circular dependencies must be rejected.
- Duplicate mission identifiers must be rejected.
- Mission dependencies must be deterministic.
- Dependency-safe ordering must be preserved.
- Planner output must never directly execute code.
- Planner output must not change secrets, DNS, production, or databases without approval.
- Planner failures must be safe and retryable only when classified retryable.

Risk Assessment

Risk levels:

- low
- medium
- high
- critical

Low risk examples:

- documentation
- tests
- formatting
- isolated bug fixes
- non-destructive UI changes
- safe performance improvements

Medium risk examples:

- internal refactoring
- API changes with compatibility preserved
- dependency-neutral architecture changes
- configuration changes without secrets

High risk examples:

- database migrations
- authentication changes
- authorization changes
- dependency additions
- infrastructure changes
- payment or compliance logic
- deployment automation

Critical risk examples:

- secret rotation
- DNS changes
- destructive database operations
- production deletion
- unrestricted administrator access changes
- disabling security controls
- force-pushing protected branches

Rules:

- Risk assessment must be deterministic and explainable.
- User-requested risk may increase but must never lower calculated risk.
- Critical changes always require approval.
- Auto-merge is forbidden for high and critical risk.
- Auto-deployment is forbidden unless explicitly configured and approved.

Approval Boundaries

Approval must be required for:

- database schema changes
- destructive data operations
- secret or credential changes
- dependency additions or removals
- DNS or Cloudflare changes
- security-policy changes
- authentication or authorization changes
- systemd, Nginx, firewall, or infrastructure activation
- production deployment
- changes outside allowed paths
- high or critical risk
- cost above configured thresholds

Approval decisions:

- approved
- rejected
- approved_with_constraints

Approval data must include:

- decision_id
- run_id
- approver_id
- decision
- constraints
- timestamp
- reason_code

Do not expose private approval notes in public events.

Branch Workflow

Use injected Git workflow interface only.

Support:

- verify clean repository
- verify base branch
- fetch status
- create development branch
- inspect changed files
- inspect diff summary
- commit generated changes
- push branch
- merge approved branch
- rollback unmerged branch

Rules:

- Never execute Git directly.
- Never force push.
- Never rewrite shared history.
- Never delete main.
- Never merge when tests fail.
- Never merge unapproved high-risk changes.
- Never merge files outside allowed paths.
- Default branch must remain protected.
- Branch names must be normalized and deterministic.
- Generated branches must include project and request identifiers safely.
- Dirty working tree must block autonomous execution.
- Existing unrelated changes must never be overwritten.

Mission Generation

- Generate missions from validated plan steps.
- Mission output paths must remain inside the existing Mission Runner allowlist.
- Limit mission count.
- Preserve deterministic mission identifiers.
- Preserve dependency order.
- Mission instructions must include project scope, allowed paths, prohibited actions, tests, security, privacy, and completion criteria.
- Large missions must be split into production-code and test missions when necessary.
- Never include secrets in mission content.
- Never request dynamic code execution.
- Never request unrestricted shell access.

Mission Execution

Use injected mission executor interface.

For each mission:

1. Verify dependencies completed.
2. Verify budget and rate limit.
3. Create mission branch.
4. Execute mission.
5. Validate generated files.
6. Run selected tests.
7. Run full repository tests where required.
8. Capture safe result.
9. Retry only when policy permits.
10. Mark mission completed, blocked, or failed.

Rules:

- Maximum retries must be enforced.
- Total retry budget must be enforced.
- Security failures must never be retried automatically.
- Compliance failures must never be retried automatically.
- Authentication, billing, and permission failures must not be retried automatically.
- Compilation, deterministic unit-test, and transient provider failures may be retryable.
- Retry missions must include only safe error summaries.
- Raw tracebacks, secrets, full user content, provider responses, and environment values must not be included.

Automatic Repair

Support bounded automatic repair for:

- compilation failures
- unit-test failures
- deterministic validation failures
- safe formatting failures
- safe type errors
- non-security path validation failures
- incomplete generated JSON
- bounded provider response truncation

Automatic repair must not handle without approval:

- security failures
- compliance failures
- secrets
- database destruction
- production failures
- DNS
- billing
- account permissions
- protected branch conflicts

Validation

Before merge readiness, require:

- generated files validated
- py_compile success for Python files
- shell syntax validation for shell scripts when applicable
- selected tests passing
- full repository unittest discovery passing
- no unrelated file changes
- no forbidden patterns
- no secrets detected
- no denied paths changed
- no unresolved approval conditions
- no budget breach
- clean deterministic report

Result Validation

The supervisor must verify:

- changed file list
- branch name
- commit identifiers
- test counts
- skipped-test counts
- failure counts
- retry counts
- cost totals
- provider/model usage
- approval state
- risk level
- merge eligibility
- deployment eligibility

Do not trust executor success flags without independent validation evidence.

Merge Policy

Low risk:

- May become merge-ready automatically.
- Actual automatic merge only when auto_merge_low_risk=true.
- All tests and validations must pass.

Medium risk:

- May auto-merge only when auto_merge_medium_risk=true.
- Must have no approval-required category.
- All tests and validations must pass.

High and critical risk:

- Never auto-merge.
- Require explicit approval.
- Require a final pre-merge validation pass.

Deployment Policy

- Deployment is disabled by default.
- No deployment implementation in this mission.
- Supervisor may only mark ready_for_deployment.
- Production deployment always requires explicit approval.
- Deployment dependencies must be injected.
- Never run systemctl, Nginx, Certbot, DNS, Cloudflare, or firewall commands directly.

Final Reporting

Generate a deterministic final report containing:

- run_id
- request_id
- project_id
- title
- objective summary
- status
- risk level
- approvals
- plan summary
- mission summary
- completed missions
- failed missions
- blocked missions
- changed files
- tests executed
- tests passed
- tests failed
- tests skipped
- retries
- provider/model usage
- estimated cost
- branch
- commits
- merge status
- deployment status
- warnings
- safe failure codes
- next required action
- started_at
- completed_at

The report must not contain:

- secrets
- API keys
- credentials
- authorization headers
- full environment values
- full user messages
- uploaded content
- raw provider responses
- raw tracebacks
- unrestricted filesystem paths
- private approval notes

Events

Emit safe deterministic events for:

- development_run_created
- request_validating
- request_validated
- planning_started
- planning_completed
- risk_assessed
- approval_required
- approval_received
- approval_rejected
- branch_preparation_started
- branch_prepared
- mission_generation_started
- mission_generated
- mission_execution_started
- mission_completed
- mission_failed
- mission_retry_scheduled
- mission_retry_completed
- validation_started
- validation_completed
- merge_ready
- merge_started
- merge_completed
- deployment_ready
- development_run_completed
- development_run_blocked
- development_run_failed
- development_run_cancelled

Events may include only:

- safe identifiers
- state
- risk level
- mission identifier
- counts
- timestamps
- safe failure code
- approval requirement category

Concurrency

- Supervisor public methods must be thread-safe.
- Concurrent duplicate submit calls must create one run.
- Concurrent run calls must execute one active workflow.
- Concurrent approvals must apply once.
- Cancellation must not deadlock.
- External dependencies must not be called while holding locks when re-entry is possible.
- No unbounded waits.
- No leaked threads or processes.

Persistence

Use an injected run-state store.

Requirements:

- atomic writes
- project-scoped state
- deterministic serialization
- duplicate request protection
- resumable blocked runs
- resumable approval-waiting runs
- corruption-safe reads
- no secrets persisted
- no unrestricted paths persisted

Dependency Injection

Support injected interfaces for:

- project resolver
- planner
- plan validator
- mission builder
- mission executor
- validation engine
- retry classifier
- Git workflow
- approval store
- run-state store
- usage ledger
- report writer
- clock
- identifier generator
- event sink
- cost evaluator
- risk evaluator

Do not instantiate real external dependencies inside the supervisor.

Failure Codes

Support safe failure codes including:

- invalid_supervisor_config
- invalid_development_request
- unknown_project
- unsafe_path
- dirty_repository
- planning_failed
- invalid_plan
- approval_required
- approval_rejected
- branch_preparation_failed
- mission_generation_failed
- mission_execution_failed
- validation_failed
- retry_exhausted
- budget_blocked
- rate_limit_blocked
- security_failure
- compliance_failure
- dependency_failed
- merge_not_allowed
- merge_failed
- deployment_not_allowed
- cancelled
- timeout

Security

- No secret logging.
- No request-body logging.
- No provider-response logging.
- No raw exception exposure.
- No dynamic code execution.
- No dynamic imports.
- No subprocess.
- No os.system.
- No shell execution.
- No direct Git execution.
- No direct deployment execution.
- No unrestricted file writes.
- No automatic weakening of security controls.

Generated File Safety

- Do not import ast, importlib, subprocess, or pty.
- Do not use eval or compile.
- Do not use exec.
- Do not use os.system.
- Generated code must not contain forbidden function-call patterns checked by Mission Runner.
- Generated code must pass py_compile.
- All existing unittest tests must pass.

Deliverables

- agent/autonomy/autonomous_development_supervisor.py
