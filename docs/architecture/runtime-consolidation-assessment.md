# MITIGATE AI Runtime Consolidation Assessment

Status: active integration work
Branch: `integration/runtime-consolidation`

## Objective

Reduce custom runtime code and maintenance burden while preserving MITIGATE AI as the independent control plane and source of authority.

MITIGATE must remain portable, provider-agnostic, replaceable at the execution layer, and able to continue operating if any external runtime is removed.

## Non-negotiable architecture rules

1. MITIGATE owns policy, approvals, mission intent, project memory, audit evidence, business/project knowledge and GitHub source-of-truth.
2. External agent runtimes are capability providers only.
3. Every external runtime is accessed through a MITIGATE-owned adapter contract.
4. No external runtime may become the only location of mission state, project memory or governance rules.
5. Upstream projects are consumed as versioned dependencies; avoid forks and internal-source imports unless no stable public surface exists.
6. Every adopted dependency must have a tested update path and rollback path.
7. New generic infrastructure must pass a Build-vs-Adopt gate before being implemented inside MITIGATE.
8. High-risk production actions remain governed by MITIGATE approval and Core Protection.
9. GitHub remains canonical; execution workspaces are disposable.
10. Failed attempts must not contaminate the canonical repository or the next attempt.

## Target architecture

```text
User / API / Scheduler
        |
        v
MITIGATE Control Plane
- mission intent
- policy / approvals
- project memory
- audit / evidence
- routing
- GitHub truth
        |
        v
MITIGATE Runtime Adapter Contract
        |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
   OpenHands            OpenClaw             Ruflo
 coding/execution       tools/skills        swarm/orchestration
 sandbox/workspace      sessions/MCP        memory/coordination
 tests/refactors        integrations         optional benchmarked use
        |
        v
Disposable execution workspace / worktree / sandbox
        |
        v
Git branch -> validation -> MITIGATE review/approval -> merge/deploy
```

## Current MITIGATE inventory: initial classification

| Current capability | Classification | Direction |
|---|---|---|
| Mission intent/schema | KEEP | MITIGATE authority |
| Core Protection | KEEP | MITIGATE authority |
| Approval policy | KEEP | MITIGATE authority |
| Project memory and machine-readable handoff | KEEP | MITIGATE authority |
| GitHub canonical history | KEEP | MITIGATE authority |
| WordPress/Lovable/project adapters | KEEP | MITIGATE-specific |
| Audit/evidence requirements | KEEP | Normalize external runtime results into MITIGATE evidence |
| `MissionQueue` | KEEP TEMPORARILY | Do not expand; reassess after external durable execution is proven |
| `ProductionMissionController` | WRAP/SHRINK | Reduce to routing/status normalization after adapter migration |
| monolithic `mission_runner.py` generation/execution loop | REPLACE/SHRINK | Move generic coding/execution to OpenHands adapter |
| custom code generation loop | REPLACE | OpenHands first |
| custom shell/file editing execution | REPLACE | Sandboxed external executor |
| custom validation retry feedback loop | WRAP/REPLACE | External executor performs task loop; MITIGATE retains acceptance policy |
| custom self-healing implementation | SHRINK | Keep policy/evidence rules; delegate implementation repair loop |
| branch/worktree mechanics | WRAP | Prefer executor workspace isolation plus MITIGATE Git gate |
| generic agent skills/tool runtime | REPLACE/WRAP | OpenClaw capability surface where useful |
| multi-agent swarm implementation | DO NOT BUILD | Benchmark Ruflo/OpenHands subagents first |
| generic persistent session runtime | REPLACE/WRAP | OpenClaw/OpenHands capability depending use case |
| generic scheduler/background agent loops | WRAP | Reuse maintained upstream mechanism where safe; MITIGATE retains schedule intent |
| model/provider abstraction | WRAP | External providers may execute; MITIGATE keeps routing policy and portability |

This table is intentionally conservative. No current production component is deleted until replacement compatibility tests pass.

## OpenHands role

Preferred first execution provider for software-engineering work.

Adopt for:

- terminal execution
- file editing
- repository-aware coding
- refactoring
- test execution
- dependency maintenance
- isolated/ephemeral workspaces
- remote Agent Server execution
- multi-step coding conversations
- optional sub-agent workflows

MITIGATE remains responsible for:

- deciding what task is authorized
- allowed repository/project scope
- acceptance criteria
- risk classification
- final Git review and approval
- production deployment authority
- persistent project knowledge

### Integration strategy

Use the public OpenHands Software Agent SDK / Agent Server interfaces. Do not vendor OpenHands core logic into MITIGATE.

Initial mode: adapter + disposable coding workspace. The adapter returns a normalized `ExecutionResult` containing status, changed files, diagnostics, test evidence and external runtime metadata.

## OpenClaw role

Use selectively as an extensible agent capability layer, especially where its maintained surfaces save custom code.

Candidate capabilities:

- skills
- typed tools
- plugin bundles
- MCP server/client integration
- isolated agent/session workspaces
- cron/background capabilities
- browser/integration tools
- channel integrations when needed later

Security rule: do not use unsandboxed host execution as the default production execution path. Plugin code is trusted code and must be explicitly allowlisted.

Integration preference: stable skills/MCP/plugin bundle surfaces over imports from OpenClaw internals.

## Ruflo role

Ruflo is optional and benchmark-gated.

Candidate capabilities:

- multi-agent orchestration
- swarm topologies
- specialized agents
- shared memory/coordination
- background workers
- MCP surface
- cost/observability plugins

Do not make MITIGATE dependent on Ruflo-specific mission state or Claude-only concepts.

Adoption condition: it must demonstrate measurable value over OpenHands subagents + MITIGATE routing on representative MITIGATE workloads.

## Build-vs-Adopt gate

Before adding a new generic runtime component, answer:

1. Does OpenHands already provide it?
2. Does OpenClaw provide a stable skills/tools/plugin/MCP surface for it?
3. Does Ruflo provide it with measurable operational advantage?
4. Is another mature, replaceable open-source component materially better?
5. Is the feature MITIGATE-specific enough that native implementation is justified?

Preferred order:

`ADOPT -> WRAP -> EXTEND -> BUILD`

## Dependency and update policy

For each external runtime:

- pin a tested version/commit in MITIGATE compatibility metadata;
- record upstream repository and license;
- monitor releases separately from production rollout;
- run compatibility tests in disposable workspace first;
- update adapter compatibility if needed;
- promote only a tested version;
- preserve the last-known-good version for immediate rollback;
- never let automatic dependency updates bypass MITIGATE approval for breaking/runtime-sensitive changes.

## Isolation model

Execution work must not occur directly in the canonical checkout by default.

Preferred sequence:

1. Canonical `main` remains clean.
2. Create disposable worktree/workspace/sandbox from known Git SHA.
3. External executor works only inside that workspace.
4. Tests and validation run there.
5. Produce structured evidence.
6. Commit to an isolated branch only after acceptance gates pass.
7. MITIGATE reviews branch diff/risk.
8. Merge/deploy according to MITIGATE policy.
9. Destroy disposable workspace.

This directly prevents failed-attempt artifacts from poisoning subsequent retries.

## Phase plan

### Phase 1 — Adapter foundation (NOW)

- define MITIGATE runtime adapter contract;
- implement normalized execution request/result models;
- add provider registry with no external hard dependency;
- add capability metadata and health checks;
- preserve current runtime unchanged.

### Phase 2 — OpenHands executor

- implement OpenHands adapter behind optional dependency;
- local/disposable workspace first;
- validate coding, tests, changed-file reporting and timeout/cancellation;
- benchmark against current mission runner on representative tasks.

### Phase 3 — OpenClaw capability adapter

- integrate only selected stable capability surfaces;
- skills/MCP/plugin bundle preference;
- sandbox and allowlist policy required;
- no Core authority delegated.

### Phase 4 — Ruflo benchmark

- run representative multi-agent tasks;
- measure latency, task success, recovery, cost and code-change quality;
- adopt only the capabilities that outperform simpler architecture.

### Phase 5 — Consolidation

- route new coding missions through OpenHands by default;
- shrink the custom mission runner;
- remove redundant runtime code only after parity tests;
- keep compatibility fallback until migration is proven.

### Phase 6 — Upstream manager / self-upgrade

- track approved upstream versions;
- detect new releases;
- create isolated compatibility test runs;
- generate upgrade evidence;
- low-risk approved upgrades can become autonomous according to policy;
- breaking/security-sensitive upgrades require approval.

## Immediate acceptance criteria

The consolidation is successful only if:

- MITIGATE remains independently usable and portable;
- no external provider owns canonical project state;
- OpenHands can be removed/replaced by implementing the same adapter contract;
- OpenClaw can be disabled without breaking MITIGATE core;
- Ruflo is optional;
- external runtime updates remain available;
- custom runtime code decreases rather than increases;
- failed executions cannot dirty the canonical checkout;
- Core Protection and approvals remain authoritative;
- GitHub remains the canonical source of truth.

## Freeze note

The failed validation-evidence V3 path is not to be expanded with additional ad-hoc runtime patches during this assessment. Its failure exposed a generic execution-workspace contamination problem that this consolidation is intended to remove structurally rather than grow more custom recovery code around.
