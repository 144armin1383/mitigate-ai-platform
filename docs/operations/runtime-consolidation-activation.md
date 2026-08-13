# MITIGATE Runtime Consolidation Activation

This document records the production activation contract for the consolidated runtime.

## Production entrypoint

The consolidated worker entrypoint is:

`python -m agent.runtime.runtime_consolidation_worker`

MITIGATE remains the control plane. OpenHands, OpenClaw and Ruflo remain replaceable external runtime providers behind MITIGATE adapters.

## systemd precedence

The activation drop-in must sort after all existing worker `ExecStart` overrides. The canonical activation drop-in is:

`/etc/systemd/system/mitigate-ai-worker.service.d/zzzz-runtime-consolidation.conf`

The legacy lower-precedence name `runtime-consolidation.conf` must not remain active.

## Safety requirements

Activation is permitted only when:

- repository branch is `main`;
- canonical repository is clean;
- `main` equals `origin/main`;
- isolated OpenHands runtime exists;
- OpenClaw runtime exists;
- Ruflo runtime exists;
- runtime adapter tests pass;
- worker and runtime API remain active after restart;
- effective `ExecStart` contains `agent.runtime.runtime_consolidation_worker`;
- canonical repository remains clean.

Failure at any post-activation verification step must remove consolidation drop-ins and restart the legacy worker.

## Rollback

Rollback removes both the canonical and legacy consolidation drop-ins, reloads systemd, restarts the worker, and verifies that the legacy `agent.runtime.background_worker` entrypoint is active.

## Recovery evidence

Before activation, the effective worker unit is stored under `/srv/mitigate/data/runtime/recovery/runtime-consolidation-<UTC timestamp>/`.

## GitHub backup policy

Before a production activation/fix, preserve the pre-change `main` commit using a dedicated `backup/...` branch. After a successful production activation, preserve the activated `main` commit using a second backup branch so the exact known-good source state remains directly recoverable from GitHub.
