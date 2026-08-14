# MITIGATE Agent Canvas Integration

## Purpose

Agent Canvas is the normal operator UI for MITIGATE AI. MITIGATE-specific controls must not be implemented by patching Canvas source files or its container filesystem.

There is intentionally no second public MITIGATE control panel. The historical `/mitigate-panel/` route is obsolete and must not be exposed. Port `8766` remains loopback-only as an API backend for Canvas overlays.

## Durable integration boundary

MITIGATE integrates with Canvas through host-owned Nginx injection and same-origin MITIGATE API routes:

- Canvas remains served under `/canvas` by its upstream service.
- MITIGATE-owned JavaScript assets are stored outside the Canvas container under `/usr/local/share/mitigate-ai`.
- Nginx injects the runtime and approval assets into Canvas HTML responses.
- Runtime status uses `/mitigate-runtime/providers`.
- Approval/request API calls use `/mitigate-runtime/api/`.
- Both are proxied to the loopback-only MITIGATE API service on `127.0.0.1:8766`.
- The public hostname is not hard-coded. The integration therefore works with the current IP and with a future domain on the same Nginx virtual host.

## Canvas controls

### MITIGATE Runtimes

The runtime control reports OpenHands, OpenClaw and Ruflo. Each runtime card shows the installed version, latest stable upstream version, whether an update is available, runtime availability and optional functional diagnostics.

Release checks use the same upstream registries as the managed update lifecycle: PyPI for OpenHands and npm for OpenClaw/Ruflo.

### MITIGATE Approvals

When MITIGATE Core exposes a mission as `awaiting_approval`, the approval overlay displays it directly inside Canvas. `Approve & Merge` calls the governed MITIGATE approval endpoint; the browser never chooses a Git branch or commit directly.

MITIGATE Core remains responsible for branch resolution, canonical-main validation, `git diff --check`, forbidden-path validation, fast-forward safety, GitHub push verification, audit persistence and final mission-state transition.

## Canvas upgrades

A Canvas image/package update may replace Canvas itself, but it must not remove MITIGATE controls because the integration files live on the host and in this repository, not inside Canvas.

After a Canvas upgrade:

1. Confirm the Canvas route still returns HTML containing `</body>`.
2. Run `agent/bootstrap/install_canvas_ui_integration.sh`.
3. Run `nginx -t` and verify both `MITIGATE Runtimes` and `MITIGATE Approvals` load.
4. Confirm `/mitigate-panel/` is not exposed.
5. Do not patch upstream Canvas source unless this external integration boundary becomes technically impossible.

The unified installer is idempotent, restores both controls from GitHub, removes the obsolete standalone panel route by recreating the managed Nginx snippet, and keeps a timestamped Nginx backup before changing host integration files.

## Failure boundary

MITIGATE overlays must fail open with respect to Agent Canvas. If a runtime release check, approval API, or overlay compatibility check fails, the official Canvas UI must remain usable. A MITIGATE overlay failure must never require rolling back an otherwise healthy upstream Canvas release.
