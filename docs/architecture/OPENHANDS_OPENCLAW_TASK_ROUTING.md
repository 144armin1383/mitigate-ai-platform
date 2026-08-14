# OpenHands / OpenClaw Task Routing

Status: production routing policy

## Decision

MITIGATE Core remains the authority for mission state, approvals, Git publication, durable memory and deployment. External runtimes execute only inside MITIGATE-owned disposable workspaces.

### OpenHands — technical engineering primary

Primary for:

- backend and API development;
- PHP/WordPress backend/plugin work;
- database changes;
- infrastructure, Nginx, systemd and deployment;
- security review and remediation;
- automated testing, regression diagnosis and bug fixing;
- refactors and repository maintenance;
- technical SEO: redirects, sitemap, robots, schema, performance and crawl/index implementation;
- monitoring/diagnostics when the task is primarily technical.

Reason: OpenHands is purpose-built as a software-engineering agent with terminal, file editing, testing, MCP and repository workflows. MITIGATE already runs it in disposable workspaces.

### OpenClaw — frontend / live-browser primary

Primary for:

- frontend and WordPress page creation/editing;
- UI/UX and responsive styling;
- forms and content presentation;
- visual validation against the live site;
- browser-led page inspection;
- design-reference tasks, including a user-supplied public reference such as `https://motionsites.ai/`;
- content insertion and visual changes.

OpenClaw must inspect the existing site UI first and reuse its established design language. A reference site is inspiration only: do not copy proprietary source code, branding or protected assets.

## OpenClaw stable compatibility execution

MITIGATE supports two governed OpenClaw coding entry points behind the same adapter contract:

1. Native `openclaw agent exec` when the installed OpenClaw release exposes `--message-file`, `--cwd` and `--json`.
2. Stable compatibility mode for releases such as `v2026.7.1-2`, whose documented CLI exposes `openclaw agent --local` but not yet `agent exec`. The repository-owned compatibility wrapper translates only the narrow MITIGATE `agent exec` invocation into `agent --local`, supplies a unique mission session key, and sets the documented `OPENCLAW_WORKSPACE_DIR` override to the MITIGATE disposable workspace.

The wrapper validates that the requested workspace resolves below `MITIGATE_WORKSPACE_ROOT` before launching OpenClaw. Unknown compatibility arguments fail closed. If neither native `agent exec` nor the required stable `agent --local` flags are present, OpenClaw coding remains disabled and the router reports the provider unavailable rather than silently weakening isolation.

This compatibility bridge exists because the latest stable OpenClaw release may lag the current upstream `main` CLI. It must be removed naturally in favor of native `agent exec` once a stable installed release provides that command; the activation probe chooses native execution automatically when available.

## Host/domain portability

Never hard-code the current public IP into WordPress page content, application routes or internal links. Use relative paths or the WordPress/site canonical URL. A page requested today as:

```text
https://18.175.175.110/fourmnew
```

must continue to resolve after the site moves to a domain such as:

```text
https://mitigateuk.com/fourmnew
```

If the user explicitly asks for a subdomain instead of a path, the agent must treat DNS/TLS/domain ownership as a separate infrastructure requirement and ask one concise clarification if the intended hostname is not supplied.

## Intelligent clarification rule

Agents should inspect the existing project/site before asking questions. Do not ask questions that can be answered safely from the repository, WordPress configuration or current UI.

If a material business/product fact is genuinely missing, ask one concise consolidated question before inventing it. Example: for a recruitment form, if the hiring area/role taxonomy materially changes the form and cannot be inferred, ask which roles or departments should be offered. If no answer is required for a safe generic implementation, use a neutral `General application` option and proceed.

## Runtime switch

Automatic routing is the default.

An operator can explicitly prefer a runtime in mission text with one of:

```text
runtime=openhands
runtime=openclaw
provider=openhands
provider=openclaw
use OpenHands
use OpenClaw
```

The forced provider is recorded in runtime evidence. Provider failover remains controlled by MITIGATE Core and never bypasses policy, credentials, quota, approval or canonical-Git safety failures.

## Non-interference rule

OpenHands and OpenClaw never edit canonical `main` directly. Every attempt receives a disposable workspace. Runtime attempts are sequential, not concurrent, and MITIGATE publishes/reviews the resulting branch. Frontend missions default to `wordpress/` + `docs/`; technical missions remain repository-scope constrained by task type and explicit deliverables.

## Panel validation missions

### Frontend / OpenClaw test

Submit from Agent Canvas with task type `frontend`:

```text
Create a production-quality WordPress recruitment page at /fourmnew. Inspect the current MITIGATE site first and use its existing UI, typography, spacing, components and responsive behavior. Build a complete employment application form with sensible fields, validation, consent/privacy acknowledgement, accessible labels, mobile layout and a safe backend submission path consistent with the existing repository architecture. Do not hard-code the server IP; the page must continue to work when the site moves to its domain. If one material business requirement is genuinely missing, ask one concise consolidated clarification question instead of inventing it. You may use https://motionsites.ai/ only as optional visual/motion inspiration; do not copy proprietary code, branding or assets. runtime=openclaw
```

Expected evidence: provider `openclaw`, browser/live-site inspection where available, changed paths limited to the authorized WordPress/frontend scope, validation/tests, and a governed mission branch awaiting approval.

### Technical / OpenHands test

Submit from Agent Canvas with task type `backend`:

```text
Perform a technical health review of the MITIGATE WordPress delivery stack and repository integration. Inspect Nginx/PHP/WordPress routing assumptions represented in the repository, identify one concrete low-risk technical defect or maintainability issue that can be proven from repository evidence, implement the smallest safe fix, add or update regression coverage, and report the validation performed. Do not make visual/page-design changes. runtime=openhands
```

Expected evidence: provider `openhands`, repository-first diagnostics, tests, no frontend design changes, and a governed mission branch awaiting approval.

## Upstream basis

The policy is based on the official OpenHands and OpenClaw project documentation current at the time of this decision. OpenHands emphasizes software-engineering execution, terminal/file tools, tests, browser tooling and MCP. OpenClaw emphasizes its integrated agent runtime, browser/canvas/tools, skills, persistent sessions, multi-agent routing and MCP/ACP integrations. MITIGATE uses only the capabilities exposed safely by its adapters; upstream capability does not override MITIGATE policy.
