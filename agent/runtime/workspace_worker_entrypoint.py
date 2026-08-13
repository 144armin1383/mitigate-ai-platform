from __future__ import annotations

import argparse

from agent.runtime.background_worker import BackgroundWorker
from agent.runtime.mission_queue import MissionQueue
from agent.runtime.workspace_production_mission_controller import (
    WorkspaceProductionMissionController,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MITIGATE isolated production worker"
    )
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--worker-id", default="production-worker")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--heartbeat-path", default=None)
    args = parser.parse_args()

    if args.poll_interval <= 0:
        raise SystemExit("poll-interval must be > 0")

    worker = BackgroundWorker(
        queue=MissionQueue(args.queue_path),
        controller=WorkspaceProductionMissionController(),
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        heartbeat_path=args.heartbeat_path,
    )
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
