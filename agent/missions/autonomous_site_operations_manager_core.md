Mission: Build Autonomous Site Operations Manager Core

Goal

Create the production-only autonomous site operations manager for continuous technical management, maintenance, SEO oversight, performance improvement, issue discovery, low-risk remediation planning, and development task creation for multiple websites and projects.

The manager acts as an autonomous technical operations lead.

It must continuously assess site health and generate safe, prioritized work for the existing Autonomous Development Supervisor while preserving project memory and requiring approval for high-risk actions.

Scope

- Generate production code only.
- Do not generate tests in this mission.
- Use Python standard library only.
- Do not add dependencies.
- Do not modify requirements.txt.
- Fully typed and compatible with Python 3.12.
- Do not execute real network requests directly.
- Do not execute Git directly.
- Do not execute shell commands directly.
- Do not deploy directly.
- Do not modify DNS, Cloudflare, Nginx, systemd, databases, credentials, or production infrastructure directly.
- All external operations must use injected interfaces.
- Reuse existing project memory and autonomous development supervisor interfaces where applicable.

Existing Components

Integrate with existing public interfaces where applicable:

- AutonomousDevelopmentSupervisor
- ProjectMemoryManager
- RuntimeService
- ProjectRegistry
- ExecutionReportWriter
- ProviderUsageLedger
- Validation Engine
- Retry Engine
- approval interfaces
- event sinks
- background worker abstractions

Do not reimplement those systems.

Public Interface

Provide:

- SiteOperationsConfig
- SiteOperationsManager
- SiteOperationsProjectConfig
- SiteObservation
- SiteFinding
- SiteFindingType
- SiteFindingSeverity
- SiteTaskCandidate
- SiteOperationsCycleResult
- SiteOperationsStatus
- build_site_operations_manager(config, dependencies=None)
- site_operations_status(manager)

Generated file:

- agent/operations/site_operations_manager.py

Operating Model

The manager must support repeated autonomous operation cycles.

Provide:

- register_project(project_config)
- unregister_project(project_id)
- run_cycle(project_id)
- run_all_projects_cycle()
- ingest_observations(project_id, observations)
- assess_findings(project_id)
- generate_task_candidates(project_id)
- dispatch_safe_tasks(project_id)
- approve_task(task_id, approval)
- reject_task(task_id, reason_code)
- status(project_id=None)
- latest_findings(project_id, limit)
- latest_events(limit)
- final_cycle_report(project_id)
- close()

Rules:

- Construction must not start background activity.
- One operation cycle must be deterministic for equivalent inputs.
- Duplicate observations must be idempotent.
- Duplicate findings must be deduplicated.
- Duplicate task dispatch must not create duplicate development runs.
- Project isolation must be strict.
- Public methods must be thread-safe.
- No unbounded waits.
- No leaked threads.

Project Configuration

Support:

- project_id
- site_name
- canonical_base_url
- repository_id
- default_branch
- allowed_paths
- denied_paths
- environment_name
- site_type
- cms_type
- ecommerce_enabled
- seo_enabled
- performance_monitoring_enabled
- availability_monitoring_enabled
- accessibility_monitoring_enabled
- security_monitoring_enabled
- content_quality_monitoring_enabled
- image_optimization_enabled
- broken_link_monitoring_enabled
- sitemap_monitoring_enabled
- robots_monitoring_enabled
- schema_monitoring_enabled
- automatic_low_risk_fixes_enabled
- automatic_medium_risk_fixes_enabled
- maximum_tasks_per_cycle
- maximum_estimated_cost_per_cycle
- minimum_severity_for_task_creation
- metadata

Configuration Rules

- Unknown fields must be rejected.
- Project ID must be non-empty.
- Canonical URL must be validated as a safe HTTP or HTTPS URL.
- Repository paths must be relative.
- Reject traversal paths and null bytes.
- Inputs must not be mutated.
- Secrets must not be accepted in project configuration.
- Provider credentials must remain outside project configuration.

Observation Sources

Use injected observation providers for:

- HTTP availability
- page status
- redirects
- response timing
- page metadata
- headings
- canonical tags
- robots directives
- sitemap state
- structured data summaries
- image summaries
- link summaries
- accessibility summaries
- performance metrics
- Core Web Vitals summaries
- security header summaries
- CMS health summaries
- ecommerce health summaries
- repository health summaries
- deployment health summaries
- search visibility summaries
- indexability summaries

The manager must not perform raw network access itself.

Site Finding Types

Support findings including:

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

Finding Severity

Support:

- info
- low
- medium
- high
- critical

Finding Fields

Support:

- finding_id
- project_id
- finding_type
- severity
- title
- safe_summary
- affected_url
- affected_component
- first_seen_at
- last_seen_at
- occurrence_count
- evidence_summary
- recommended_action
- estimated_risk
- estimated_effort
- auto_fix_eligible
- approval_required
- related_memory_records
- metadata

Never retain:

- authentication headers
- cookies
- session tokens
- full HTML pages
- private user content
- checkout data
- customer data
- credentials
- provider raw responses

SEO Management

The manager must continuously assess technical SEO.

Cover:

- titles
- meta descriptions
- canonical URLs
- indexability
- robots directives
- sitemap health
- heading hierarchy
- structured data
- broken links
- redirect quality
- duplicate-content signals
- thin-content signals
- orphan-page signals
- internal-link opportunities
- image alt text
- image optimization
- page performance
- mobile performance summaries
- Core Web Vitals
- crawlability
- search visibility trends
- indexing warnings

SEO Rules

- Never fabricate ranking data.
- Search visibility must come from injected verified sources.
- Do not generate spammy SEO changes.
- Do not keyword-stuff.
- Do not create doorway pages.
- Do not automatically remove high-value content.
- Do not automatically change canonical strategy without approval.
- Do not automatically change robots or noindex rules when impact is uncertain.
- Major sitewide SEO changes require approval.
- Safe metadata fixes may be classified low risk.
- Every SEO task must preserve user experience and factual accuracy.

Performance Management

Assess:

- response times
- page weight
- image weight
- image dimensions
- caching observations
- asset duplication
- render-blocking summaries
- Core Web Vitals
- repeated slow endpoints
- frontend regressions
- performance regressions after deployments

Safe performance actions may include task creation for:

- image optimization
- lazy loading
- asset cleanup
- caching improvements
- stylesheet cleanup
- JavaScript cleanup
- database-query review
- page-template optimization

Do not apply infrastructure-level changes directly.

Availability and Reliability

Assess:

- uptime observations
- repeated HTTP failures
- unexpected redirects
- deployment regressions
- recurring errors
- health-check failures
- application readiness failures

Critical availability findings must:

- create a critical finding
- prevent unrelated automatic changes if necessary
- create an urgent development task
- require escalation event
- preserve safe incident memory

Content and Product Quality

Support technical observations for:

- missing product images
- broken product images
- incomplete product metadata
- duplicate product pages
- stale product information
- inconsistent structured data
- missing image alt text
- technical content quality problems

Do not invent or alter commercial product facts without an authoritative source.

Security Monitoring

Support safe observation summaries for:

- missing security headers
- mixed content
- certificate warnings
- unexpected public exposure
- dependency-security summary from injected scanners
- authentication regression summary
- authorization regression summary

Rules:

- Security findings high or critical must not be auto-fixed unless an explicitly approved low-risk remediation exists.
- Security controls must never be weakened automatically.
- Raw vulnerability secrets or exploit material must not be persisted.
- Security findings must integrate with approval boundaries.

Finding Deduplication

Equivalent findings must be deduplicated using deterministic safe identifiers.

On recurrence:

- update last_seen_at
- increment occurrence_count
- preserve first_seen_at
- update severity only according to deterministic rules
- do not create duplicate development tasks unless prior task is closed or invalid

Prioritization

Calculate deterministic priority using:

- severity
- affected traffic scope when provided
- availability impact
- SEO impact
- conversion impact
- security impact
- recurrence
- regression status
- effort
- risk
- existing open task
- current project priority

Priority must not depend on hidden random values.

Task Candidate Generation

Convert actionable findings into safe SiteTaskCandidate objects.

Support:

- task_id
- project_id
- title
- objective
- finding_ids
- recommended_changes
- allowed_paths
- denied_paths
- risk_level
- approval_required
- auto_dispatch_eligible
- priority
- estimated_effort
- estimated_cost
- acceptance_criteria
- validation_requirements
- metadata

Task Rules

- Task candidates must be deterministic.
- Multiple related findings may be grouped when safe.
- Unrelated findings must not be grouped solely to reduce task count.
- Every task must have acceptance criteria.
- Every task must specify validation requirements.
- Every task must preserve project path restrictions.
- No secret values in tasks.
- No unrestricted filesystem access.

Automatic Development Dispatch

Use the injected AutonomousDevelopmentSupervisor.

For eligible tasks:

1. Create a DevelopmentRequest.
2. Preserve project ID.
3. Include task objective.
4. Include allowed and denied paths.
5. Include risk classification.
6. Include acceptance criteria.
7. Include validation requirements.
8. Submit to AutonomousDevelopmentSupervisor.
9. Persist safe dispatch result in project memory.

Auto-dispatch must only occur when:

- automatic_low_risk_fixes_enabled is true
- risk is low
- no approval category is triggered
- project budget allows it
- task limit for the cycle is not exceeded
- no equivalent active development run exists

Medium-risk auto-dispatch requires:

- automatic_medium_risk_fixes_enabled=true
- no approval-required category
- no security-sensitive change
- no deployment action
- no database migration
- no dependency addition
- no authentication or authorization change

High and critical risk tasks must never be auto-dispatched.

Approval Required Categories

Require explicit approval for:

- database schema changes
- destructive data changes
- authentication changes
- authorization changes
- secret changes
- dependency additions or removals
- payment logic
- checkout logic
- compliance logic
- DNS
- Cloudflare
- Nginx
- systemd
- firewall
- certificate configuration
- robots strategy changes with broad impact
- canonical strategy changes with broad impact
- mass deletion
- mass content replacement
- production deployment
- high risk
- critical risk

Development Lifecycle Tracking

Track dispatched tasks through:

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

Use safe identifiers from AutonomousDevelopmentSupervisor.

Project Memory Integration

Automatically write safe records for:

- operations cycle summary
- newly discovered findings
- resolved findings
- recurring findings
- dispatched development tasks
- blocked tasks
- failed tasks
- completed tasks
- SEO trend summary
- performance trend summary
- availability incident summary
- technical debt summary
- next recommended operations actions

The memory record must allow another AI/provider to understand:

- what was observed
- what action was taken
- what remains open
- what failed
- what must not be repeated
- what requires approval
- what should happen next

Do not copy full raw observations into memory.

Continuous Operation Model

The manager must support an external scheduler or background worker calling run_cycle() repeatedly.

The manager itself must not create an uncontrolled infinite loop.

Support recommended cadence hints:

- critical availability checks: frequent
- health and performance: regular
- SEO technical audit: daily or scheduled
- content quality review: scheduled
- repository health: after changes and scheduled
- full technical audit: periodic

Actual scheduling is delegated to an injected scheduler/background worker.

Do not hard-code external cron or systemd timers in this mission.

Cycle Limits

Enforce:

- maximum findings per cycle
- maximum task candidates per cycle
- maximum auto-dispatched tasks per cycle
- maximum estimated cost per cycle
- maximum cycle duration
- duplicate task prevention

If limits are reached:

- preserve remaining findings
- report deferred work
- continue in the next cycle

Operations Cycle Result

Return deterministic safe result containing:

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

Cycle status:

- completed
- completed_with_warnings
- blocked
- failed
- cancelled

Reports

Generate a safe final cycle report containing:

- project
- cycle
- site health summary
- SEO summary
- performance summary
- availability summary
- security summary
- accessibility summary
- ecommerce summary when applicable
- new findings
- recurring findings
- resolved findings
- work started automatically
- work awaiting approval
- completed development work
- deferred work
- critical alerts
- cost summary
- next recommended actions

The report must be understandable by both the user and another AI agent.

Do not expose:

- secrets
- API keys
- credentials
- tokens
- authorization headers
- cookies
- full customer data
- full user content
- raw HTML
- raw provider responses
- raw tracebacks
- unrestricted filesystem paths

Events

Emit safe deterministic events:

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

Events may contain only:

- project_id
- cycle_id
- finding_id
- task_id
- safe development run identifier
- finding type
- severity
- status
- counts
- timestamps
- safe failure code

Dependency Injection

Support injected interfaces for:

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

Do not instantiate real external clients inside the manager.

Portability

The manager must remain provider-neutral.

Rules:

- No direct OpenAI-specific logic.
- No direct Anthropic-specific logic.
- No direct Gemini-specific logic.
- No direct CMS-specific network client.
- No hard dependency on WordPress internals.
- CMS-specific observation and action adapters must be injected.
- Another platform must be able to reuse the manager by supplying adapters and credentials.

Failure Codes

Support safe failure codes including:

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

Security

- No secret logging.
- No request body logging.
- No raw page-body persistence.
- No customer-data persistence.
- No provider-response persistence.
- No raw exception exposure.
- No dynamic code execution.
- No dynamic imports.
- No subprocess.
- No os.system.
- No shell execution.
- No direct Git execution.
- No direct deployment execution.
- No direct DNS execution.
- No direct systemd execution.
- No direct Nginx execution.
- No unrestricted file writes.

Generated File Safety

- Do not import ast, importlib, subprocess, pty, pickle, shelve, or marshal.
- Do not use eval, exec, or compile.
- Do not use os.system.
- Generated code must not contain forbidden function-call patterns checked by Mission Runner.
- Generated code must pass py_compile.
- All existing unittest tests must pass.

Deliverables

- agent/operations/site_operations_manager.py
