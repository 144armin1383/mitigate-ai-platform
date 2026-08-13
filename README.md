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

Agent Canvas has a dedicated upgrade workflow that performs preflight checks, pulls the target image, starts the new version, waits for readiness, reapplies the persistent OpenHands LLM profile, performs functional configuration verification, and retains rollback handling.

The OpenHands LLM configuration is persisted through the Agent Server API so a Canvas replacement or upgrade does not require manually re-entering the model configuration.

## OpenHands, OpenClaw and Ruflo upgrades

OpenHands, OpenClaw and Ruflo have dedicated upgrade scripts. Updates are performed through controlled candidate/install workflows and are verified before the new runtime is accepted. OpenClaw and Ruflo update handling includes rollback hardening to avoid leaving the active runtime in a partially upgraded state.

On low-memory hosts, swap must remain available because npm dependency installation can temporarily require substantially more memory than normal runtime operation.

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

The repository is the portable source of truth for MITIGATE AI. Installation, runtime configuration, update lifecycle, resource safeguards and recovery behavior should be encoded in GitHub wherever practical so a fresh server can be deployed from the repository without reconstructing previously solved operational fixes by hand.
