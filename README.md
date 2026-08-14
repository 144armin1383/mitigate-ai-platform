# MITIGATE AI Platform

This repository contains the infrastructure, AI agent, WordPress customizations,
automation, documentation and deployment scripts for the MITIGATE platform.

## Repository structure

- `agent/`
- `wordpress/`
- `infrastructure/`
- `scripts/`
- `automation/`
- `docs/`
- `knowledge/`
- `tests/`

## Managed AI components

MITIGATE AI includes a managed component lifecycle for the core external runtimes used by the platform. The currently managed components include:

- OpenHands / `openhands-sdk`
- OpenClaw
- Ruflo
- OpenHands Agent Canvas

The managed-component registry is stored in:

```text
agent/config/managed-components.json
```

The platform is designed so additional components can be registered and incorporated into the same lifecycle in the future.

## Automatic updates

Managed components are checked automatically every day through the systemd timer:

```text
mitigate-ai-auto-update.timer
```

The corresponding service is:

```text
mitigate-ai-auto-update.service
```

The lifecycle is designed to use stable releases, perform host-resource preflight checks, verify component/platform health, prevent overlapping update runs, and use rollback handling where supported.

The systemd definitions are version-controlled in:

```text
agent/deploy/systemd/mitigate-ai-auto-update.service
agent/deploy/systemd/mitigate-ai-auto-update.timer
```

The maintenance implementation is stored under:

```text
agent/maintenance/
```

Important scripts include:

```text
ensure_host_resources.sh
upgrade_managed_components.py
upgrade_agent_canvas.sh
upgrade_openhands.sh
upgrade_openclaw.sh
upgrade_ruflo.sh
upgrade_all_external_runtimes.sh
verify_platform_after_upgrade.sh
```

## Host resource safeguards

Before managed upgrades, the platform checks the host resources required to complete an update safely. The deployment currently supports persistent swap provisioning for low-memory hosts and disk-space checks before large upgrades such as Agent Canvas image replacement.

The current production host was validated with a persistent 4 GB swap file. Fresh deployments should obtain the required host-resource configuration through the repository bootstrap rather than requiring manual recovery steps.

The host-resource logic is maintained in:

```text
agent/maintenance/ensure_host_resources.sh
```

## Agent Canvas upgrades

Agent Canvas has a dedicated upgrade workflow that performs preflight checks, pulls the target image only when a newer stable version is detected, starts the new version, waits for readiness, reapplies the persistent OpenHands LLM profile, performs functional configuration verification, and retains rollback handling.

The OpenHands LLM configuration is persisted through the Agent Server API so a Canvas replacement or upgrade does not require manually re-entering the model configuration.

## Unified MITIGATE controls inside Agent Canvas

Agent Canvas is the single normal operator UI. MITIGATE does not maintain a second public control-panel page. The legacy `/mitigate-panel/` UI is intentionally removed; the service bound to `127.0.0.1:8766` is a private API backend only and is not a public standalone panel.

MITIGATE-specific controls are injected into the existing `/canvas` interface through a repository-managed Nginx integration layer. The official Agent Canvas image, source code and container filesystem remain untouched.

The Canvas UI contains two MITIGATE-owned controls:

```text
MITIGATE Runtimes
MITIGATE Approvals
```

### MITIGATE Runtimes

Opening `MITIGATE Runtimes` displays live status for:

```text
OpenHands
OpenClaw
Ruflo
```

For every runtime the overlay reports:

- installed version;
- latest stable upstream version;
- whether the installed version is current or an update is available;
- runtime availability;
- LLM configuration for OpenHands;
- optional functional diagnostics for OpenClaw and Ruflo.

Latest-version checks use the same upstream package sources used by the managed upgrade lifecycle: PyPI for `openhands-sdk` and npm for OpenClaw/Ruflo. A release-check failure is reported separately and must not make Agent Canvas unavailable.

The runtime integration source is version-controlled in:

```text
agent/integrations/agent-canvas/mitigate-runtime-overlay.js
agent/web/external_runtime_probe.py
agent/bootstrap/install_canvas_ui_integration.sh
agent/maintenance/verify_canvas_ui_integration.sh
```

### MITIGATE Approvals

When MITIGATE Core reaches a governed `manual_review_required` boundary, the public mission state is exposed as:

```text
state = awaiting_approval
queue_state = blocked
status_reason = manual_review_required
requires_action = manual_review
```

The `MITIGATE Approvals` control displays those missions directly inside Canvas. Each card provides two explicit human decisions:

- `Approve & Merge` validates the selected mission and allows MITIGATE Core to fast-forward its governed branch into `main` when safe;
- `Reject` removes the mission from the active approval queue by transitioning its durable queue state to `cancelled` without merging or modifying canonical Git content.

The Reject action is intentionally red and requires confirmation. Rejecting does not erase the audit trail or mission evidence. The browser sends only the selected mission ID; it cannot supply an arbitrary Git branch, commit, ref, approver identity or shell command.

MITIGATE Core remains responsible for:

- resolving the mission branch;
- verifying canonical `main` is clean and synchronized with `origin/main`;
- `git diff --check` validation;
- forbidden-path checks;
- fast-forward-only merge safety;
- GitHub push and remote verification;
- durable approval/rejection audit persistence;
- final mission transition to `completed` after approval or `cancelled` after rejection.

#### Durable human decision history

Every Approve or Reject decision is persisted outside the Git worktree so audit state never dirties canonical `main`.

Per-mission decision records are stored under:

```text
/srv/mitigate/data/runtime/approvals/<mission-id>.json
```

An append-only machine-readable history is stored at:

```text
/srv/mitigate/data/runtime/approvals/decision-history.jsonl
```

Each record includes, where available:

- mission ID;
- request ID;
- decision (`approved` or `rejected`);
- authenticated decision-maker identity;
- UTC decision timestamp;
- mission branch and commit;
- canonical `main` before and after the decision;
- changed-file list;
- whether the approved commit was already merged;
- resulting mission state.

Agent Canvas can read recent records through the read-only MCP tool:

```text
mitigate_manual_review_history
```

This history is intended to be consulted during regression diagnosis, incident analysis and recovery so an agent can determine which human-approved or rejected change most recently affected the governed lifecycle.

The approval integration source is version-controlled in:

```text
agent/web/canvas_approval_overlay.js
agent/runtime/manual_review_approval.py
agent/runtime/manual_review_status.py
agent/runtime/runtime_mcp_server.py
agent/deploy/nginx/mitigate-ai-canvas-approval.conf
agent/bootstrap/install_canvas_ui_integration.sh
```

## Canvas update survival

MITIGATE Canvas controls are deliberately external to the upstream Agent Canvas image. They do not use `docker exec` to patch the Canvas frontend, do not overwrite files inside the upstream container, and do not require a fork of Agent Canvas.

The durable boundary is:

```text
Agent Canvas upstream UI
        ↑
Nginx external script injection
        ↑
MITIGATE repository-managed runtime + approval overlays
        ↑
Same-origin /mitigate-runtime/... routes
        ↑
Loopback-only MITIGATE API on 127.0.0.1:8766
```

After an Agent Canvas upgrade, rerun:

```bash
sudo bash /srv/mitigate/mitigate-ai-platform/agent/bootstrap/install_canvas_ui_integration.sh
```

The installer is idempotent, recreates both overlays and API routes from GitHub, validates Nginx before reload, keeps timestamped host backups, and intentionally removes the obsolete standalone `/mitigate-panel/` route. It contains no public IP or hostname dependency, so the same integration works after migration from the current IP to a domain on the same Nginx host.

If an upstream Canvas HTML change makes script injection incompatible, MITIGATE must report the integration as degraded without modifying or rolling back an otherwise healthy Agent Canvas release.

### Upstream protection policy

```text
NEVER modify upstream Agent Canvas frontend files.
NEVER overwrite files inside the official Agent Canvas container.
NEVER require a permanent fork of the upstream frontend for MITIGATE controls.
Keep MITIGATE UI code in this repository, outside the upstream image.
Agent Canvas updates remain independent from MITIGATE UI compatibility.
A failed MITIGATE overlay must not make Agent Canvas unavailable.
```

## OpenHands, OpenClaw and Ruflo upgrades

OpenHands, OpenClaw and Ruflo have dedicated upgrade scripts. Updates are performed through controlled candidate/install workflows and are verified before the new runtime is accepted. OpenClaw and Ruflo update handling includes rollback hardening to avoid leaving the active runtime in a partially upgraded state.

On low-memory hosts, swap must remain available because npm dependency installation can temporarily require substantially more memory than normal runtime operation.

OpenClaw uses the portable state path:

```text
/srv/mitigate/data/openclaw
```

rather than a user-specific home-directory state path. This path is shared consistently across the MITIGATE API, runtime gateway and worker services.

## Daily update status

Check the next scheduled automatic update with:

```bash
systemctl list-timers mitigate-ai-auto-update.timer --no-pager
```

Check the most recent automatic-update logs with:

```bash
sudo journalctl -u mitigate-ai-auto-update.service --no-pager -n 200
```

Check the timer itself with:

```bash
systemctl status mitigate-ai-auto-update.timer --no-pager
```

## Manual managed-runtime check

A manual managed-runtime update/check can be started with:

```bash
sudo bash /srv/mitigate/mitigate-ai-platform/agent/maintenance/upgrade_all_external_runtimes.sh
```

Routine operation should normally rely on the automatic lifecycle rather than requiring manual update commands.

## Operational design goal

The repository is the portable source of truth for MITIGATE AI. Installation, runtime configuration, update lifecycle, resource safeguards, Canvas control APIs, Agent Canvas integration and recovery behavior should be encoded in GitHub wherever practical so a fresh server can be deployed from the repository without reconstructing previously solved operational fixes by hand.
