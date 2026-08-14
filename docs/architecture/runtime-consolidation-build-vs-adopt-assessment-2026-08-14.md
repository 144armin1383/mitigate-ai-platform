# Runtime Consolidation / Build-vs-Adopt Assessment

Status: assessment only  
Mission ID: `m1786716360293515`  
Request ID: `canvas-20260814T140600Z-d184f8`  
Date: 2026-08-14  
Scope: MITIGATE AI Core, external runtimes, deployment/bootstrap portability, and governed autonomous execution architecture.

## Executive Summary

MITIGATE should **preserve MITIGATE Core as the authoritative governance and orchestration layer**. The repository shows that MITIGATE Core owns mission intent, request gating, policy boundaries, queue state, retry state, execution evidence, Git governance, durable mission definitions, disposable workspace allocation, and production deployment authority. Those responsibilities are MITIGATE-specific and should not be delegated wholesale to OpenHands, OpenClaw, Ruflo, Agent Canvas, Temporal, Celery, Kubernetes, or any AI-provider platform.

The strongest architecture direction is **runtime consolidation through adapters**, not core replacement:

1. **KEEP / BUILD INTERNALLY**: MITIGATE Core governance, request/mission lifecycle authority, Core Protection, approval policy, GitHub source-of-truth, project adapters, execution evidence normalization, durable mission definitions, bounded recovery policy, and portable bootstrap contract.
2. **ADOPT EXTERNAL TECHNOLOGY**: use OpenHands as the primary generic software-engineering executor for coding, shell, file editing, test-running, repository refactoring, and iterative development inside MITIGATE-owned disposable workspaces.
3. **HYBRID**: use OpenClaw selectively for MCP, tools, skills, browser/integration helpers, and persistent session capabilities, while retaining MITIGATE routing, policy, queue state, and Git boundaries.
4. **DEFER**: keep Ruflo benchmark-gated for swarm/multi-agent/memory coordination until it demonstrates measurable value over OpenHands subagents plus MITIGATE routing on representative workloads.
5. **HYBRID / DEFER**: evaluate external observability and workflow technologies only where they solve proven operational pain. Prometheus/OpenTelemetry can improve metrics/traces; Temporal/Celery/Redis/Kubernetes should not replace the current file-backed queue/systemd worker until mission concurrency, SLA, or multi-host requirements clearly exceed the current architecture.

MITIGATE is rebuilding some generic capabilities: coding loops, shell/file execution, generic tool/session runtime, patch application, custom retry plumbing, ad hoc observability, and parts of background workflow management. The right response is **not a large migration**. The smallest architecture-consistent response is to keep the existing governed queue and lifecycle, route generic execution through mature runtimes behind MITIGATE-owned adapters, and retire redundant native execution code only after parity tests prove the external path is safer and cheaper to maintain.

Final recommendation: **GO for continued runtime consolidation behind MITIGATE adapters; NO-GO for replacing MITIGATE Core or moving mission authority into any external runtime.**

## Repository and Architecture Inspection Performed

This assessment is based on inspection of the disposable worktree for mission `m1786716360293515`; canonical `main` was checked read-only and not modified. Key files inspected include:

- `README.md`
- `agent/README.md`
- `docs/architecture/ARCHITECTURE_V2.md`
- `docs/architecture/runtime-consolidation-assessment.md`
- `docs/architecture/RUFLO_INTEGRATION_CONTRACT.md`
- `docs/architecture/RUFLO_UPGRADE_POLICY.md`
- `docs/architecture/TECHNOLOGY_WATCHER.md`
- `docs/PORTABLE_AGENT_CANVAS_STACK.md`
- `docs/policies/RUNTIME_UPSTREAM_AND_BACKUP_POLICY.md`
- `docs/operations/runtime-consolidation-activation.md`
- `agent/config/external-runtimes.json`
- `agent/config/managed-components.json`
- `agent/runtime/mission_queue.py`
- `agent/runtime/production_request_queue_adapter.py`
- `agent/runtime/production_request_composition.py`
- `agent/runtime/production_runtime_api.py`
- `agent/runtime/background_worker.py`
- `agent/runtime/managed_workspace_mission_controller.py`
- `agent/runtime/runtime_consolidation_controller.py`
- `agent/runtime/task_scope_workspace_controller.py`
- `agent/runtime/runtime_mcp_server.py`
- `agent/runtime/runtime_gateway.py`
- `agent/runtime/checkpoint_store.py`
- `agent/runtime/mission_diagnostics.py`
- `agent/execution/runtime_adapter.py`
- `agent/execution/runtime_router.py`
- `agent/execution/workspace_manager.py`
- `agent/execution/managed_openhands_adapter.py`
- `agent/execution/external_openhands_runner.py`
- `agent/execution/openhands_adapter.py`
- `agent/execution/openclaw_adapter.py`
- `agent/execution/ruflo_adapter.py`
- `agent/execution/runtime_branch_publisher.py`
- `agent/execution/execution_outcome_coordinator.py`
- `agent/policies/core_protection.py`
- `agent/git/review_engine.py`
- `agent/memory/project_memory_manager.py`
- `agent/providers/*`
- `agent/orchestrator/*`
- `agent/integrations/agent-canvas/mitigate-runtime-overlay.js`
- `agent/bootstrap/*`
- `agent/maintenance/*`

## Current Architecture Assessment

### High-level architecture

Current MITIGATE architecture is already moving toward a layered control-plane model:

```text
User / Agent Canvas / MCP / Private API / Scheduler
        |
        v
MITIGATE Runtime API and Request Gate
- project scope
- provider/model selection
- budget and rate checks
- request validation
        |
        v
Planner -> Plan Validator -> Queue Enqueue Coordinator
        |
        v
Durable MissionQueue + durable mission definitions
        |
        v
Background worker / Runtime Consolidation Controller
        |
        v
Runtime Router + MITIGATE-owned adapter contract
        |
        +--> Managed OpenHands execution in disposable worktree
        +--> OpenClaw capability/session/tool surfaces
        +--> Ruflo benchmark-only swarm/memory surface
        |
        v
Evidence normalization -> Git review / policy / branch publication
        |
        v
MITIGATE review, approval, merge/deploy gates
```

This is directionally sound. The control plane is not merely an executor; it is the policy and continuity layer that makes autonomous execution safe.

### Mission orchestration

Current implementation:

- `ProductionRequestComposition` wires request gate, planner, validator, and queue coordinator.
- `RequestGateSelector` validates request ownership, project context, task support, provider/model availability, budgets, and rate limits.
- `PlanValidatorMissionBuilder` validates plans, dependencies, mission payload safety, and deterministic mission ordering.
- `QueueEnqueueCoordinator` enforces project-scoped queue resolution and uses batch enqueue where available.
- `MissionQueue` persists mission state to JSON with file locking, deterministic ordering, dependencies, retries, terminal states, cancellation, resume, and stale-running recovery.

Assessment: **KEEP / BUILD INTERNALLY**, with targeted simplification. Mission orchestration represents MITIGATE product semantics and governance; external workflow engines can supplement persistence/scale later but should not own mission meaning.

### Request and mission lifecycle

Current implementation:

- `RuntimePrivateAPI` provides localhost-bound authenticated API endpoints.
- `runtime_mcp_server.py` exposes governed `mitigate_submit_mission`, request status, mission status, and runtime verification tools.
- `ProductionRequestQueueAdapter` materializes safe mission-definition Markdown before queue visibility, rejects command-like payload keys, validates deliverables, enforces project ownership, and rolls back definitions on enqueue failure.
- Runtime data includes durable mission definitions under `/srv/mitigate/data/runtime/mission-definitions` and queue state under `/srv/mitigate/data/runtime/missions.json`.

Assessment: **KEEP / BUILD INTERNALLY**. This lifecycle is governance-critical. External technologies may improve durability or API ergonomics, but MITIGATE must own the schema, state transitions, policy gates, and request-to-mission lineage.

### Autonomous recovery

Current implementation:

- `RetryEngine`, `RetryBudget`, retry classification, queue retry projection, and retry runtime integration exist.
- `MissionQueue.recover_stale()` recovers running missions after worker restart without consuming retry budget.
- `DurableCheckpointStore` provides atomic local checkpoints.
- `HostRecoverySupervisor` quarantines generated runtime artifacts and blocks if non-generated canonical changes exist.
- `mission_diagnostics.py` and `autonomous_mission_diagnostics.py` expose bounded diagnostics and failure evidence.
- Existing self-healing docs show a deliberate fail-closed philosophy for path-policy and allowlist recovery.

Assessment: **HYBRID**. MITIGATE must retain recovery policy, retry budgets, path safety, evidence requirements, and fail-closed decisions. Generic implementation repair loops should increasingly be delegated to OpenHands/OpenClaw in disposable workspaces, with MITIGATE retaining the retry and acceptance boundary.

### Runtime routing

Current implementation:

- `RuntimeAdapter` defines provider-neutral `ExecutionRequest`, `ExecutionResult`, `RuntimeCapabilities`, `RuntimeStatus`, and evidence.
- `RuntimeRegistry` selects healthy adapters by capability.
- `RuntimeRouter` creates a fresh disposable workspace per provider attempt, records provider attempts, and only fails over on integration/runtime failures.

Assessment: **KEEP / BUILD INTERNALLY**. This is the correct boundary: external runtimes are interchangeable capability providers; MITIGATE owns routing, scope, evidence, and failover semantics.

### Provider failover

Current implementation:

- `RuntimeRouter` distinguishes failover-eligible reasons such as runtime unavailable, process start failure, workspace unavailable, network/connection, and runtime adapter exception.
- It refuses failover for policy, quota, credential, permission, approval, dirty-repository, and scope violations.

Assessment: **KEEP / BUILD INTERNALLY**. This is a key safety property. External runtime failover must not bypass governance. Improve coverage through adapter contract tests and more explicit typed failure codes, but keep the authority internal.

### Disposable workspaces

Current implementation:

- `DisposableWorkspaceManager` creates detached Git worktrees from explicit revisions under a workspace parent, refuses canonical workspace use, verifies the repository is clean before routing, and removes worktrees after execution.
- `ManagedOpenHandsRuntimeAdapter` and `OpenClawRuntimeAdapter` require `workspace_root` and reject canonical execution.

Assessment: **HYBRID**. MITIGATE should keep workspace ownership and scope policy. Execution providers can use their own internal sandboxing, but MITIGATE should continue allocating and verifying the outer workspace because it is the Git and policy boundary.

### Git governance

Current implementation:

- `GitReviewEngine` validates refs, performs read-only diffs, classifies high-risk/secret-like files, and returns risk/merge recommendations.
- `CoreProtection` blocks protected core and canonical test writes unless mission text carries explicit markers.
- `RuntimeBranchPublisher` can publish successful runtime changes to isolated branches after evidence and scope validation; it does not merge to main.
- Repository docs preserve GitHub as the source of truth and require backup/verified-main deployment gates.

Assessment: **KEEP / BUILD INTERNALLY**. GitHub remains the portable source of truth. MITIGATE-specific review and approval policy must stay internal even if GitHub Actions or branch protection provide additional enforcement.

### Approvals and policy boundaries

Current implementation:

- Request gate, core protection, deliverable allowlists, denied path handling, mission definition safety, Git review, and external-runtime adapter prompts all reinforce scoped authority.
- `RuntimePrivateAPI` rejects public wildcard binding and requires bearer-token auth where configured.
- Agent Canvas integration is explicitly non-authoritative and uses MITIGATE MCP for governed submissions.

Assessment: **KEEP / BUILD INTERNALLY**. This is MITIGATE Core’s central value. External policy engines such as Open Policy Agent may become useful for declarative rules later, but they should not replace MITIGATE’s decision model without a clear operational need.

### Persistent memory / handoff

Current implementation:

- `ProjectMemoryManager` defines rich portable memory records, decisions, work records, issues, handoff bundles, redaction, bounded payloads, retention policy, deterministic IDs, and event emission.
- The current concrete store inspected is `InMemoryProjectMemoryStore`, which is thread-safe but not durable.
- Architecture docs state canonical memory must remain readable and portable; semantic/vector memory is acceleration only.

Assessment: **HYBRID**. MITIGATE must own canonical portable memory and handoff schemas. Adopt external vector/semantic stores only as rebuildable acceleration. Add a durable Git-backed or file-backed memory store before relying on memory for autonomous continuity; do not make a vector database the canonical source.

### Diagnostics and observability

Current implementation:

- Bounded mission diagnostics collect Git status, mission metadata, runtime evidence, failure evidence, artifacts, and warnings.
- Runtime APIs keep event buffers.
- Retry metrics exist as in-process structures.
- Execution reporters persist structured reports.
- Runtime gateway exposes provider status and verification endpoints.

Assessment: **HYBRID**. Keep MITIGATE-owned evidence and audit records. Adopt OpenTelemetry/Prometheus-style metrics/traces later for operational visibility if production needs exceed JSON reports and event buffers. Avoid making external observability mandatory for recovery.

### Scheduling and background execution

Current implementation:

- `BackgroundWorker` consumes `MissionQueue`, writes heartbeats/checkpoints, reports execution, handles retries/failures/blocks, and installs signal handlers.
- systemd services/timers manage runtime API, worker, MCP, gateway, panel, and managed auto-update.
- `managed-components.json` enables scheduled updates through repository-maintained scripts.

Assessment: **HYBRID now, DEFER large workflow engine**. For current single-host/low-concurrency operation, systemd plus file queue is portable and low overhead. Temporal/Celery/Redis/APScheduler should be evaluated only when requirements demand distributed scheduling, long-running workflow history, concurrency control beyond file locks, or delayed jobs at scale.

### MCP integration

Current implementation:

- `runtime_mcp_server.py` exposes MITIGATE runtime status, OpenClaw/Ruflo verification, submit mission, request status, and mission status.
- `runtime_mcp_server_extended.py` adds autonomous diagnostics/recovery helpers.
- The MCP instructions explicitly say MITIGATE Core owns planning, policy, approvals, mission state, Git governance, and runtime routing.

Assessment: **HYBRID / ADOPT MCP STANDARD**. MITIGATE should keep its MCP tools and boundaries, while adopting MCP as the external interoperability protocol. Do not expose arbitrary shell or canonical repository access through MCP.

### Agent Canvas integration

Current implementation:

- Agent Canvas runs as an external managed component on localhost.
- `mitigate-runtime-overlay.js` injects MITIGATE runtime status and MCP config into Canvas conversations without modifying upstream Canvas files.
- Nginx injection is external to the upstream image and fails open so Canvas remains usable if the overlay breaks.
- `PORTABLE_AGENT_CANVAS_STACK.md` documents a fresh-server recovery flow and security boundaries.

Assessment: **HYBRID**. Keep Agent Canvas as the interactive UI/conversation surface; keep MITIGATE runtime status overlay external and non-invasive. Do not fork Canvas or move MITIGATE governance into Canvas.

### OpenHands integration

Current implementation:

- `external-runtimes.json` pins `openhands-sdk` `1.42.1` as active primary software-engineering execution provider.
- `ManagedOpenHandsRuntimeAdapter` runs OpenHands in a separately managed venv.
- `ExternalOpenHandsRunner` isolates environment, state root, subprocess execution, timeout cleanup, preflight checks, and bounded evidence.
- `OpenHandsRuntimeAdapter` rejects canonical workspace use and detects scope violations.

Assessment: **ADOPT EXTERNAL TECHNOLOGY** for generic software-engineering execution. MITIGATE should reduce custom code generation/execution loops in favor of OpenHands behind the adapter, while retaining mission authority and evidence normalization.

### OpenClaw integration

Current implementation:

- `external-runtimes.json` pins OpenClaw `2026.7.1-2` as active-selective.
- `OpenClawRuntimeAdapter` exposes coding, terminal, file editing, tests, browser, MCP, skills, persistent sessions, isolated workspace, and remote execution capabilities.
- The adapter supports read-only MCP status verification and headless `agent exec` inside MITIGATE-provided workspaces.

Assessment: **HYBRID**. Use OpenClaw selectively for skills/tools/MCP/session and browser/integration capabilities. Do not make it the default coding authority until OpenHands comparison shows a clear advantage for specific task classes.

### Ruflo integration

Current implementation:

- `external-runtimes.json` pins Ruflo `3.38.9` as benchmark-only.
- `RUFLO_INTEGRATION_CONTRACT.md` explicitly forbids Ruflo owning mission state, policy, approvals, Git authority, durable memory, or provider selection.
- `RufloRuntimeAdapter` blocks non-benchmark execution and supports `doctor --json` verification only.

Assessment: **DEFER** for production mission execution; **HYBRID** for benchmark/evaluation. Ruflo may be valuable for multi-agent/swarm/memory coordination, but only after representative benchmarks demonstrate measurable benefit over simpler OpenHands/OpenClaw plus MITIGATE routing.

### Deployment/bootstrap portability

Current implementation:

- Bootstrap scripts install MITIGATE, external runtimes, Agent Canvas, MCP, remote access, runtime consolidation, and recovery.
- systemd service definitions are version-controlled.
- `deploy_verified_main.sh` enforces verified GitHub backup/rolling-main deployment gates.
- External runtime installs live outside the MITIGATE venv.
- Docs require secrets outside Git and fresh-server recovery from GitHub plus config/secrets.

Assessment: **KEEP / HYBRID**. Keep repository-owned bootstrap and systemd because they are portable and low overhead. Consider Ansible or a minimal declarative host bootstrap layer later if fresh-server rebuild frequency or drift grows, but avoid Kubernetes or heavyweight orchestration for a single-server control plane.

## Current Strengths

1. **Correct authority boundary**: MITIGATE Core, not external runtimes, owns policy, mission state, approvals, Git governance, and evidence.
2. **Provider independence**: OpenHands, OpenClaw, and Ruflo are behind adapters with normalized capabilities and results.
3. **Disposable workspace model**: execution happens in isolated worktrees, reducing failed-attempt contamination.
4. **Fail-closed governance**: scope violations, credentials/quota issues, and policy failures are not bypassed via failover.
5. **Portable source of truth**: GitHub remains canonical for code, docs, policies, runtime adapters, and bootstrap assets.
6. **Non-invasive Canvas integration**: MITIGATE overlays and MCP injection do not fork or patch upstream Canvas images.
7. **Managed external runtime lifecycle**: components are pinned, health-checked, and upgraded through repository-managed scripts.
8. **Strong documentation direction**: existing architecture docs already define target boundaries and non-negotiable rules.
9. **Reasonable single-host operational footprint**: file queue, systemd, and local JSON reports avoid heavyweight infrastructure.
10. **Security-aware interfaces**: API auth, localhost binding, safe mission definition rendering, forbidden payload keys, redaction, bounded diagnostics, and path checks are visible in code.

## Current Weaknesses

1. **Multiple overlapping execution paths**: legacy `mission_runner.py`, `AutonomousController`, runtime consolidation controller, OpenHands adapter, OpenClaw adapter, patch engine, and repair loops overlap.
2. **File-backed queue limits**: `MissionQueue` is simple and portable, but lacks durable worker ownership, distributed concurrency, rich scheduling semantics, and transactional multi-record state beyond best-effort rollback.
3. **Memory durability gap**: the inspected concrete project memory store is in-memory; durable portable memory needs a production-grade file/Git implementation or clear integration point.
4. **Observability is fragmented**: events, reports, diagnostics, retry metrics, gateway status, and checkpoints exist but are not unified under standard traces/metrics.
5. **Custom API stack**: `http.server`-based APIs are minimal and portable, but lack mature middleware, schema generation, request tracing, OpenAPI docs, and operational hardening of frameworks like FastAPI/Uvicorn.
6. **External runtime version lifecycle is script-heavy**: bash/systemd scripts are portable but can be harder to test and compose than declarative automation.
7. **Adapter evidence variance**: OpenHands/OpenClaw/Ruflo metadata shapes differ; more typed failure codes and contract tests would improve maintainability.
8. **Ruflo value not proven**: current Ruflo integration is correctly benchmark-gated, but there is not yet enough evidence to adopt it for production swarms.
9. **Canvas injection is brittle by nature**: Nginx `sub_filter` and JS fetch wrapping are intentionally non-invasive but can break with upstream HTML/API changes.
10. **Prunable stale worktrees exist on host**: read-only `git worktree list` showed several prunable `/tmp` worktrees. This is not a production migration issue in this mission, but it indicates cleanup hygiene should be monitored.

## Technical Debt

| Area | Debt | Impact | Recommendation |
|---|---|---:|---|
| Legacy mission runner | Monolithic generation/execution/validation loop overlaps with OpenHands path | High maintenance cost | Shrink to compatibility/fallback after OpenHands parity |
| Native patch/code generation | Custom patch and code generation duplicates mature coding-agent capabilities | Medium-high | Keep validators/review; reduce generic generation loop |
| Retry/recovery components | RetryEngine, RetryBudget, repair loops, runtime integration, and queue retries are spread across modules | Medium | Normalize retry authority around queue + policy + typed failure classes |
| Queue persistence | JSON queue is portable but limited for scale and crash semantics | Medium | Keep now; define migration criteria before adopting external queue |
| Memory persistence | Rich schema but in-memory concrete store inspected | Medium-high | Add durable Git/file store; optional vector index only as cache |
| Observability | Reports/events/diagnostics are useful but fragmented | Medium | Add standard metrics/traces without replacing evidence records |
| Bootstrap scripts | Many shell scripts and systemd drop-ins are powerful but procedural | Medium | Add idempotent validation and possibly Ansible later |
| Adapter contracts | Optional runtime adapters use normalized result but differ in metadata and failure code granularity | Medium | Add adapter conformance tests and failure-code registry |
| Canvas overlay | Non-invasive but dependent on upstream UI structure | Low-medium | Keep fail-open; add compatibility tests |

## Duplicate / Rebuilt Capabilities

MITIGATE is intentionally building governance-specific systems. Those should remain internal. However, several generic capabilities are being rebuilt and should be reduced over time:

| Capability being rebuilt | Existing MITIGATE implementation | Mature external candidate | Recommendation |
|---|---|---|---|
| Generic coding agent loop | `mission_runner.py`, `CodeGenerator`, `AutonomousController`, patch generation | OpenHands | Adopt OpenHands; shrink native loop to fallback and validation |
| Shell/file execution | native subprocess/file editing paths, patch engine | OpenHands/OpenClaw | Delegate execution; keep path validation and review |
| Agent tools/skills/session runtime | custom plugin/task/runtime patterns | OpenClaw, MCP ecosystem | Hybrid; use only stable allowlisted surfaces |
| Multi-agent swarm | potential MITIGATE-native expansion | Ruflo, OpenHands subagents | Defer Ruflo until benchmark value proven |
| Workflow scheduling | file queue + systemd loops | systemd timers now; APScheduler/Temporal later | Keep systemd/file queue now; defer heavy engine |
| Metrics/tracing | event buffers, reports, retry metrics | OpenTelemetry, Prometheus | Hybrid later; keep MITIGATE evidence canonical |
| Vector/semantic memory | planned native memory acceleration | SQLite/pgvector/Qdrant/Chroma/etc. | Defer as rebuildable cache; never canonical |
| API framework capabilities | custom `http.server` APIs | FastAPI/Uvicorn | Defer unless API surface/ops burden grows |

## Build-vs-Adopt Decision Matrix

Legend: **Low / Medium / High** ratings describe the adoption pressure or concern. Recommendation values are required mission classifications.

| Subsystem | Recommendation | Technical maturity | Reliability | Maintainability | Security/isolation | Governance compatibility | Agent suitability | Portability | Ops complexity | CPU/RAM overhead | Lock-in | Migration risk | Rationale |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MITIGATE Core governance | KEEP / BUILD INTERNALLY | High | High | Medium | High | High | High | High | Medium | Low | Low | High if replaced | Core authority is product-specific and safety-critical. |
| Request gate and policy selector | KEEP / BUILD INTERNALLY | Medium-high | High | Medium | High | High | High | High | Low | Low | Low | Medium | Project/provider/budget policy is MITIGATE-owned. |
| Planner-to-queue mission builder | KEEP / BUILD INTERNALLY | Medium | High | Medium | High | High | High | High | Low | Low | Low | Medium | Encodes mission schema and dependencies. |
| MissionQueue JSON file queue | KEEP / BUILD INTERNALLY now; HYBRID later | Medium | Medium | Medium | High | High | Medium | High | Low | Low | Low | Medium | Adequate single-host queue; external queue only when scale demands. |
| Background worker/systemd | HYBRID | High for systemd | Medium-high | Medium | High | High | Medium | High on Linux | Low-medium | Low | Low | Medium | Keep systemd; evaluate scheduler only if requirements grow. |
| Runtime adapter contract | KEEP / BUILD INTERNALLY | Medium-high | High | High | High | High | High | High | Low | Low | Low | Medium | Correct provider-neutral boundary. |
| Generic coding execution | ADOPT EXTERNAL TECHNOLOGY | High with OpenHands | Medium-high | High | Medium-high if sandboxed | High via adapter | High | Medium-high | Medium | Medium | Medium-low | Medium | OpenHands reduces custom coding-loop burden. |
| Tool/skills/MCP/session layer | HYBRID | Medium-high with OpenClaw/MCP | Medium | Medium-high | Medium | Medium-high via allowlist | High | Medium | Medium | Medium | Medium-low | Medium | Use selected stable OpenClaw/MCP capabilities. |
| Multi-agent swarm | DEFER | Unproven in MITIGATE | Unknown | Unknown | Unknown | Medium via adapter | Potentially high | Medium | Medium-high | Medium-high | Medium | High | Ruflo must earn adoption through benchmarks. |
| Disposable workspace allocation | HYBRID | High with Git worktrees | High | Medium | High | High | High | High | Low | Low | Low | Low | Keep MITIGATE outer workspace; providers may add sandboxing. |
| Git governance/review | KEEP / BUILD INTERNALLY | Medium-high | High | Medium | High | High | High | High | Low | Low | Low | High if replaced | GitHub is canonical; MITIGATE policy review is specific. |
| Core Protection | KEEP / BUILD INTERNALLY | High | High | High | High | High | High | High | Low | Low | Low | High | Fail-closed rules must remain internal. |
| Persistent canonical memory | KEEP / BUILD INTERNALLY | Medium | Medium | Medium | High | High | High | High | Low | Low | Low | Medium | MITIGATE owns portable memory; add durable store. |
| Semantic/vector memory | DEFER / HYBRID later | High externally | Medium | Medium | Medium | Medium if cache only | High | Medium | Medium | Medium-high | Medium | Medium | Use only rebuildable acceleration after canonical memory exists. |
| Diagnostics/evidence | KEEP / HYBRID | Medium-high | High | Medium | High | High | High | High | Low | Low | Low | Medium | Evidence canonical; metrics/traces can be external. |
| Metrics/tracing | HYBRID | High with OpenTelemetry/Prometheus | High | High | Medium-high | High if non-authoritative | Medium | High | Medium | Low-medium | Low | Low-medium | Add standard telemetry without replacing reports. |
| MCP integration | HYBRID / ADOPT STANDARD | High | Medium-high | High | Medium | High via MITIGATE tools | High | High | Low | Low | Low | Low | MCP is a good interoperability standard. |
| Agent Canvas UI | HYBRID | High enough | Medium-high | High if no fork | Medium | High if non-authoritative | High | Medium | Medium | Medium | Medium | Low-medium | Keep as UI, not control plane. |
| Deployment/bootstrap | KEEP / HYBRID | Medium-high | Medium-high | Medium | High | High | Medium | High | Medium | Low | Low | Medium | Keep scripts/systemd; add declarative tooling only if drift grows. |
| Managed runtime upgrades | HYBRID | Medium | Medium | Medium | High with pins | High | Medium | High | Medium | Medium during upgrades | Low-medium | Medium | Keep exact pins, compatibility tests, rollback. |
| Private Runtime API | KEEP now; DEFER framework migration | Medium | Medium-high | Medium | Medium-high | High | Medium | High | Low | Low | Low | Medium | Custom API sufficient now; FastAPI only if API complexity grows. |

## Component-by-Component Recommendations

### 1. Mission orchestration

Recommendation: **KEEP / BUILD INTERNALLY**.

MITIGATE should own request decomposition, mission identity, dependencies, task type, project context, policy profile, and queue submission. External planners or agents may assist with plans, but the mission schema and validation must remain MITIGATE-owned.

External comparison:

- OpenHands can execute a mission but should not own the mission queue.
- Ruflo can orchestrate agents but should not own MITIGATE mission state.
- Temporal can own workflow histories but would introduce infrastructure overhead and a second source of lifecycle truth unless carefully constrained.

### 2. Request and mission lifecycle

Recommendation: **KEEP / BUILD INTERNALLY**.

The current `RuntimePrivateAPI` + request gate + planner + mission builder + queue adapter path correctly preserves project scope, request IDs, mission IDs, and durable mission definitions. Keep this path authoritative.

Potential improvement: introduce a typed request/mission schema package shared by API, MCP, queue adapter, and tests to reduce drift.

### 3. Autonomous recovery

Recommendation: **HYBRID**.

MITIGATE should own retry classification, retry budget, bounded recovery, diagnostics, and final acceptance. OpenHands/OpenClaw can perform implementation repair inside disposable workspaces. Ruflo can be evaluated for coordinating multiple repair agents but should not own recovery state.

### 4. Runtime routing and provider failover

Recommendation: **KEEP / BUILD INTERNALLY**.

The current `RuntimeRouter` behavior is appropriate: failover only on provider/runtime failures, never on policy/quota/credential/scope/approval failures. This protects governance from accidental bypass.

Potential improvement: replace string-marker failure detection with a typed `failure_code` enum in `ExecutionResult`.

### 5. Disposable workspaces

Recommendation: **HYBRID**.

Keep MITIGATE-owned Git worktree allocation and cleanup. Add provider-native sandboxing where useful, but do not rely on provider sandboxes as the only isolation layer.

### 6. Git governance

Recommendation: **KEEP / BUILD INTERNALLY**.

GitHub should remain canonical. MITIGATE should keep Git review, Core Protection, branch publication policy, and deployment gates. GitHub Actions and branch protection can enforce but not define MITIGATE policy.

### 7. Approvals and policy boundaries

Recommendation: **KEEP / BUILD INTERNALLY**.

Approval/risk policy is product authority. External engines may encode declarative rules later, but MITIGATE must keep the final decision and audit trail.

### 8. Persistent memory / handoff

Recommendation: **HYBRID**.

MITIGATE should keep canonical memory/handoff schemas and implement durable portable storage. External vector/semantic stores can be added later as indexes that can be rebuilt from canonical records.

Immediate improvement: add or certify a durable Git-backed/file-backed `ProjectMemoryStore` and tests that prove fresh-server recovery without any vector DB.

### 9. Diagnostics and observability

Recommendation: **HYBRID**.

Keep MITIGATE evidence, reports, and diagnostics authoritative. Add OpenTelemetry/Prometheus later for metrics/traces, not as the audit source.

### 10. Scheduling and background execution

Recommendation: **HYBRID now; DEFER heavy adoption**.

systemd timers/services are appropriate for the current portable single-host architecture. Consider APScheduler for in-process scheduled jobs if cron-like complexity grows. Consider Temporal/Celery/Redis only if the platform requires distributed workers, large concurrency, durable timers, or complex human-in-the-loop workflow histories.

### 11. MCP integration

Recommendation: **HYBRID / ADOPT MCP STANDARD**.

MCP is a useful standard boundary. MITIGATE should expose only governed tools and keep canonical repository access restricted.

### 12. Agent Canvas integration

Recommendation: **HYBRID**.

Use Agent Canvas for interactive UI and conversations. Preserve non-invasive overlay and MCP injection. Do not fork or make Canvas authoritative.

### 13. OpenHands integration

Recommendation: **ADOPT EXTERNAL TECHNOLOGY**.

Use OpenHands as the primary execution provider for software-engineering tasks. It should replace/simplify generic coding loop, shell/file editing execution, test-running loop, and some native repair behavior.

MITIGATE must still own:

- mission authority;
- allowed and denied paths;
- base revision;
- disposable workspace allocation;
- provider selection and failover;
- budget/rate limits;
- final evidence acceptance;
- Git branch/review/approval/deployment.

### 14. OpenClaw integration

Recommendation: **HYBRID**.

Use OpenClaw for tools, skills, MCP, browser/integration helpers, and persistent-session capabilities after allowlist and sandbox controls. Keep it optional and adapter-scoped.

### 15. Ruflo integration

Recommendation: **DEFER production adoption; HYBRID benchmark-only**.

Continue benchmark-gated evaluation. Adopt only specific capabilities that demonstrably improve throughput, quality, reliability, or coordination for MITIGATE workloads.

### 16. Deployment/bootstrap portability

Recommendation: **KEEP / HYBRID**.

Keep repository-owned bootstrap scripts, systemd units, Docker Compose for Agent Canvas, external runtime pins, and verified-main deployment gates. Evaluate Ansible only if bootstrap drift or manual rebuilds become frequent.

## Recommended Target Architecture

```text
                    GitHub canonical repository
       policies, docs, bootstrap, adapters, tests, memory snapshots
                                  |
                                  v
User/API/Scheduler/Agent Canvas -> MITIGATE Runtime API/MCP
                                  |
                                  v
                         Request Gate Selector
      project scope | provider/model | budgets | rate limits | approvals
                                  |
                                  v
                      Planner + Mission Builder
                                  |
                                  v
                    Durable MITIGATE MissionQueue
                mission definitions | dependencies | retry state
                                  |
                                  v
                         Background Worker
                 checkpoints | reports | diagnostics | heartbeat
                                  |
                                  v
                         Runtime Router
    failover rules | capability matching | disposable workspace allocation
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
        OpenHands adapter    OpenClaw adapter     Ruflo adapter
        coding executor      tools/MCP/skills     benchmark/swarm only
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                         Execution evidence
                                  |
                                  v
                 MITIGATE review, approval, Git branch,
                    validation, merge/deploy, rollback
```

Target principles:

1. MITIGATE Core remains the only source of governance truth.
2. External runtimes are optional capability providers.
3. Every external runtime uses a MITIGATE-owned adapter contract.
4. Disposable workspaces are allocated by MITIGATE.
5. GitHub remains canonical and portable.
6. Durable memory is readable without external vector/runtime dependencies.
7. Recovery is bounded and fail-closed.
8. Runtime updates are pinned, tested, and rollback-capable.

## Technologies to Keep

| Technology/component | Keep rationale |
|---|---|
| MITIGATE Core | Product-specific governance and orchestration authority. |
| GitHub | Portable source of truth and review/backup anchor. |
| MissionQueue for current scale | Low-overhead, portable, deterministic single-host queue. |
| systemd services/timers | Mature, low-overhead host process management for current deployment model. |
| Core Protection | Fail-closed policy boundary. |
| GitReviewEngine | MITIGATE-specific risk classification and merge recommendation. |
| Durable mission definitions | Human-readable, portable request/mission audit artifacts. |
| Disposable Git worktrees | Simple, effective outer isolation boundary. |
| Agent Canvas | Useful interactive UI when kept non-authoritative. |
| MCP | Useful interoperability protocol when constrained to governed tools. |
| Bootstrap scripts | Portable operational knowledge encoded in repository. |

## Technologies to Replace or Reduce

| Current capability | Replace/reduce with | Timing | Notes |
|---|---|---|---|
| Monolithic `mission_runner.py` coding/execution loop | OpenHands adapter | Now through phased migration | Keep only fallback/compatibility until parity proven. |
| Native generic code-generation loop | OpenHands | Now | MITIGATE should retain prompts/policy, not generic coding internals. |
| Native shell/file editing execution | OpenHands/OpenClaw in disposable workspaces | Now/later by task type | Keep validators and evidence normalization. |
| Generic repair implementation loops | OpenHands/OpenClaw execution, MITIGATE retry policy | Phased | Do not remove fail-closed recovery policy. |
| Custom tool/session runtime expansion | OpenClaw/MCP | Selective | Adopt only stable, allowlisted surfaces. |
| Ad hoc metrics-only visibility | OpenTelemetry/Prometheus | Later | Do not replace canonical reports/evidence. |
| Procedural bootstrap drift | Optional Ansible/declarative checks | Later | Only if operational drift becomes material. |

## Technologies to Integrate

### OpenHands

Adoption recommendation: **Recommended now**.

What MITIGATE would use it for:

- repository-aware software-engineering execution;
- terminal commands and tests inside disposable workspaces;
- file editing and refactoring;
- dependency maintenance;
- iterative coding repair loops;
- optional sub-agent workflows if stable.

Existing MITIGATE code it could replace or simplify:

- most generic `mission_runner.py` generation/execution behavior;
- native `CodeGenerator` and patch-generation paths for software-engineering tasks;
- custom shell/file editing loops;
- parts of autonomous repair implementation, while keeping MITIGATE retry policy.

MITIGATE must still own internally:

- mission/request state;
- policy, approvals, and allowed paths;
- runtime routing/failover;
- disposable workspace creation;
- Git branch publication/review;
- durable memory/evidence;
- provider budget/rate limit policy;
- deployment authority.

Integration boundaries:

- `ExecutionRequest` and `ExecutionResult` only;
- managed external venv;
- no canonical workspace execution;
- bounded stdout/stderr and provider metadata;
- no direct merge/push/deploy by OpenHands.

Risks:

- SDK/API changes;
- LLM quota/credential failures;
- increased CPU/RAM during agent execution;
- tool behavior changes;
- hidden provider coupling if prompts/config assume one model.

Rollback strategy:

- disable OpenHands adapter or mark unhealthy;
- route to native fallback or OpenClaw if capability-compatible;
- keep previous pinned OpenHands version in external runtime configuration;
- keep canonical repo untouched because execution occurs in disposable workspaces.

### OpenClaw

Adoption recommendation: **Recommended selectively now; broaden later only with evidence**.

What MITIGATE would use it for:

- MCP/tool/skill capability surfaces;
- browser/integration tools;
- persistent sessions where useful;
- selected headless agent execution for task types where it outperforms OpenHands.

Existing MITIGATE code it could replace or simplify:

- generic plugin/tool runtime expansion;
- some browser/integration helpers;
- selected MCP handling and external capability checks.

MITIGATE must still own internally:

- capability allowlists;
- mission and Git authority;
- workspace allocation;
- approval/risk policy;
- evidence normalization;
- secret scoping.

Integration boundaries:

- adapter contract;
- `openclaw mcp status --json` for verification;
- `openclaw agent exec --cwd <workspace>` for governed execution;
- no unsandboxed host execution by default;
- no canonical state ownership.

Risks:

- plugin trust and supply-chain risk;
- session state becoming non-portable;
- capability drift across versions;
- higher runtime overhead than native small helpers.

Rollback strategy:

- disable OpenClaw adapter and MCP capabilities;
- fall back to OpenHands/native paths;
- preserve MITIGATE-owned state because OpenClaw state is optional.

### Ruflo

Adoption recommendation: **Later, benchmark-gated only**.

What MITIGATE would use it for if proven:

- multi-agent/swarm orchestration;
- specialized developer/reviewer/test/security coordination;
- shared memory or RAG acceleration;
- observability/cost plugins;
- background coordination where it demonstrably improves outcomes.

Existing MITIGATE code it could replace or simplify:

- future native swarm code that should not be built prematurely;
- some multi-agent coordination glue if Ruflo proves stable;
- optional semantic-memory acceleration if rebuildable.

MITIGATE must still own internally:

- request, plan, mission, approval, and Git state;
- durable memory canonical records;
- provider routing and budget policy;
- final merge/deploy authority.

Integration boundaries:

- benchmark mode unless promoted;
- capability negotiation;
- version-pinned adapter;
- no Ruflo-only mission state;
- native fallback or safe stop on failure.

Risks:

- fast upstream changes;
- hidden assumptions around specific providers or agent frameworks;
- additional CPU/RAM overhead;
- operational complexity without proven payoff;
- migration complexity if state leaks into Ruflo.

Rollback strategy:

- keep Ruflo disabled/benchmark-only;
- drop adapter route without changing mission records;
- rebuild optional memory/cache from MITIGATE-owned sources.

### OpenTelemetry and Prometheus-compatible metrics

Adoption recommendation: **Later / incremental hybrid**.

What MITIGATE would use it for:

- runtime metrics;
- queue depth and latency;
- provider attempt timing;
- retry counts;
- health dashboards;
- alerting on worker/API/runtime degradation.

Existing MITIGATE code it could replace or simplify:

- some ad hoc metrics aggregation;
- manual event polling for operational dashboards.

MITIGATE must still own internally:

- execution reports;
- audit evidence;
- mission diagnostics;
- security-sensitive logs redaction.

Integration boundaries:

- metrics/traces are derived telemetry;
- never canonical mission evidence;
- no secrets in labels/spans;
- optional exporter.

Risks:

- exposing sensitive labels;
- added infrastructure;
- partial telemetry becoming mistaken for audit truth.

Rollback strategy:

- disable exporter;
- keep JSON reports and diagnostics unchanged.

### APScheduler / Temporal / Celery / Redis-backed queue

Adoption recommendation: **Defer; define trigger criteria first**.

What MITIGATE might use it for:

- delayed schedules;
- distributed workers;
- complex workflow histories;
- retries with durable timers;
- high-concurrency queueing.

Existing MITIGATE code it could replace or simplify:

- parts of `MissionQueue` persistence;
- systemd polling loops;
- custom stale-running recovery;
- some scheduling scripts.

MITIGATE must still own internally:

- mission schema and states;
- approval/risk policy;
- durable mission definitions;
- Git governance;
- evidence normalization.

Integration boundaries:

- external queue/workflow engine stores delivery mechanics only;
- MITIGATE remains lifecycle authority;
- migration must preserve queue export/import and rollback.

Risks:

- increased operational complexity;
- external database/broker dependency;
- CPU/RAM overhead;
- reduced fresh-server portability;
- second source of mission truth if not carefully bounded.

Rollback strategy:

- maintain JSON queue compatibility/export;
- keep systemd worker path as fallback during migration;
- migrate only after dual-write or replay tests prove safety.

### FastAPI/Uvicorn

Adoption recommendation: **Defer**.

What MITIGATE would use it for:

- richer private API;
- OpenAPI schemas;
- middleware;
- validation;
- better async request handling.

Existing MITIGATE code it could replace or simplify:

- parts of `RuntimePrivateAPI` custom handler code.

MITIGATE must still own internally:

- request gate;
- runtime facade;
- auth policy;
- failure-code mapping;
- lifecycle state.

Integration boundaries:

- framework is transport only;
- no behavior change to request/mission contracts.

Risks:

- added dependencies;
- migration bugs in auth/status mapping;
- more moving parts for bootstrap.

Rollback strategy:

- keep current `RuntimePrivateAPI` service until parity tests pass;
- run both behind localhost during transition if needed.

### Ansible

Adoption recommendation: **Later if drift grows**.

What MITIGATE would use it for:

- idempotent fresh-server bootstrap;
- host package/service configuration;
- reproducible nginx/systemd/runtime setup.

Existing MITIGATE code it could replace or simplify:

- some procedural shell-script orchestration;
- manual host drift checks.

MITIGATE must still own internally:

- bootstrap policy;
- exact runtime pins;
- secrets-outside-Git rule;
- verified deployment gate.

Integration boundaries:

- Ansible playbooks live in repo as automation, not runtime authority;
- shell scripts may remain wrappers for portability.

Risks:

- additional operator dependency;
- over-generalization for a single-host deployment.

Rollback strategy:

- retain current shell/bootstrap scripts;
- treat Ansible as optional validation/deployment path until proven.

## Technologies to Defer

| Technology | Defer reason | Re-evaluation trigger |
|---|---|---|
| Ruflo production swarm execution | Value not proven; current benchmark-only boundary is correct | Representative benchmark shows measurable success/quality/cost improvement |
| Temporal | Heavy infrastructure and workflow-state migration risk | Multi-host durable workflow requirements exceed MissionQueue/systemd |
| Celery + Redis/RabbitMQ | Adds broker dependency and operational overhead | High mission concurrency or distributed worker pool becomes necessary |
| Kubernetes | Too heavy for current single-server architecture | Multi-node deployment/SLA/isolation requirements demand orchestration |
| Vector database as memory authority | Violates portable canonical memory rule | Never as authority; only cache after durable memory exists |
| FastAPI migration | Current API adequate; migration risk without urgent benefit | API grows enough to require OpenAPI/middleware/async framework |
| Ansible/Terraform | Shell/systemd bootstrap currently sufficient | Fresh-server rebuilds or host drift become frequent |

## Migration Complexity

| Migration | Complexity | Risk | Suggested approach |
|---|---:|---:|---|
| Route more coding tasks to OpenHands | Medium | Medium | Contract tests, representative tasks, fallback retained |
| Shrink legacy mission runner | High | Medium-high | Only after OpenHands parity; remove one responsibility at a time |
| Add durable memory store | Medium | Medium | Git/file-backed implementation with migration-free start |
| Add telemetry exporter | Low-medium | Low-medium | Optional metrics/traces; no evidence schema replacement |
| Adopt OpenClaw capabilities | Medium | Medium | Capability allowlist, sandbox checks, task-type gating |
| Promote Ruflo beyond benchmark | High | High | Require benchmark evidence, rollback, no state ownership |
| Replace queue with external workflow engine | High | High | Defer; requires dual-run/export/replay strategy |
| API framework migration | Medium | Medium | Defer; transport-only replacement with compatibility suite |
| Declarative bootstrap layer | Medium | Low-medium | Optional alongside existing scripts |

## Risks

1. **Authority drift**: external runtimes may gradually accumulate mission state or memory unless adapter boundaries are enforced.
2. **Scope bypass through failover**: provider failover could bypass governance if failure classes are not strict and typed.
3. **External runtime churn**: OpenHands/OpenClaw/Ruflo APIs may change; pinned versions and compatibility tests are mandatory.
4. **Operational complexity creep**: adopting Redis, Temporal, Kubernetes, or multiple observability components too early could reduce portability.
5. **Memory fragmentation**: vector/session/runtime memory could diverge from MITIGATE canonical memory.
6. **Canvas integration fragility**: upstream UI/API changes can break overlay injection.
7. **Resource exhaustion**: multiple external runtimes plus agent execution may stress low-memory hosts, especially npm upgrades and parallel agents.
8. **Partial cleanup failures**: disposable workspace cleanup and stale worktrees need monitoring.
9. **Secrets exposure through telemetry or prompts**: external tools and telemetry must receive only scoped, redacted data.
10. **Premature deletion of working native paths**: removing fallback paths before parity tests could reduce reliability.

## Security and Governance Impact

Recommended consolidation improves security if MITIGATE keeps current boundaries:

- external runtimes execute in MITIGATE-created disposable workspaces;
- `.git`, `.env`, and secrets remain denied unless explicitly authorized by policy;
- scope violations are terminal and not failover-eligible;
- quota/credential failures are not bypassed;
- Core Protection stays authoritative;
- GitHub remains canonical;
- durable mission definitions and reports preserve auditability;
- Agent Canvas remains non-authoritative;
- MCP tools expose governed operations, not arbitrary host shell access.

The main governance risk is accidental delegation of state or decision-making to external runtimes. Every adoption must include tests proving that MITIGATE can disable the external component without losing mission records, policies, memory, or Git history.

## Operational Impact

Positive impact of recommended path:

- less custom runtime code to maintain;
- improved coding-task success through mature external agents;
- clearer runtime provider health and fallback;
- lower contamination risk from disposable workspaces;
- continued single-host portability;
- improved upgrade discipline through managed pins and health checks.

Negative/managed impact:

- more adapter compatibility testing;
- external runtime installations consume disk/RAM;
- upgrades need careful rollback points;
- operators must understand which system owns which state;
- telemetry or scheduler adoption could add services later.

## Resource / Infrastructure Impact

Current approach is resource-conscious:

- file queue and JSON reports have low CPU/RAM overhead;
- systemd timers/services have low overhead;
- Git worktrees use disk proportional to changed files and checkout metadata;
- OpenHands/OpenClaw/Ruflo add runtime-specific CPU/RAM and dependency overhead;
- npm-based upgrades may need swap and free disk, already reflected in managed-component policy.

Recommendations by resource impact:

| Option | CPU/RAM impact | Disk impact | Recommendation |
|---|---:|---:|---|
| Continue file queue/systemd | Low | Low | Keep |
| OpenHands execution | Medium during runs | Medium | Adopt for coding tasks |
| OpenClaw tools/sessions | Medium | Medium | Selective hybrid |
| Ruflo swarm | Medium-high | Medium | Defer until benchmark value proven |
| OpenTelemetry exporter | Low-medium | Low | Later optional |
| Prometheus stack | Medium | Medium | Later if dashboards/alerts needed |
| Redis/Celery/Temporal | Medium-high | Medium-high | Defer |
| Kubernetes | High | High | No-go for current architecture |

## Portability Impact

Recommended path preserves portability because:

- GitHub remains canonical;
- external runtimes are pinned and reinstallable;
- durable mission definitions are readable Markdown/JSON;
- queue and reports are local files that can be backed up/restored;
- secrets remain outside Git;
- Agent Canvas integration does not fork upstream;
- semantic memory and telemetry are optional caches/derived views.

Adopting heavyweight infrastructure too early would reduce portability. Any future adoption must include a fresh-server recovery test proving MITIGATE can reinstall from GitHub plus configuration/secrets without recoding.

## Recommended Implementation Phases

### Phase 0 — Preserve current boundaries

- Keep MITIGATE Core authoritative.
- Do not replace queue, policy, Git governance, or memory authority.
- Keep current external runtime pins and rollback policy.

### Phase 1 — Adapter contract hardening

- Add typed failure codes to `ExecutionResult`.
- Add adapter conformance tests for OpenHands, OpenClaw, and Ruflo.
- Verify failover never bypasses policy/quota/credential/scope failures.
- Verify every provider refuses canonical workspace execution.

### Phase 2 — OpenHands-first coding path

- Route representative documentation, bugfix, backend, test, and refactor missions to Managed OpenHands by default.
- Compare success, changed-file evidence, validation pass rate, runtime duration, and retry behavior against legacy paths.
- Keep native fallback until parity is proven.

### Phase 3 — Legacy execution shrink

- Remove or disable generic code-generation/shell/file-editing responsibilities from legacy `mission_runner.py` one at a time.
- Keep only MITIGATE-specific validation, policy, evidence, and fallback code.
- Require rollback branches and full contract tests.

### Phase 4 — Durable memory foundation

- Implement/certify a durable Git-backed or file-backed `ProjectMemoryStore`.
- Add export/import/fresh-server recovery tests.
- Only after this, evaluate optional semantic/vector memory indexes.

### Phase 5 — Selective OpenClaw capability adoption

- Define capability allowlist.
- Add plugin/session state portability rules.
- Adopt browser/MCP/skills capabilities where they remove native code or improve reliability.

### Phase 6 — Observability standardization

- Add optional OpenTelemetry/Prometheus-compatible metrics for queue depth, mission durations, provider attempts, retry counts, and runtime health.
- Keep reports/diagnostics as canonical evidence.

### Phase 7 — Ruflo benchmark gate

- Run representative multi-agent tasks.
- Compare Ruflo against OpenHands subagents plus MITIGATE routing.
- Adopt only specific capabilities that show measurable value.

### Phase 8 — Queue/scheduler reassessment

- Reassess file queue/systemd when concurrency, durability, delayed scheduling, or multi-host requirements exceed current design.
- If needed, design export/import and dual-run migration before adopting Temporal/Celery/Redis.

## Immediate Next Actions

1. Keep this mission documentation-only; perform no production migration.
2. Add typed runtime failure codes and adapter conformance tests in a future governed mission.
3. Define representative benchmark tasks for OpenHands vs OpenClaw vs Ruflo.
4. Measure runtime success rate, validation pass rate, duration, changed-file accuracy, and rollback cleanliness.
5. Create a durable memory store design mission.
6. Add a cleanup/doctor check for prunable stale worktrees and workspace parent disk usage.
7. Add explicit criteria for when external queue/workflow adoption becomes justified.
8. Add optional metrics exporter design only after deciding required dashboards/alerts.
9. Keep GitHub backup/verified-main deployment policy unchanged.
10. Preserve Agent Canvas overlay fail-open behavior and upstream no-fork rule.

## Final Go / No-Go Recommendations

### GO

- **GO**: Keep MITIGATE Core as authoritative governance/orchestration.
- **GO**: Continue runtime consolidation through MITIGATE-owned adapters.
- **GO**: Adopt OpenHands as the primary generic software-engineering executor in disposable workspaces.
- **GO**: Keep OpenClaw as selective tools/MCP/skills/session capability provider.
- **GO**: Preserve GitHub as canonical source of truth.
- **GO**: Preserve fail-closed policy, bounded recovery, and provider independence.
- **GO**: Add durable canonical memory storage before semantic/vector memory.
- **GO**: Add optional standard telemetry if it remains derived/non-authoritative.

### NO-GO

- **NO-GO**: Replace MITIGATE Core with OpenHands, OpenClaw, Ruflo, Agent Canvas, Temporal, or any provider platform.
- **NO-GO**: Move canonical mission state, approvals, durable memory, Git authority, or deployment authority into an external runtime.
- **NO-GO**: Adopt Ruflo for production swarms before benchmark evidence.
- **NO-GO**: Adopt Redis/Celery/Temporal/Kubernetes solely because they are common; require concrete scale/SLA triggers.
- **NO-GO**: Make vector memory canonical.
- **NO-GO**: Fork Agent Canvas or patch upstream container files for MITIGATE runtime UI.
- **NO-GO**: Remove working native fallback paths before external parity and rollback are proven.

### Final recommendation

Proceed with **incremental, adapter-based runtime consolidation**. MITIGATE should build internally where governance, safety, mission lifecycle, and portability are unique to the product; adopt external technologies where they replace generic execution/tooling work without taking authority. The immediate architectural priority is not more technology adoption; it is disciplined reduction of duplicate runtime code after OpenHands/OpenClaw/Ruflo compatibility evidence proves each reduction safe.
