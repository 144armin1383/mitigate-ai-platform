# MITIGATE AI Platform — Architecture v2

## Mission

MITIGATE AI is the primary product and control plane. It is an autonomous technical management and development platform that can attach to WordPress, WooCommerce, React, Next.js, PHP, Python, and other Git-backed or remotely manageable applications without becoming coupled to any one application stack.

The platform must provide an independent management panel outside the managed site. A managed site's failure must not take down the MITIGATE AI control plane.

## Core product capabilities

MITIGATE AI must support:

- natural-language technical requests and end-to-end execution;
- diagnosis, planning, implementation, validation, review, deployment, verification, rollback, and reporting;
- autonomous low-risk maintenance and human approval for high-risk or irreversible work;
- multi-agent development, review, QA, security, SEO, content, and DevOps workflows;
- persistent portable project memory shared across AI providers and agents;
- proactive health, bug, dependency, performance, security, SEO, and operational scanning;
- continuous self-maintenance and controlled self-upgrade;
- provider-agnostic AI integration;
- reusable project adapters rather than WordPress-specific core logic;
- GitHub as the portable source of truth for code, policies, schemas, tests, bootstrap assets, mission knowledge, and durable memory.

## Architectural layers

1. **Independent Control Plane** — projects, users, requests, missions, approvals, reports, observability, configuration, and management UI.
2. **MITIGATE Runtime** — request planning, mission queue, execution reporting, policy enforcement, risk classification, lifecycle state, and recovery.
3. **Agent Orchestration** — native MITIGATE agents plus optional external orchestration engines behind adapters.
4. **Project Adapters** — WordPress/WooCommerce, React/Next.js, generic Git projects, and future stacks.
5. **Execution & Deployment** — isolated branches/worktrees, tests, review, deployment, health verification, rollback.
6. **Memory** — canonical portable memory in Git plus optional semantic indexes/caches that can always be rebuilt.
7. **Observability** — request_id, plan_id, mission_id, agent_id, execution_id, deployment_id, structured logs, metrics, traces, and audit history.

## Multi-agent operating model

A lead technical-manager agent may delegate to specialized agents such as developer, reviewer, QA, security, SEO, content, and DevOps agents. Important changes should support independent implementation and review rather than allowing the same agent to be the sole author and approver.

Agent consensus is advisory to MITIGATE policy. The MITIGATE policy/risk layer remains authoritative for merge, deployment, rollback, and approval decisions.

## Project adapter contract

The core must not encode WordPress assumptions. Each adapter should expose capabilities such as:

- inspect project and runtime;
- collect logs and diagnostics;
- modify code/content/configuration within policy;
- run project-specific validation and tests;
- deploy;
- verify health;
- rollback;
- expose project-specific operational actions.

### Project-aware mission scope derivation

Before an external execution runtime starts, MITIGATE derives the minimum repository write scope from the mission task type, project metadata, requested objective, and explicit deliverables. The derived scope is a Core-owned policy boundary; execution providers consume it but may not broaden it.

For ordinary managed-project work, known project-owned repository areas should be authorized automatically so routine requests do not require repeated path-by-path approval. For example, a WordPress/WooCommerce feature may receive repository scope for the repository-managed `wordpress/` source tree and related documentation even when the planner classifies the overall request as `deployment`.

Automatic scope derivation does **not** authorize live-host mutations. Secrets, MITIGATE policy, global Nginx/systemd configuration, firewall/security configuration, privilege changes, WordPress core, unrelated projects, and other trust-boundary changes remain protected by their existing deployment and approval controls.

Scope derivation follows these rules:

- explicit safe deliverables remain useful scope hints but do not override protected boundaries;
- project metadata and objective intent can correct an overly broad task classification such as a WordPress feature being labelled `deployment`;
- managed WordPress work is constrained to repository-managed WordPress source and documentation, not live `wp-content` or host paths;
- MITIGATE self-maintenance can receive Core repository scope only when the mission objective explicitly targets MITIGATE platform/runtime architecture;
- derived scope and rationale are recorded in runtime evidence for diagnosis and audit;
- if execution changes a path outside the derived scope, execution stops fail-closed and reports the scope violation rather than silently widening authorization.

## Memory contract

Durable knowledge must answer what the project is, its architecture, what changed, why it changed, previous failures and successful fixes, decisions, constraints, deployment process, known risks, and outstanding work.

Canonical memory must remain readable and portable without any particular vector database, AI provider, or orchestration framework. Semantic/vector memory is an acceleration layer, never the only copy.

## Self-maintenance and self-upgrade

MITIGATE AI should inspect its own health, tests, dependencies, security findings, runtime failures, and upgrade opportunities. Self-improvement is allowed only through the same controlled engineering pipeline used for managed projects.

- low-risk maintenance may be autonomous after validation;
- runtime/framework upgrades require compatibility validation and staged rollout;
- security-policy, secret, privilege, or trust-boundary changes require explicit approval;
- rollback must remain available for platform upgrades.

## Portability and no lock-in

No AI provider, orchestration framework, vector database, browser framework, or external agent runtime may become required for recovery of the MITIGATE AI platform.

External systems are integrations behind stable MITIGATE-owned interfaces. If an integration becomes unavailable or incompatible, the core platform, Git history, durable memory, policies, mission records, and project configuration must remain usable.

## Ruflo role

Ruflo is an optional orchestration/agent capability provider, not the MITIGATE AI core. It may provide swarm coordination, specialized agents, semantic/RAG memory acceleration, learning/autopilot features, observability helpers, browser/testing capabilities, or other useful functionality through a MITIGATE-owned adapter.

The detailed boundary, version policy, and upgrade policy are defined in `RUFLO_INTEGRATION_CONTRACT.md` and `RUFLO_UPGRADE_POLICY.md`.
