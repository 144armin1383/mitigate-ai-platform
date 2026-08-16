# Lovable-Style Builders Pattern Review

Status: assessment only  
Scope: architecture patterns potentially useful to MITIGATE's Project Adapter contract  
Constraint: no implementation changes, no external code import/copy, no Core or adapter modifications

## Purpose

This review examines several open-source Lovable-style app/web builders for architectural patterns that may be useful to MITIGATE. The products themselves primarily solve a different problem — creating new applications — while MITIGATE's target is long-running management of existing live sites and Git-backed projects.

The review therefore focuses only on four possible capability contracts that could extend the existing Project Adapter contract in `docs/architecture/ARCHITECTURE_V2.md`:

1. `PreviewSession` — `start_preview()`, `get_preview_url()`, `health()`, `stop_preview()`.
2. `SandboxProvider` — a pluggable sandbox backend independent of Project Adapters and execution-engine adapters.
3. `GitSyncProvider` — explicit `fetch`, `sync`, `publish`, `compare`, and `reconcile` operations.
4. `ProjectSessionState` — durable project/session metadata that survives disposable executors.

Decision vocabulary:

- **ADOPT PATTERN** — the pattern is directly useful and aligns with MITIGATE's existing architecture.
- **DEFER** — useful ideas exist, but the pattern is incomplete, too product-specific, or not urgent enough to formalize yet.
- **REJECT** — the observed implementation shape is a poor fit for MITIGATE's stated durability/governance goals.

## Executive recommendation

MITIGATE should not import any of these builders or adopt their product scope. The strongest reusable architectural ideas are:

- **Adopt `PreviewSession` as an explicit Project Adapter capability.** Adorable, Claudable, Open Lovable, and Dyad all treat preview lifecycle as a first-class concern rather than incidental process output.
- **Adopt a separate `SandboxProvider` contract.** Open Lovable's provider selection between Vercel Sandbox and E2B is the clearest evidence that sandbox choice should be independent of the project type and the coding-agent/runtime choice.
- **Adopt a narrow `GitSyncProvider` contract, but keep MITIGATE governance authoritative.** Adorable's Git-backed projects and bidirectional GitHub sync, Claudable's repository metadata/commit model, and Dyad's host capability design all support separating Git transport/mechanics from policy and approval.
- **Adopt durable `ProjectSessionState`, but do not copy in-memory session patterns.** Claudable's persisted project/session/commit metadata is the best concrete reference. Open Lovable's global in-memory conversation state is specifically an anti-pattern for MITIGATE's durability requirements.

The four contracts should remain MITIGATE-owned interfaces. External sandbox, preview, Git, or session implementations must stay replaceable and must not become governance authorities.

## Decision matrix

| Project | PreviewSession | SandboxProvider | GitSyncProvider | ProjectSessionState |
|---|---|---|---|---|
| `freestyle-sh/Adorable` | **ADOPT PATTERN** | **DEFER** | **ADOPT PATTERN** | **ADOPT PATTERN** |
| `firecrawl/open-lovable` | **ADOPT PATTERN** | **ADOPT PATTERN** | **DEFER** | **REJECT** |
| `aniketdandagavhan/OpenLovable` | **DEFER** | **DEFER** | **DEFER** | **DEFER** |
| `opactorai/Claudable` | **ADOPT PATTERN** | **DEFER** | **ADOPT PATTERN** | **ADOPT PATTERN** |
| `codinit-dev/codinit-dev` | **ADOPT PATTERN** | **DEFER** | **DEFER** | **DEFER** |
| `dyad-sh/dyad` | **ADOPT PATTERN** | **ADOPT PATTERN** | **ADOPT PATTERN** | **ADOPT PATTERN** |

## 1. `freestyle-sh/Adorable`

### Evidence reviewed

- Repository README.
- `adorable/lib/adorable-vm.ts`.

The README describes conversational building inside a sandboxed VM, live preview and terminal, persistent Git-backed projects, and bidirectional GitHub sync. The VM implementation returns explicit runtime metadata containing a VM ID, preview URL, and terminal URLs. It creates a VM with sticky persistence, mounts a Git repository at the work directory, starts a development server, and exposes preview/terminal domains.

### PreviewSession — ADOPT PATTERN

This is the clearest useful pattern in Adorable. Preview is represented as explicit runtime metadata instead of being inferred from arbitrary executor output. MITIGATE should similarly treat preview lifecycle as a capability with its own identifier, URL, health state, and teardown operation.

MITIGATE-specific adaptation: a preview must be linked to `project_id`, `mission_id`/`execution_id`, workspace revision, and expiry policy. Preview authority remains with MITIGATE; the underlying Project Adapter decides how a preview is produced (dev server, staging slot, WordPress staging URL, container, etc.).

### SandboxProvider — DEFER

Adorable demonstrates strong VM isolation, but the inspected implementation is tightly coupled to Freestyle VM primitives. The isolation ideas are useful, but Open Lovable and Dyad provide stronger evidence for a provider-neutral abstraction.

### GitSyncProvider — ADOPT PATTERN

Adorable explicitly treats Git-backed persistence and bidirectional GitHub sync as product capabilities. This supports formalizing Git synchronization as a separate interface instead of allowing fetch/push/reconciliation behavior to be scattered across adapters.

MITIGATE must not adopt Adorable's authority model wholesale: sync mechanics may be providerized, but merge, approval, protected-path checks, and source-of-truth rules remain MITIGATE governance concerns.

### ProjectSessionState — ADOPT PATTERN

Adorable preserves project conversations/history across sessions while using an isolated VM execution model. The useful pattern is the separation between project continuity and executor lifetime. MITIGATE should preserve durable session/project metadata even if the executor/workspace is disposable.

## 2. `firecrawl/open-lovable`

### Evidence reviewed

- Repository README and environment configuration.
- Repository tree under `app/api/*`.
- `app/api/conversation-state/route.ts`.
- Sandbox dependencies include both `@vercel/sandbox` and `@e2b/code-interpreter`.

The README exposes a `SANDBOX_PROVIDER` setting with Vercel Sandbox as default and E2B as an alternative. The repository contains separate sandbox lifecycle routes including creation, file access, package installation, Vite monitoring, and sandbox termination.

### PreviewSession — ADOPT PATTERN

Open Lovable's sandbox lifecycle and Vite monitoring demonstrate that preview should be managed as a bounded runtime lifecycle, not merely a URL displayed in UI. MITIGATE should adopt the lifecycle concept while keeping preview implementation Project Adapter-specific.

### SandboxProvider — ADOPT PATTERN

This is Open Lovable's strongest architectural contribution for MITIGATE. Provider choice is explicitly configurable between different sandbox backends. That matches the proposed separation:

`Project Adapter` != `Execution Engine Adapter` != `SandboxProvider`.

MITIGATE could then support local Git worktree, container, VM, E2B, or other backends without changing project-type logic or agent routing.

### GitSyncProvider — DEFER

The reviewed project does not make Git reconciliation a first-class architectural boundary comparable to its sandbox provider abstraction. No sufficiently strong evidence was found to treat its Git mechanics as a reference design.

### ProjectSessionState — REJECT

The inspected conversation state endpoint stores state in a process-global variable. It retains messages, edits, project evolution, and preferences only in memory and can be cleared/reset through the endpoint. This directly conflicts with MITIGATE's requirement that canonical project/session knowledge survive process restarts.

Useful lesson: the shape of the state is relevant; the storage strategy is not. MITIGATE should explicitly avoid global/in-memory-only canonical session state.

## 3. `aniketdandagavhan/OpenLovable`

### Evidence reviewed

The exact repository named in the review request could not be reliably resolved through the available GitHub/web search paths at review time. No authoritative repository README or source tree could be verified for this exact owner/repository pair.

### PreviewSession — DEFER
### SandboxProvider — DEFER
### GitSyncProvider — DEFER
### ProjectSessionState — DEFER

No architecture decision should be based on an unverified or possibly renamed/deleted repository. This project should be re-evaluated only when an exact accessible repository URL or commit is available.

This is intentionally not a negative technical judgment; it is an evidence-quality decision.

## 4. `opactorai/Claudable`

### Evidence reviewed

- Repository README.
- `prisma/schema.prisma`.

The README describes local CLI-agent execution (Claude Code, Codex CLI, Cursor CLI, Qwen Code and others), instant preview with hot reload, GitHub integration, and Vercel deployment. The Prisma schema uses SQLite and stores durable `Project`, `Session`, `Message`, `Commit`, `UserRequest`, and service-connection records. Project state includes preview metadata, repository path, active CLI session IDs, preferred CLI/model, timestamps, and service connection metadata including GitHub repository/default-branch data and last-sync time.

### PreviewSession — ADOPT PATTERN

Claudable persists preview metadata (`previewUrl`, `previewPort`) at the project layer while the execution agent remains replaceable. MITIGATE should adopt the same architectural separation, although preview state should be modeled more explicitly than legacy URL/port fields.

### SandboxProvider — DEFER

Claudable's public design emphasizes local CLI agents and explicitly markets minimal sandbox setup. It is a strong reference for executor interchangeability, but not the strongest reference for a pluggable sandbox-provider contract.

### GitSyncProvider — ADOPT PATTERN

Claudable persists repository/service connection metadata, commit records, and last-sync timestamps separately from individual agent sessions. That separation is relevant to MITIGATE's proposed `GitSyncProvider` boundary.

Again, MITIGATE should only providerize Git mechanics. Approval, risk policy, protected paths, review, and merge authority must stay in MITIGATE Core.

### ProjectSessionState — ADOPT PATTERN

This is Claudable's strongest contribution. The SQLite schema demonstrates durable separation between project identity, executor session identity, messages, commit history, user requests, preview metadata, and external service connections. That maps closely to the proposed MITIGATE contract.

MITIGATE should not copy the schema directly. The reusable idea is: durable MITIGATE-owned project/session state references disposable provider sessions rather than making provider session state canonical.

## 5. `codinit-dev/codinit-dev` (CodinIT.dev)

### Evidence reviewed

- Repository README.
- Public project documentation describing local Node.js execution versus browser-sandbox alternatives.

CodinIT.dev presents itself as a local-first web/mobile AI app builder with desktop and browser modes, multiple AI providers, Docker workflows, diff visualization, concurrency file locking, deployment presets, and vendor-neutral provider switching. Its documentation emphasizes local Node.js execution for native-module compatibility.

### PreviewSession — ADOPT PATTERN

CodinIT includes a development/preview workflow as an explicit product surface. The reusable MITIGATE lesson is that preview should be a host/project capability rather than something owned by a particular coding model.

### SandboxProvider — DEFER

CodinIT is useful as a contrast: local execution can be a legitimate backend alongside stronger isolation. MITIGATE should support a local-worktree/local-process provider where policy allows it, but CodinIT itself does not provide as strong a reference architecture for pluggable sandbox backends as Open Lovable or Dyad.

### GitSyncProvider — DEFER

The project advertises Git/GitHub-related capabilities and diff tooling, but the reviewed material did not expose a sufficiently clear provider-style Git contract to use as a direct architectural reference.

### ProjectSessionState — DEFER

The local-first architecture and project-management features suggest persisted state is important, but the reviewed evidence was not as explicit or mature as Claudable's persisted project/session schema or Dyad's host/session contract. Revisit only if MITIGATE needs a second concrete persistence reference.

## 6. `dyad-sh/dyad`

### Evidence reviewed

- Repository README.
- `docs/adrs/0001-host-capability-interface.md`.
- `src/version_preview/*` and related preview-state planning artifacts discovered in the tree.

Dyad is particularly relevant because its current architecture work explicitly identifies coupling between product logic and desktop/Electron execution primitives, then proposes a canonical `HostProvider` capability interface. The ADR groups capabilities under `project`, `exec`, `git`, `preview`, `integration`, `system`, and `session`. Operations carry `workspaceId`, `projectId`, `requestId`, idempotency key, actor, and timestamp; responses use typed errors and correlation IDs. It also defines transport-neutral stream events and runtime capability negotiation.

### PreviewSession — ADOPT PATTERN

Dyad's proposed `preview` capability group (`start`, `stop`, `status`, `getPreviewUrl`) is nearly the same shape as the proposed MITIGATE `PreviewSession` contract. This is strong independent validation of the interface direction.

MITIGATE should add health/verification and bind preview to an immutable revision/workspace identity.

### SandboxProvider — ADOPT PATTERN

Dyad's broader `HostProvider` concept validates separating privileged execution capabilities from transport and UI. MITIGATE should not copy Dyad's entire host abstraction, but the provider boundary strongly supports a dedicated `SandboxProvider` that can be local, containerized, VM-based, or remote.

### GitSyncProvider — ADOPT PATTERN

Dyad explicitly defines a `git` capability group containing branch/commit/status/sync operations behind the host boundary. This supports the proposed MITIGATE `GitSyncProvider` as a mechanical interface.

MITIGATE should go further by splitting policy-free Git transport/synchronization from MITIGATE-owned review/approval/merge governance.

### ProjectSessionState — ADOPT PATTERN

Dyad's ADR explicitly includes `session` state controls and standardized request/workspace/project identifiers, idempotency, actor identity, timestamps, typed errors, and correlation IDs. This maps well to MITIGATE's need for durable continuity across disposable executors.

MITIGATE's canonical implementation should remain Git/file-backed and portable as required by `ARCHITECTURE_V2.md`; provider-side caches are optional accelerators only.

## Cross-project conclusions

### A. Preview should become a first-class optional Project Adapter capability

Recommended conceptual contract:

```text
PreviewSession
- start_preview(project, revision, workspace, policy) -> preview_id
- get_preview_url(preview_id) -> url
- health(preview_id) -> typed health result
- stop_preview(preview_id) -> result
```

Important MITIGATE constraints:

- preview is always project- and revision-scoped;
- preview cannot imply production deployment;
- preview lifecycle must be auditable;
- credentials/secrets remain policy-controlled;
- a preview provider cannot bypass Project Adapter validation or deployment gates.

Decision: **ADOPT PATTERN**.

### B. Sandbox should be a separate provider boundary

Recommended conceptual separation:

```text
MITIGATE Core
  -> Project Adapter
  -> Execution Engine Adapter
  -> SandboxProvider
```

These answer different questions:

- Project Adapter: how this project type is inspected, tested, deployed, verified, and rolled back.
- Execution Engine Adapter: which coding/agent executor performs bounded work.
- SandboxProvider: where isolated commands/files/processes run.

Possible backends may include local disposable Git worktrees, containers, VMs, E2B, Vercel Sandbox, or future providers. Capability negotiation should be explicit rather than assumed.

Decision: **ADOPT PATTERN**, with implementation deferred to a separately approved mission.

### C. Git mechanics should be providerized; Git governance should not

Recommended conceptual interface:

```text
GitSyncProvider
- fetch()
- compare()
- sync()
- publish()
- reconcile()
```

The provider must not own:

- approval decisions;
- protected-path policy;
- risk classification;
- merge authority;
- source-of-truth policy;
- rollback acceptance criteria.

Those remain MITIGATE Core responsibilities.

Decision: **ADOPT PATTERN**.

### D. Project/session continuity must outlive executors

Recommended conceptual state includes:

- current/last known branch and revision;
- preview ID, provider, status, URL metadata, and expiry;
- pending user intent and unresolved clarification;
- latest diagnostics and validation references;
- current execution/session references per provider;
- Git sync state and last reconciliation;
- last successful deployment/health result;
- correlation IDs linking request, mission, execution, preview, deployment, and approval records.

Canonical state must be durable and MITIGATE-owned. An executor session ID is a reference, not the source of truth.

Decision: **ADOPT PATTERN**.

## Relationship to `ARCHITECTURE_V2.md`

These proposed contracts are extensions of the existing Project Adapter architecture, not replacements for it.

`ARCHITECTURE_V2.md` already requires adapters to inspect projects/runtimes, collect diagnostics, modify within policy, run project-specific tests, deploy, verify health, roll back, and expose project-specific operational actions. The four reviewed contracts make several cross-cutting mechanics explicit so they do not leak into stack-specific adapters or external execution engines.

A possible future architecture, subject to separate approval, is:

```text
MITIGATE Core / Policy / Mission Lifecycle
        |
        +-- ProjectAdapter
        |     inspect / validate / deploy / health / rollback
        |
        +-- PreviewSession capability
        |
        +-- GitSyncProvider
        |
        +-- SandboxProvider
        |
        +-- Execution Engine Adapters
        |     OpenHands / OpenClaw / future providers
        |
        +-- Durable ProjectSessionState
```

No implementation change is authorized by this document.

## Recommended follow-up sequence

Assessment-only recommendation; each item requires a separate explicitly approved implementation mission.

1. Define interfaces/schemas only for the four contracts, with no provider implementations.
2. Map current MITIGATE runtime/workspace/Git/session behavior against those contracts to avoid duplicating existing functionality.
3. Implement `ProjectSessionState` on the durable memory foundation first, because preview/sandbox/Git providers need stable canonical state references.
4. Add `PreviewSession` as an optional Project Adapter capability.
5. Extract a `GitSyncProvider` mechanical boundary while preserving current Git governance unchanged.
6. Extract `SandboxProvider` only after current disposable-workspace behavior has contract/parity tests, so isolation is not weakened during refactoring.

## Final assessment

The external builders validate MITIGATE's existing architectural direction more than they suggest a product change.

The most important reusable lesson is **separation of concerns**:

- project-specific operations should remain in Project Adapters;
- agent execution should remain behind execution adapters;
- sandbox location/lifecycle should become separately pluggable;
- preview should be a first-class lifecycle capability;
- Git synchronization mechanics should be explicit but policy-free;
- durable MITIGATE-owned project/session state should outlive all disposable executors.

No reviewed project should be imported wholesale. No external implementation should become the canonical owner of MITIGATE policy, memory, Git governance, deployment authority, or project continuity.
