# Portable MITIGATE AI + Agent Canvas Stack

## Goal

A fresh server should be able to restore the MITIGATE AI control plane from GitHub with minimal host-specific work. GitHub remains the source of truth for code, deployment manifests, non-secret configuration templates, tests, and recovery documentation. Secrets remain outside Git.

## Components

- MITIGATE production Runtime API on localhost port 8765.
- MITIGATE autonomous Worker consuming the durable mission queue.
- MITIGATE read-only inspection executor and external runtime routing.
- MITIGATE Web Panel for Runtime requests, mission status, and execution history.
- OpenHands Agent Canvas on localhost port 8000 for interactive agent conversations, terminal/files UI, and automations.
- External runtimes installed under `/srv/mitigate/external-runtimes` where applicable.

## Agent Canvas deployment

The pinned default is `ghcr.io/openhands/agent-canvas:1.7.0`. The deployment binds only to `127.0.0.1:8000`, persists OpenHands state outside the repository, and mounts the configured project root under `/projects`.

Files:

- `agent/deploy/agent-canvas/docker-compose.yml`
- `agent/deploy/agent-canvas/agent-canvas.env.example`
- `agent/bootstrap/start_agent_canvas.sh`

Required secret:

- `LOCAL_BACKEND_API_KEY` — generate independently on every deployment. Never commit the real value.

## Security boundaries

Agent Canvas can drive agents with filesystem, shell, and network access. It must not be exposed directly on a public wildcard interface. The default deployment is localhost-only. Use an SSH tunnel for initial access or an authenticated TLS reverse proxy for deliberate remote access.

The MITIGATE Runtime API remains independently bound to localhost and retains its own bearer-token authentication. Agent Canvas does not replace the MITIGATE queue, worker, checkpoints, execution reports, or governance paths.

## Fresh-server recovery contract

A fresh deployment should follow this order:

1. Clone `144armin1383/mitigate-ai-platform` into `/srv/mitigate/mitigate-ai-platform`.
2. Install base host prerequisites and Docker/Compose.
3. Create `/etc/mitigate-ai/runtime.env` from the repository template and supply real secrets.
4. Restore/create persistent data directories under `/srv/mitigate/data`.
5. Install the MITIGATE Python environment and external runtimes.
6. Install/enable MITIGATE systemd services.
7. Create `/etc/mitigate-ai/agent-canvas.env` from the Agent Canvas example and generate `LOCAL_BACKEND_API_KEY`.
8. Start Agent Canvas through `agent/bootstrap/start_agent_canvas.sh`.
9. Run the repository health checks and one end-to-end inspection request before exposing any UI remotely.

## Portability rule

No production secret, generated API key, machine-specific credential, private SSH key, or mutable runtime queue/checkpoint/report file belongs in Git. Everything needed to recreate the software and deployment structure does belong in Git.
