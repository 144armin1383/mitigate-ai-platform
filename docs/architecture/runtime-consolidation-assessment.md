# MITIGATE AI Runtime Consolidation / Build-vs-Adopt Assessment

Status: assessment complete; migration not started.
Scope: documentation artifact only; no production architecture, configuration, code, permission, merge, deployment, or upstream-runtime changes.

## 1. Executive summary

MITIGATE is already partially consolidated. Repository evidence shows a Core-owned request API/MCP surface (`agent/runtime/runtime_mcp_server.py`, `production_runtime_api.py`), mission queue and worker (`mission_queue.py`, `background_worker.py`), replaceable runtime adapter contract (`agent/execution/runtime_adapter.py`), explicit router (`runtime_router.py`), disposable Git worktrees (`workspace_manager.py`), Core-owned branch publishing (`runtime_branch_publisher.py`), OpenHands/OpenClaw/Ruflo adapters, Agent Canvas overlay, provider/model governance, memory, audit, bootstrap, and upstream-version metadata.

The target direction is correct: MITIGATE should keep authority over intelligence, governance, mission state, approvals, auditability, project/business knowledge, memory, provider routing, security boundaries, Git authority, validation, and rollback, while external runtimes provide replaceable execution. Current custom generic runtime code remains significant: `mission_runner.py` (826 lines), `code_generator.py` (191), `retry_engine.py` (446), `autonomous_controller.py` (402), `background_worker.py` (860), `mission_queue.py` (510), and repair-loop files (674). Some is Core-specific and should remain; generic coding/shell/file/test/retry/repair loops should shrink after adapter parity.

Recommendation: **GO for phased migration planning and phases 1-2 only**. Do not delete legacy paths or make production dependency changes until OpenHands health, workspace-cleanliness regression tests, provider evidence, rollback switches, and fresh-server restore validation are complete.

## 2. Current MITIGATE capability inventory

| Capability | Repository evidence | Current state | Target ownership |
|---|---|---|---|
| Mission submission/status | MCP tools in `runtime_mcp_server.py`; request status in `production_runtime_api.py` | Exists | KEEP in Core |
| Request API and queue enqueue | `production_request_queue_adapter.py` writes definitions before queue visibility | Exists | KEEP in Core |
| Mission queue/worker | `mission_queue.py`, `background_worker.py` | Exists; custom | KEEP now, shrink later |
| Runtime contract/router | `runtime_adapter.py`, `runtime_router.py` | Exists | KEEP in Core |
| Disposable workspaces | `workspace_manager.py` creates detached worktrees and checks canonical cleanliness | Exists | KEEP policy/API |
| Runtime branch publishing | `runtime_branch_publisher.py` commits/pushes from worktree after scope match | Exists | KEEP in Core |
| OpenHands | `openhands_adapter.py`, `managed_openhands_adapter.py`, `external_openhands_runner.py` | Partially active | WRAP as primary coding runtime |
| OpenClaw | `openclaw_adapter.py`, gateway verify | Selective | WRAP for tools/MCP/browser/capabilities |
| Ruflo | `ruflo_adapter.py`, docs/evaluations, gateway verify | Benchmark-gated | WRAP diagnostic only |
| Agent Canvas | overlay and deploy assets | UI/MCP integration | WRAP as UI/submission only |
| MCP/tool gateway | `runtime_mcp_server_extended.py`, `runtime_gateway.py` | Exists | KEEP Core gateway, wrap tools |
| Provider/model governance | `agent/providers/*` | Exists | KEEP in Core |
| Memory | `project_memory_manager.py` | Exists | KEEP in Core |
| Core Protection | `core_protection.py`, manifest | Exists | KEEP in Core |
| Audit/evidence | execution report writer/outcome coordinator/checkpoints | Exists | KEEP in Core |
| Upstream versions | `external-runtimes.json`, `managed-components.json`, `upstream_manager.py`, upgrade scripts | Exists | KEEP in Core |
| Bootstrap/install | bootstrap scripts and systemd docs | Exists | KEEP in Core |
| Legacy generic execution | `agent/ai/*`, repair loops | Exists | REPLACE/SHRINK later |

Current version policy: `external-runtimes.json` pins OpenHands SDK `1.42.1`, OpenClaw `2026.7.1-2`, and Ruflo `3.38.9`, with rollback/disposable-test/no-fork policy. Runtime gateway status observed OpenClaw and Ruflo available; OpenHands is active through managed adapter/processes but is not yet surfaced in gateway `/v1/status`.

## 3. Current architecture map

```text
User / Panel / Agent Canvas
  -> MITIGATE MCP / production request API
  -> mission definitions + queue in /srv/mitigate/data/runtime
  -> background worker / runtime consolidation controller
  -> RuntimeRouter + RuntimeAdapter contract
  -> DisposableWorkspaceManager detached worktree
  -> OpenHands / OpenClaw / Ruflo adapter
  -> ExecutionEvidence
  -> MITIGATE branch publisher / review / audit
  -> GitHub canonical source of truth
```

Already exists: request API, queue, worker, adapter contract, OpenHands/OpenClaw/Ruflo adapters, disposable worktrees, branch publishing, MCP/gateway, provider/model governance, memory, Core Protection, audit, bootstrap, Canvas integration, managed-component update scripts. Partially implemented: full runtime selection policy, OpenHands status visibility, external-runtime compatibility/rollback verification, migration from legacy loops. Proposed: make OpenHands default for software work, OpenClaw selective capability runtime, Ruflo diagnostic-only, Canvas UI/submission only. Retire later: direct legacy canonical execution, custom generic coding/shell/file/test loops, ad hoc validation V4/self-healing patch paths, provider-specific durable mission state.

## 4. OpenHands capability map

Delegate to OpenHands through MITIGATE adapter: repository coding, debugging, refactoring, dependency maintenance, test generation/execution, bounded terminal operations, file editing, software-engineering agent loop, and isolated workspace execution. Evidence: `OpenHandsRuntimeAdapter.capabilities()` advertises coding, terminal, file editing, tests, MCP, skills, multi-agent, isolated workspace, and remote execution; `_validated_workspace()` requires a disposable Git checkout and refuses the canonical repository.

Keep outside OpenHands: mission authorization, task classification, allowed/denied paths, approvals, Core Protection, persistent memory, model/provider routing, budget/usage ledger, Git commit/push/merge/deploy authority, secrets, production mutation, audit/event persistence, and rollback.

Role: **primary software-engineering execution provider** once health/status parity and workspace-cleanliness tests pass.

## 5. OpenClaw capability map

Delegate selectively: general tool orchestration, MCP/plugin/skills surfaces, browser/web operations, bounded persistent operational agents, and possible coding fallback under the same workspace/path policy. Evidence: `OpenClawRuntimeAdapter.capabilities()` advertises coding, terminal, file editing, tests, browser, MCP, skills, persistent sessions, isolated workspace, and remote execution; gateway verifies OpenClaw MCP status.

Keep outside OpenClaw: mission state, memory, approvals, Git/GitHub authority, secrets, deployment, unrestricted host shell, and uncontrolled plugin installation.

Role: **optional/selective capability runtime**, not default Core or default repository-coding authority.

## 6. Ruflo capability map

Ruflo has material value today as a diagnostic/benchmark tool only. Evidence: `RufloRuntimeAdapter` advertises MCP/skills/multi-agent/persistent sessions/remote execution but blocks normal execution unless `benchmark_mode` is true, and runs `ruflo doctor --json`. Existing docs/evaluations indicate exploration, not production dependence.

Classification: **benchmark/diagnostic only; disabled by default for production runtime**. Adopt production multi-agent functionality only after measurable benchmark advantage over OpenHands subagents plus MITIGATE routing. Otherwise keep optional or remove.

## 7. Agent Canvas role assessment

Agent Canvas should be a replaceable developer/operator UI and mission submission layer, not an execution layer. Evidence: `mitigate-runtime-overlay.js` injects MITIGATE MCP config into Canvas conversations, requests encrypted settings, and fails open so upstream Canvas is not broken. Deployment assets exist under `agent/deploy/agent-canvas/`.

Target role: UI/operator interface + MCP mission submission. Not Core authority, not direct execution, not persistent mission state owner.

## 8. KEEP/WRAP/REPLACE/DELETE matrix

Tally: **KEEP 13, WRAP 10, REPLACE 11, DELETE 4**.

| # | Subsystem | Class | Replacement/target and rationale | Prerequisite/security/rollback/reduction |
|---:|---|---|---|---|
| 1 | Core authority, policy, approvals | KEEP | Native MITIGATE; business-specific authority | Preserve; rollback N/A |
| 2 | Request API, mission definitions, status | KEEP | Core-owned durable provenance | Backup `/srv/mitigate/data`; no external authority |
| 3 | Mission queue/worker | KEEP | Keep now; shrink if durable orchestration adopted | Tests before replacement; restore queue backup |
| 4 | Runtime adapter contract | KEEP | Provider-neutral boundary enables replaceability | Compatibility tests; adapters can be disabled |
| 5 | Runtime selection/router | KEEP | Routing must be explicit/auditable | Encode full policy; disable provider to rollback |
| 6 | Provider/model/budget ledger | KEEP | Core owns provider choice and cost audit | Protect secrets; revert registry config |
| 7 | Project/business memory | KEEP | MITIGATE-specific durable knowledge | Backup and redaction policy |
| 8 | Core Protection/path approvals | KEEP | High-risk boundary must stay Core-owned | Manual approval for protected paths |
| 9 | Audit/evidence/reporting | KEEP | Governance and forensics | Restore reports; normalize provider metadata |
| 10 | GitHub truth/review/merge authority | KEEP | External runtimes may propose only | Revert branch/commit; merge policy remains |
| 11 | Runtime branch publisher | KEEP | Core-owned commit/push after scope validation | Scope tests; delete branch to rollback |
| 12 | Bootstrap/install portability | KEEP | Fresh-server rebuild is MITIGATE-specific | Restore Git + config/secrets + data backup |
| 13 | Project/domain adapters | KEEP | Business/project specific | Route-specific rollback |
| 14 | OpenHands coding/debug/test/file/shell loop | WRAP | Primary external software runtime | Requires health/status and parity; disable adapter to rollback; high reduction |
| 15 | OpenHands isolated execution | WRAP | Use MITIGATE worktree + OpenHands | Cleanliness tests; fallback legacy/OpenClaw |
| 16 | OpenClaw MCP/tools/plugins | WRAP | Reuse maintained capability infra | Allowlist/sandbox; disable adapter; medium reduction |
| 17 | OpenClaw browser/web | WRAP | Avoid custom browser automation | Network approval/audit; manual fallback |
| 18 | OpenClaw persistent ops agents | WRAP | Low-risk bounded operational tasks only | Core schedule/state; disable route |
| 19 | Ruflo doctor/benchmark | WRAP | Diagnostic and benchmark value | Keep benchmark flag; disable install/adapter |
| 20 | Agent Canvas UI/submission | WRAP | Replaceable UI with Core MCP | Disable overlay; use API/panel |
| 21 | MCP/tool/plugin gateway | WRAP | Core gateway wrapping tools | Auth/tool allowlist; disable tool |
| 22 | External runtime update scripts | WRAP | Candidate-update pipeline, not production promotion | Pin rollback version; approval for breaking changes |
| 23 | Runtime health/diagnostics | WRAP | Unified Core health over all adapters | Add OpenHands status; revert status route |
| 24 | Custom shell execution in legacy runner | REPLACE | OpenHands/OpenClaw terminal in disposable workspace | Parity tests; no secrets/canonical access; high reduction |
| 25 | Custom file/code generation | REPLACE | OpenHands file editor/coding loop | Changed-file evidence; fallback generator until parity |
| 26 | Custom test/debug loop | REPLACE | OpenHands test/debug loop, Core acceptance policy | Test evidence normalization; legacy fallback |
| 27 | Monolithic `mission_runner.py` | REPLACE | Thin controller + router + OpenHands | Representative mission parity; very high reduction |
| 28 | Retry execution loop | REPLACE | Provider handles task iteration; Core keeps retry budget | Retry semantics tests; queue fallback |
| 29 | Self-healing repair generation | REPLACE | Governed OpenHands repair mission | Approval/audit gates; disable self-healing route |
| 30 | Generic browser/tool executor | REPLACE | OpenClaw/future browser runtime | Domain/network audit; manual fallback |
| 31 | Multi-agent/swarm build | REPLACE | Ruflo/OpenHands subagents if benchmarked | Disabled by default; avoid native swarm code |
| 32 | Generic persistent session runtime | REPLACE | External sessions wrapped by Core | Secret/memory isolation; expire sessions |
| 33 | Generic scheduled agent loops | REPLACE | Core schedule + external execution only | Approval policy; disable timer/route |
| 34 | Manual upstream upgrade as primary process | REPLACE | Managed compatibility pipeline using scripts | Candidate env, health, rollback; medium reduction |
| 35 | Gateway OpenHands observability gap | REPLACE | Unified adapter health registry | Status tests; revert if needed |
| 36 | Legacy canonical-checkout execution path | DELETE later | Disposable workspaces only | Full parity; re-enable frozen fallback; high reduction |
| 37 | Direct Canvas execution authority | DELETE/forbid | Canvas submission only, Core executes | UI policy tests; disable overlay |
| 38 | Runtime-specific durable mission state | DELETE/forbid | MITIGATE mission state only | Contract tests; ignore provider state |
| 39 | Old validation V4/ad hoc patch pathway | DELETE/forbid | Consolidation phases only | Architecture approval; no rollback needed |

## 9. Dependency analysis

OpenHands should be a replaceable but preferred dependency for software engineering. OpenClaw should be optional/selective for tools/MCP/browser. Ruflo should be optional diagnostic/benchmark only. Agent Canvas should be replaceable UI. MCP is a Core-owned protocol boundary; individual external MCP tools remain optional. Internal Core dependencies that remain native: provider registry/ledger, memory, policies, audit, request API, queue state, bootstrap, and Git authority.

## 10. Portability analysis

Fresh rebuild target: GitHub checkout + secure configuration/secrets + optional `/srv/mitigate/data` restore.

| Item | GitHub | `/srv/mitigate/data` | Secret | Recreated | Backup |
|---|---:|---:|---:|---:|---:|
| Source, docs, tests, policies, adapters | Yes | No | No | Clone | GitHub |
| Version manifests/examples | Yes | No | No | Clone | GitHub |
| Real tokens/API keys | No | No; use `/etc/mitigate-ai/runtime.env` or secret store | Yes | No | Secret manager |
| Mission queue/definitions | No | Yes | Sensitive operational data | Created by API | Yes |
| Execution reports/checkpoints/audit | No | Yes | May be sensitive | Created during runs | Yes |
| Disposable workspaces | No | Yes temporary | Should not persist secrets | Yes | No |
| External runtime installs | No | `/srv/mitigate/external-runtimes` | No | Bootstrap | Optional cache |
| Project memory | Schema/code in Git | Live memory in data/configured store | Business sensitive | No | Yes |
| Git branches/commits | GitHub | Local clones/worktrees | No | Fetch/clone | GitHub |

External runtime installation requires pinned versions, Python venv, Node/npm prefix, health checks, compatibility tests, and rollback version retention. Bootstrap/systemd docs already place real secrets outside Git and bind runtime API locally by default.

## 11. Explicit runtime selection policy

| Work class | Preferred | Fallback | Capabilities | Approval | Workspace | Audit |
|---|---|---|---|---|---|---|
| Software engineering/bugfix/repo work | OpenHands | OpenClaw, then frozen legacy only by flag | coding, terminal, editing, tests | Core scope + Core Protection | Disposable worktree | provider/model, files, tests, branch/commit |
| MITIGATE Core modification | OpenHands | None automatic | coding/tests/protected path handling | Manual approval, full suite, recovery gate | Disposable worktree | full diff/evidence/rollback |
| General tool orchestration | OpenClaw | Future MCP runtime | MCP/tools/skills | Tool allowlist | Isolated session/workspace | bounded tool transcript |
| Browser/web ops | OpenClaw/future browser runtime | Manual | browser/network controls | Approval for auth/destructive actions | Browser sandbox | domains/actions/screenshots/logs |
| Multi-agent work | Disabled; Ruflo benchmark only | OpenHands subagents if proven | multi-agent/evidence | Architecture approval | Disposable | benchmark/cost/success evidence |
| Maintenance/dependencies | OpenHands + managed update scripts | Manual | coding/tests/health | Approval for breaking/runtime changes | Disposable compatibility workspace | versions, health, rollback |
| Diagnostics | Core read-only + Ruflo/OpenClaw doctor | Manual | read-only status | No approval unless invasive | Usually none | timestamped health/version |
| Scheduled jobs | Core scheduler/queue | Manual | task-specific | policy risk gate | Disposable for repo work | schedule id, mission id, result |
| Git operations | MITIGATE Git layer | Human | git/scope validation | Core owns commit/push; merge policy | Worktree | branch, commit, diff, approval |
| High-risk/prod mutation/deploy | MITIGATE/operator | None automatic | task-specific | Explicit approval | strongest isolation | full transcript and rollback |

## 12. Security/approval boundary design

MITIGATE owns shell grants, Git commit, Git push, merge to main, deployment, production mutation, secrets, destructive operations, external network policy, infrastructure mutation, provider/model choice, persistent memory, and audit. External runtimes execute bounded tasks inside approved workspaces/sessions and return evidence. They do not own canonical main, durable mission state, approvals, secrets, or deployment. Failover must not bypass policy, quota, credential, scope, or approval failures.

## 13. Upstream update strategy

For OpenHands, OpenClaw, Ruflo, Agent Canvas, and MCP dependencies: pin tested versions; monitor latest separately; install candidates in isolated runtime roots; run health checks (`OpenHands adapter health`, `openclaw --version`/MCP status, `ruflo doctor --json`, Canvas UI/MCP smoke, MCP tool schema tests); run compatibility missions; preserve last-known-good versions; rollback by disabling adapter or reinstalling prior pin. Automatic update is permitted only for candidate installation and low-risk promotion after tests. Approval is required for major versions, sandbox/auth/secret/tool/browser changes, production-routing changes, or failed compatibility.

## 14. Migration sequence

1. Phase 0 evidence/policy lock: approve this report; no code deletion. Tests: doc validation/status. Rollback: revert doc. Reduction: 0.
2. Phase 1 observability/routing policy: expose all runtime health including OpenHands and encode work-class routing. Tests: routing/failover/unit. Rollback: disable policy config. Reduction: enabling only.
3. Phase 2 workspace cleanliness/evidence hardening: prove failed/blocked execution leaves canonical checkout clean. Tests: provider fail/block/timeout regression. Rollback: revert hardening. Reduction: 0.
4. Phase 3 OpenHands default: route software work to managed OpenHands by default. Tests: representative docs/backend/tests/dependency/protected-path missions. Rollback: disable OpenHands adapter. Reduction: eventual 1,000-1,400 lines.
5. Phase 4 OpenClaw selective adoption: allowlisted MCP/tool/browser routes. Tests: allowlist denial, sandbox, network audit. Rollback: disable OpenClaw route. Reduction: medium.
6. Phase 5 retry/self-healing shrink: Core keeps budgets/policy; OpenHands performs repair missions. Tests: recovery, block, audit, chain limit. Rollback: disable self-healing route. Reduction: 500-900 lines.
7. Phase 6 Ruflo benchmark decision: run benchmarks only. Tests: doctor, cost/latency/success comparison. Rollback: disable Ruflo. Reduction: avoids native swarm or remove small integration.
8. Phase 7 legacy retirement: delete/shrink proven-dead generic loops. Tests: full suite, bootstrap reinstall, rollback drill. Rollback: revert retirement branch. Reduction: 1,500-2,500+ lines total.

## 15. Rollback strategy

OpenHands: disable adapter or reinstall previous SDK pin; Core state remains. OpenClaw: disable route/gateway tool; Core state remains. Ruflo: keep benchmark flag false or uninstall; no production state loss. Agent Canvas: disable overlay/deployment and use API/panel directly. MCP tools: disable individual tools. Router policy: revert config to last-known-good. Branch publisher: disable publishing and leave changed files for review. Legacy deletion: revert Git branch or restore last-known-good Git revision. All rollbacks depend on keeping MITIGATE mission state, memory, reports, and Git authority outside external runtimes.

## 16. Expected custom-code reduction

Eventual reduction is qualitative high and quantitatively about **1,500-2,500+ lines** after gates pass. Main candidates: legacy mission runner (826), code generator (191), retry engine (446), autonomous controller portions (402), and repair loop/adapter (674). Queue/worker may shrink later but should remain until durable orchestration replacement is proven. Adapter/router/workspace/publisher code is not a reduction target; it is the replaceability boundary.

## 17. Risks and unresolved questions

OpenHands health is not yet visible in gateway status; queue backlog/stale-running diagnosis needs operator-safe tooling; automatic updates must mean candidate testing, not production promotion; OpenClaw plugin/browser surfaces expand attack surface; Ruflo value is unproven; Canvas fail-open behavior must not permit direct execution; provider-specific state must not become durable truth; `/srv/mitigate/data` backup/restore must be tested; historical validation V4 patching must remain frozen.

## 18. Final recommended target architecture

```text
User / Panel / Canvas
        ↓
MITIGATE Core
        ↓
Governance / Memory / Policies / Mission State
        ↓
Runtime Selection
        ↓
Replaceable Runtime Adapters
        ↓
OpenHands / OpenClaw / optional Ruflo / future runtimes
        ↓
Disposable Workspaces / Tools
        ↓
MITIGATE Review / Git / Audit / Deployment Authority
```

Invariants: MITIGATE remains usable without any single external runtime; runtimes are dependencies behind adapters, not forks; provider choice is auditable; repo work uses disposable workspaces; GitHub remains canonical; clean-repo, validation, audit, and rollback controls are preserved.

## 19. Go / No-Go recommendation for beginning phased migration

**GO** for phases 1-2. **NO-GO** for deletion, production dependency changes, or weakening controls until OpenHands status parity, workspace-cleanliness regression, provider evidence persistence, OpenClaw sandbox/allowlist, Ruflo benchmark decision, update rollback, and fresh-server restore gates pass.

## Final mission evidence fields

- REQUEST_ID: active workspace request `canvas-20260814T120751Z-d0cc16`; nested submitted request `canvas-20260814T122056Z-23fb0a` was pending at last observation.
- MISSION_ID: active workspace mission `m1786709271048027`; nested submitted mission `m1786710056746186`.
- EXECUTION_PROVIDER: OpenHands in a MITIGATE-managed disposable workspace.
- ASSESSMENT_FILE: `docs/architecture/runtime-consolidation-assessment.md`.
- CURRENT_ARCHITECTURE_SUMMARY: MITIGATE Core already owns request API, queue, router, adapters, workspaces, branch publishing, memory, policy, provider abstraction, audit, bootstrap, Canvas MCP integration, and upstream metadata; consolidation is partial because legacy generic execution/retry/self-healing loops remain.
- KEEP_COUNT: 13.
- WRAP_COUNT: 10.
- REPLACE_COUNT: 11.
- DELETE_COUNT: 4.
- OPENHANDS_ROLE: primary software-engineering executor; not authority for policy, memory, Git, approvals, secrets, or deployment.
- OPENCLAW_ROLE: optional/selective capability runtime for tools/MCP/plugins/browser and bounded ops; possible coding fallback only under Core controls.
- RUFLO_ROLE: optional benchmark/doctor/diagnostic runtime, disabled by default for production execution.
- CANVAS_ROLE: replaceable developer/operator UI and mission submission layer via MITIGATE MCP; not execution authority.
- TARGET_ARCHITECTURE: User/Panel/Canvas -> MITIGATE Core -> Governance/Memory/Policies/Mission State -> Runtime Selection -> Replaceable Runtime Adapters -> OpenHands/OpenClaw/optional Ruflo/future runtimes -> Disposable Workspaces/Tools -> MITIGATE Review/Git/Audit/Deployment Authority.
- EXPECTED_CUSTOM_CODE_REDUCTION: roughly 1,500-2,500+ lines after parity and rollback gates.
- MIGRATION_PHASES: 0 evidence/policy lock; 1 observability/routing; 2 cleanliness/evidence; 3 OpenHands default; 4 OpenClaw selective; 5 retry/self-healing shrink; 6 Ruflo benchmark; 7 legacy retirement.
- ROLLBACK_READY: mostly yes architecturally; final readiness needs explicit route flags and OpenHands status parity.
- GITHUB_BRANCH: to be supplied by MITIGATE branch publisher if Core publishes this artifact; no manual branch was created by the external runtime.
- COMMIT: to be supplied by MITIGATE branch publisher if Core commits this artifact; no manual commit was made by the external runtime.
- REQUEST_STATUS: active mission in progress while artifact written; nested submitted mission pending at last observed status.
- GO_NO_GO: GO for phases 1-2 only; NO-GO for deletion/production dependency changes until gates pass.
- RESULT: assessment artifact created; no implementation migration performed.
