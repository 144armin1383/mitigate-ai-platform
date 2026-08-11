# Ruflo Integration Contract

## Principle

MITIGATE AI owns the product architecture, control plane, policy engine, mission lifecycle, project model, durable memory, deployment authority, and audit trail. Ruflo is optional infrastructure behind a replaceable adapter.

## What MITIGATE may use Ruflo for

Subject to compatibility tests and policy controls, the Ruflo adapter may expose:

- multi-agent/swarm orchestration;
- developer/reviewer/test/security agent coordination;
- task decomposition and parallel execution;
- semantic/RAG retrieval and memory acceleration;
- learned patterns and task assistance;
- observability/tracing helpers;
- browser or testing helpers;
- other capabilities explicitly adopted through this contract.

## What Ruflo must not own

Ruflo must not be the sole source of truth for:

- project definitions;
- requests, plans, missions, or approvals;
- risk policy;
- Git/deployment authority;
- durable project memory;
- secrets or credentials;
- production audit records;
- recovery/bootstrap instructions;
- provider selection.

## Adapter boundary

MITIGATE must call Ruflo through a MITIGATE-owned interface rather than scattering Ruflo-specific commands, schemas, paths, or assumptions throughout the core.

The adapter should normalize at least:

- capability discovery;
- agent/swarm creation;
- task submission;
- task status;
- cancellation/timeouts;
- result collection;
- structured errors;
- trace/correlation identifiers;
- memory retrieval/write operations when enabled;
- health/version information.

The rest of MITIGATE should consume normalized MITIGATE types.

## Capability negotiation

The adapter must detect the installed Ruflo version and supported capabilities at startup. Optional features must be feature-gated. A missing or changed Ruflo capability must produce a controlled degraded state rather than crashing the MITIGATE runtime.

## Native fallback

Critical MITIGATE operations must retain a native execution path where practical. Ruflo failure must not corrupt mission state, Git state, portable memory, or deployment state.

If a Ruflo-backed mission cannot continue safely, MITIGATE should either:

1. fall back to a compatible native agent path; or
2. stop safely with a clear retryable/non-retryable reason.

## Data ownership

Any knowledge generated through Ruflo that is required for future continuity must be promoted into MITIGATE durable memory. Ruflo/AgentDB/vector state may be rebuilt from MITIGATE-owned durable sources where feasible.

## Security boundary

Ruflo does not independently receive unrestricted production credentials. MITIGATE policy decides which scoped capabilities/tools are exposed to an agent execution. High-risk actions continue through MITIGATE approval controls.

## Fork policy

Do not copy or permanently vendor the complete Ruflo codebase into MITIGATE by default.

A MITIGATE-maintained Ruflo fork is permitted only when an essential production requirement cannot be met through the public/stable integration surface and waiting for upstream is unacceptable. Any fork must:

- preserve upstream Git history;
- contain the smallest practical patch set;
- document why each patch exists;
- track the upstream commit/release it is based on;
- have tests covering the patch;
- periodically test whether the patch can be removed after upstream changes.

MITIGATE-owned functionality should live in MITIGATE whenever it can be implemented cleanly outside Ruflo.

## Exit strategy

Replacing Ruflo must require changing the adapter/provider implementation, not rewriting the control plane. Durable state must remain available and another orchestration provider or the native engine must be able to assume future missions.
