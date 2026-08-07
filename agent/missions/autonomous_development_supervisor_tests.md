Mission: Build Autonomous Development Supervisor Tests

Goal

Create a comprehensive unittest suite for the existing Autonomous Development Supervisor production module.

Scope

- Generate test code only.
- Do not modify agent/autonomy/autonomous_development_supervisor.py.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use Python standard library unittest only.
- Fully compatible with Python 3.12.
- Do not execute real Git commands, shell commands, network calls, provider calls, deployments, or destructive operations.

Module Under Test

- agent.autonomy.autonomous_development_supervisor.AutonomousDevelopmentConfig
- agent.autonomy.autonomous_development_supervisor.AutonomousDevelopmentSupervisor
- agent.autonomy.autonomous_development_supervisor.DevelopmentRequest
- agent.autonomy.autonomous_development_supervisor.DevelopmentRunResult
- agent.autonomy.autonomous_development_supervisor.DevelopmentRunStatus
- agent.autonomy.autonomous_development_supervisor.RiskLevel
- agent.autonomy.autonomous_development_supervisor.ApprovalDecision
- agent.autonomy.autonomous_development_supervisor.build_autonomous_development_supervisor
- agent.autonomy.autonomous_development_supervisor.supervisor_status

Testing Environment

Use deterministic fakes for:

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

General Rules

- Use unittest and unittest.mock.
- Use TemporaryDirectory when filesystem state is required.
- Do not modify sys.path.
- Use repository-root imports.
- Do not use dynamic code execution.
- Do not use dynamic imports.
- Do not use subprocess, os.system, pty, or shell execution.
- Tests must use bounded waits and must never hang.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Configuration Tests

Test:

- default configuration values
- invalid limits
- invalid retry counts
- invalid run timeout
- invalid maximum cost
- invalid parallel mission count
- unknown configuration fields
- configuration immutability
- approval defaults enabled
- auto-merge defaults disabled
- auto-deploy default disabled

Development Request Tests

Test:

- valid request acceptance
- missing request_id
- missing project_id
- empty objective
- unknown fields
- absolute allowed path rejection
- traversal path rejection
- null-byte path rejection
- denied-path enforcement
- requested risk cannot lower calculated risk
- request input is not mutated
- metadata redaction

Lifecycle Tests

Test:

- submit registers without execution
- duplicate submit is idempotent
- run executes once
- duplicate concurrent run executes once
- resume blocked run
- resume approval-waiting run
- cancel active run
- repeated cancel is idempotent
- approve applies once
- reject stops run safely
- close idempotency
- context-manager lifecycle
- invalid state transitions

Planning Tests

Test:

- successful planning flow
- planner receives deterministic input
- planner failure
- invalid plan
- circular dependency
- duplicate mission identifiers
- maximum plan size enforcement
- maximum mission count enforcement
- dependency ordering preservation
- project isolation
- no side effects before validation

Risk Tests

Test:

- low-risk documentation work
- low-risk isolated bug fix
- medium-risk refactor
- high-risk database migration
- high-risk authentication change
- critical-risk secret rotation
- critical-risk DNS change
- critical-risk destructive deletion
- user-requested risk may increase risk
- user-requested risk may not reduce risk
- high and critical risk never auto-merge

Approval Tests

Test approval requirements for:

- database changes
- destructive changes
- secret changes
- dependency changes
- DNS changes
- security-policy changes
- authentication changes
- authorization changes
- systemd changes
- Nginx changes
- firewall changes
- production deployment
- high risk
- critical risk
- cost threshold breach

Test:

- approved
- rejected
- approved_with_constraints
- duplicate approval
- private approval notes excluded from events
- approval does not bypass validation

Git Workflow Tests

Test:

- dirty repository blocks execution
- base branch validation
- deterministic branch naming
- branch contains safe project and request identifiers
- create branch
- inspect changed files
- reject denied path changes
- reject unrelated file changes
- commit generated changes
- push branch
- no force push
- no history rewrite
- no main deletion
- merge prevented when tests fail
- merge prevented without required approval
- rollback unmerged branch
- Git dependency exception conversion

Mission Generation Tests

Test:

- deterministic mission identifiers
- deterministic dependency ordering
- project scope included
- allowed paths included
- denied actions included
- security rules included
- privacy rules included
- completion criteria included
- large mission split policy
- secret values never included
- mission count limit
- mission output remains inside allowlist

Mission Execution Tests

Test:

- successful mission
- dependency not completed
- budget block
- rate-limit block
- compilation failure retry
- unittest failure retry
- validation failure retry
- transient provider failure retry
- security failure never retried
- compliance failure never retried
- authentication failure never retried
- billing failure never retried
- permission failure never retried
- retry attempts per mission enforced
- total retry budget enforced
- retry exhaustion
- safe retry summary
- raw traceback excluded
- provider response excluded
- environment values excluded

Validation Tests

Test merge readiness requires:

- generated-file validation
- py_compile success
- shell syntax validation when applicable
- selected tests pass
- full repository tests pass
- no unrelated changes
- no forbidden patterns
- no secrets detected
- no denied paths
- approvals satisfied
- no budget breach
- deterministic final evidence

Merge Policy Tests

Test:

- low risk becomes merge-ready
- low risk does not auto-merge by default
- low risk auto-merges only when configured
- medium risk auto-merge disabled by default
- medium risk auto-merges only when configured and no approval category applies
- high risk never auto-merges
- critical risk never auto-merges
- failed tests prevent merge
- missing approval prevents merge
- independent validation evidence required

Deployment Policy Tests

Test:

- deployment disabled by default
- supervisor only marks ready_for_deployment
- no direct systemctl execution
- no direct Nginx execution
- no direct Certbot execution
- no direct DNS execution
- no direct firewall execution
- production deployment requires approval
- deployment dependency is injected

Persistence Tests

Test:

- atomic run-state write contract
- project-scoped state
- deterministic serialization
- duplicate request protection
- resume blocked run
- resume approval-waiting run
- corruption-safe read failure
- no secrets persisted
- no unrestricted filesystem paths persisted

Final Report Tests

Test report includes:

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

Test report excludes:

- secrets
- API keys
- credentials
- authorization headers
- full environment values
- full user messages
- uploaded content
- provider responses
- raw tracebacks
- unrestricted paths
- private approval notes

Event Tests

Test safe events for:

- run creation
- request validation
- planning
- risk assessment
- approval required
- approval received
- approval rejected
- branch preparation
- mission generation
- mission execution
- retry
- validation
- merge readiness
- merge completion
- deployment readiness
- completion
- block
- failure
- cancellation

Test events contain only safe identifiers, states, risk levels, counts, timestamps, mission identifiers, safe failure codes, and approval categories.

Concurrency Tests

Test:

- concurrent duplicate submit
- concurrent duplicate run
- concurrent approval
- concurrent cancellation
- no double execution
- no double merge
- bounded locking
- no deadlocks
- no leaked threads
- dependency calls not made while re-entrant lock is held

Failure Code Tests

Test safe propagation for:

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

Repository Safety

- Do not create persistent temporary directories in repository root.
- Clean up all temporary resources.
- Do not modify production data.
- Do not modify unrelated files.
- Tests must leave a clean working tree when started from a clean checkout.

Deliverables

- agent/tests/test_autonomous_development_supervisor.py

Public Type Contract Clarification

The production module intentionally defines these enum types:

- DevelopmentRunStatus
- RiskLevel
- ApprovalDecisionType

These types must be tested as Python Enum classes.

ApprovalDecision is NOT an enum.

ApprovalDecision is intentionally a frozen dataclass representing one approval record and contains:

- decision_id
- run_id
- approver_id
- decision
- constraints
- timestamp
- reason_code

The ApprovalDecision.decision field uses ApprovalDecisionType.

Tests must not require ApprovalDecision to expose Enum attributes such as __members__.

Enum presence tests must validate:

- DevelopmentRunStatus is an Enum
- RiskLevel is an Enum
- ApprovalDecisionType is an Enum

ApprovalDecision tests must validate its dataclass structure and immutable approval-record behavior instead.

Do not change the production implementation merely to satisfy an incorrect enum assumption.

All existing and newly generated unittest tests must pass.
