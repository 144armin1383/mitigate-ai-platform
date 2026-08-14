# MITIGATE Agent Canvas Integration

## Purpose

Agent Canvas is an external UI/runtime component. MITIGATE-specific controls must not be implemented by patching Canvas source files or its container filesystem.

## Durable integration boundary

MITIGATE integrates with Canvas through host-owned Nginx injection and same-origin MITIGATE API routes:

- Canvas remains served under `/canvas` by its upstream service.
- MITIGATE-owned JavaScript assets are stored outside the Canvas container under `/usr/local/share/mitigate-ai`.
- Nginx injects those assets into Canvas HTML responses.
- Approval/API calls use same-origin paths under `/mitigate-runtime/api/` and are proxied to the loopback-only MITIGATE panel service.
- The public hostname is not hard-coded. The integration therefore works with the current IP and with a future domain on the same Nginx virtual host.

## Canvas upgrades

A Canvas image/package update may replace Canvas itself, but it must not remove the MITIGATE integration because the integration files live on the host and in this repository, not inside Canvas.

After a Canvas upgrade:

1. Confirm the Canvas route still returns HTML containing `</body>`.
2. Run `agent/bootstrap/install_canvas_approval_integration.sh`.
3. Run `nginx -t` and verify the MITIGATE approval overlay loads.
4. Do not patch upstream Canvas source unless this external integration boundary becomes technically impossible.

The installer is idempotent and keeps a timestamped Nginx backup before changing the host integration snippet.

## Approval flow

When MITIGATE Core exposes a mission as `awaiting_approval`, the Canvas approval overlay displays it in the same Canvas UI. `Approve & Merge` calls the governed MITIGATE approval endpoint; the browser never chooses a Git branch or commit directly.

MITIGATE Core remains responsible for branch resolution, validation, fast-forward safety, GitHub push verification, audit persistence, and final mission-state transition.
