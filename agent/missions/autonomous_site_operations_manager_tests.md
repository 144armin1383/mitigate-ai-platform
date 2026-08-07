Mission: Build Autonomous Site Operations Manager Tests

Goal

Create a comprehensive unittest suite for the existing Autonomous Site Operations Manager production module.

Scope

- Generate test code only.
- Do not modify agent/operations/site_operations_manager.py.
- Do not add dependencies.
- Do not modify requirements.txt.
- Use Python standard library unittest only.
- Fully compatible with Python 3.12.
- Do not execute real network requests, Git commands, shell commands, deployments, DNS operations, systemd operations, Nginx operations, provider calls, or destructive operations.

Module Under Test

- agent.operations.site_operations_manager.SiteOperationsConfig
- agent.operations.site_operations_manager.SiteOperationsManager
- agent.operations.site_operations_manager.SiteOperationsProjectConfig
- agent.operations.site_operations_manager.SiteObservation
- agent.operations.site_operations_manager.SiteFinding
- agent.operations.site_operations_manager.SiteFindingType
- agent.operations.site_operations_manager.SiteFindingSeverity
- agent.operations.site_operations_manager.SiteTaskCandidate
- agent.operations.site_operations_manager.SiteOperationsCycleResult
- agent.operations.site_operations_manager.SiteOperationsStatus
- agent.operations.site_operations_manager.build_site_operations_manager
- agent.operations.site_operations_manager.site_operations_status

Testing Environment

Use deterministic fakes for:

- project resolver
- observation provider
- availability monitor
- SEO observer
- performance observer
- accessibility observer
- security observer
- ecommerce observer
- repository observer
- deployment observer
- search visibility observer
- autonomous development supervisor
- project memory manager
- approval store
- budget evaluator
- clock
- identifier generator
- event sink

General Rules

- Use unittest and unittest.mock.
- Use TemporaryDirectory where required.
- Do not modify sys.path.
- Use repository-root imports.
- Do not use dynamic code execution.
- Do not use dynamic imports.
- Do not use subprocess, os.system, pty, shell execution, pickle, shelve, or marshal.
- Tests must use bounded waits.
- Tests must never hang.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Configuration Tests

Test:

- default configuration
- invalid limits
- invalid cycle timeout
- invalid maximum cost
- invalid maximum task count
- unknown configuration fields
- configuration immutability
- automatic low-risk fixes default behavior
- automatic medium-risk fixes default behavior

Project Configuration Tests

Test:

- valid project config
- missing project_id
- missing canonical URL
- unsafe URL
- unsupported URL scheme
- absolute allowed path rejection
- traversal path rejection
- null-byte path rejection
- denied path enforcement
- secrets rejected from metadata or configuration
- project input not mutated
- project isolation

Lifecycle Tests

Test:

- register_project
- duplicate project registration
- unregister_project
- run_cycle
- run_all_projects_cycle
- ingest_observations
- assess_findings
- generate_task_candidates
- dispatch_safe_tasks
- approve_task
- reject_task
- status
- latest_findings
- final_cycle_report
- close idempotency
- context-manager behavior if implemented
- invalid lifecycle transitions
- duplicate cycle protection
- concurrent cycle protection
- cancellation when supported

Observation Tests

Test safe ingestion of observations for:

- availability
- page status
- redirects
- response timing
- page metadata
- headings
- canonical tags
- robots directives
- sitemap
- structured data
- image summaries
- link summaries
- accessibility summaries
- performance metrics
- Core Web Vitals
- security headers
- CMS health
- ecommerce health
- repository health
- deployment health
- search visibility
- indexability

Verify:

- no raw network access
- no raw HTML persistence
- no credentials
- no cookies
- no customer data
- duplicate observations are idempotent

Finding Type Tests

Validate supported finding types including:

- site_unavailable
- slow_response
- broken_internal_link
- broken_external_link
- redirect_chain
- redirect_loop
- missing_title
- duplicate_title
- weak_title
- missing_meta_description
- duplicate_meta_description
- missing_h1
- multiple_h1
- heading_hierarchy_issue
- missing_canonical
- conflicting_canonical
- noindex_unexpected
- robots_blocking
- sitemap_missing
- sitemap_invalid
- sitemap_stale
- sitemap_url_error
- structured_data_missing
- structured_data_invalid
- image_missing_alt
- image_oversized
- image_unoptimized
- image_broken
- page_too_large
- render_blocking_resource
- poor_lcp
- poor_inp
- poor_cls
- accessibility_issue
- security_header_issue
- mixed_content
- certificate_warning
- stale_content
- orphan_page
- duplicate_content
- thin_content
- pagination_issue
- ecommerce_product_issue
- ecommerce_price_issue
- ecommerce_stock_issue
- checkout_warning
- repository_health_issue
- deployment_health_issue
- regression_detected
- seo_visibility_drop
- indexing_warning
- monitoring_gap
- technical_debt
- maintenance_required

Severity Tests

Test:

- info
- low
- medium
- high
- critical

Finding Generation Tests

Test:

- deterministic finding ID
- first_seen_at
- last_seen_at
- occurrence_count
- evidence summary
- recommended action
- estimated risk
- estimated effort
- auto-fix eligibility
- approval requirement
- related memory records
- project ownership
- finding input not mutated

Finding Deduplication Tests

Test:

- equivalent finding deduplication
- occurrence count increment
- first_seen preserved
- last_seen updated
- severity escalation
- no duplicate development task while equivalent task remains active
- new task allowed after previous equivalent task closes
- no cross-project deduplication

SEO Tests

Test detection and handling for:

- missing title
- duplicate title
- weak title
- missing meta description
- duplicate meta description
- missing canonical
- conflicting canonical
- unexpected noindex
- robots blocking
- sitemap missing
- sitemap invalid
- stale sitemap
- sitemap URL errors
- heading hierarchy
- missing H1
- multiple H1
- structured data missing
- structured data invalid
- broken links
- redirect chains
- redirect loops
- duplicate content
- thin content
- orphan pages
- internal linking opportunities where supported
- image alt text
- crawlability
- indexing warning
- search visibility drop

SEO Safety Tests

Verify:

- no fabricated ranking data
- no keyword stuffing tasks
- no doorway-page tasks
- no automatic broad canonical strategy changes
- no automatic broad robots/noindex changes
- major sitewide SEO changes require approval
- safe metadata fixes may remain low risk
- user experience and factual accuracy preserved in task constraints

Performance Tests

Test:

- slow response
- oversized image
- unoptimized image
- page too large
- render-blocking resource
- poor LCP
- poor INP
- poor CLS
- repeated slow endpoint
- regression after deployment
- safe performance task generation

Availability Tests

Test:

- site unavailable
- repeated HTTP failure
- unexpected redirect
- readiness failure
- deployment regression
- recurring failure
- critical availability escalation
- critical incident memory capture
- unrelated automatic changes deferred when critical availability issue requires it

Security Tests

Test:

- missing security headers
- mixed content
- certificate warning
- public exposure summary
- dependency-security summary
- authentication regression summary
- authorization regression summary

Verify:

- high or critical security findings do not auto-dispatch
- security controls are never weakened automatically
- raw vulnerability secret material is not persisted
- security findings trigger approval boundaries

Accessibility Tests

Test:

- accessibility observation
- finding creation
- severity preservation
- task candidate generation
- validation requirements

Ecommerce Tests

Test:

- missing product image
- broken product image
- incomplete product metadata
- duplicate product page
- stale product information
- inconsistent structured data
- price observation issue
- stock observation issue
- checkout warning

Verify:

- commercial product facts are not invented
- authoritative source requirement is preserved

Prioritization Tests

Test deterministic priority based on:

- severity
- traffic scope
- availability impact
- SEO impact
- conversion impact
- security impact
- recurrence
- regression status
- effort
- risk
- existing open task
- project priority

Verify:

- no randomness
- critical issues outrank normal maintenance
- equivalent inputs give equivalent priority

Task Candidate Tests

Test:

- deterministic task ID
- finding grouping
- unrelated findings not grouped
- objective generation
- recommended changes
- allowed paths
- denied paths
- risk level
- approval requirement
- auto-dispatch eligibility
- priority
- estimated effort
- estimated cost
- acceptance criteria
- validation requirements
- no secrets
- no unrestricted filesystem access

Automatic Dispatch Tests

Test safe dispatch through injected AutonomousDevelopmentSupervisor:

- low-risk eligible task
- low-risk disabled
- equivalent active run prevents duplicate dispatch
- budget block
- cycle task limit
- automatic medium-risk disabled
- automatic medium-risk enabled when safe
- medium-risk approval category prevents dispatch
- high-risk never auto-dispatched
- critical-risk never auto-dispatched
- security-sensitive task not auto-dispatched
- database migration not auto-dispatched
- dependency addition not auto-dispatched
- auth change not auto-dispatched
- deployment action not auto-dispatched

Verify DevelopmentRequest contains:

- project ID
- objective
- allowed paths
- denied paths
- risk
- acceptance criteria
- validation requirements

Approval Tests

Require approval for:

- database schema changes
- destructive data changes
- authentication
- authorization
- secrets
- dependencies
- payments
- checkout
- compliance
- DNS
- Cloudflare
- Nginx
- systemd
- firewall
- certificate configuration
- broad robots changes
- broad canonical changes
- mass deletion
- mass content replacement
- production deployment
- high risk
- critical risk

Development Lifecycle Tests

Test tracking:

- candidate
- awaiting_approval
- submitted
- planning
- executing
- validating
- ready_for_merge
- merged
- deployment_pending
- deployed
- completed
- blocked
- failed
- cancelled

Project Memory Integration Tests

Test safe memory capture for:

- cycle summary
- new finding
- resolved finding
- recurring finding
- dispatched task
- blocked task
- failed task
- completed task
- SEO trend
- performance trend
- availability incident
- technical debt
- next actions

Verify handoff context explains:

- observation
- action taken
- remaining work
- failure
- do-not-repeat guidance
- approval requirement
- next step

Continuous Operation Tests

Verify:

- manager itself does not create uncontrolled infinite loop
- repeated run_cycle works
- external scheduler model supported
- cadence hints remain advisory
- no hard-coded cron
- no direct systemd timers
- cycle limit enforcement
- deferred work preserved

Cycle Result Tests

Verify result includes:

- cycle_id
- project_id
- started_at
- completed_at
- status
- observations_processed
- findings_created
- findings_updated
- findings_resolved
- task_candidates_created
- tasks_auto_dispatched
- tasks_awaiting_approval
- tasks_deferred
- critical_findings
- estimated_cost
- development_run_ids
- warnings
- safe_failure_codes
- next_recommended_actions

Test statuses:

- completed
- completed_with_warnings
- blocked
- failed
- cancelled

Final Report Tests

Verify report contains:

- site health summary
- SEO summary
- performance summary
- availability summary
- security summary
- accessibility summary
- ecommerce summary where applicable
- new findings
- recurring findings
- resolved findings
- automatically started work
- approval-waiting work
- completed development work
- deferred work
- critical alerts
- cost summary
- next recommended actions

Verify report excludes:

- secrets
- API keys
- credentials
- tokens
- authorization headers
- cookies
- full customer data
- raw HTML
- raw provider responses
- raw tracebacks
- unrestricted filesystem paths

Concurrency Tests

Test:

- concurrent observation ingestion
- concurrent equivalent findings
- concurrent task generation
- concurrent duplicate dispatch
- concurrent cycle execution
- no duplicate development run
- bounded locks
- no deadlock
- no leaked threads

Event Tests

Test safe events:

- operations_cycle_started
- observations_ingested
- finding_created
- finding_updated
- finding_resolved
- critical_finding_detected
- task_candidate_created
- task_approval_required
- task_dispatched
- task_deferred
- task_blocked
- task_completed
- operations_cycle_completed
- operations_cycle_failed

Verify events contain only safe identifiers, finding types, severities, statuses, counts, timestamps, and safe failure codes.

Portability Tests

Verify:

- no OpenAI-specific logic
- no Anthropic-specific logic
- no Gemini-specific logic
- no direct WordPress network dependency
- CMS adapters are injected
- provider-neutral operation
- another platform can supply adapters without changing manager core

Failure Code Tests

Test safe propagation for:

- invalid_site_operations_config
- invalid_project_config
- unknown_project
- unsafe_url
- unsafe_path
- observation_failed
- seo_observation_failed
- performance_observation_failed
- availability_observation_failed
- security_observation_failed
- accessibility_observation_failed
- ecommerce_observation_failed
- finding_generation_failed
- task_generation_failed
- approval_required
- budget_blocked
- task_limit_reached
- dispatch_failed
- memory_capture_failed
- dependency_failed
- timeout
- cancelled

Repository Safety

- Do not create persistent temporary files in repository root.
- Clean up all temporary resources.
- Do not modify unrelated files.
- Tests must leave a clean working tree when started from a clean checkout.

Deliverables

- agent/tests/test_site_operations_manager.py
