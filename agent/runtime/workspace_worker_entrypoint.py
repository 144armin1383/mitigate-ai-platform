from __future__ import annotations

import argparse
import os
from pathlib import Path

from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.background_worker import BackgroundWorker
from agent.runtime.checkpoint_store import DurableCheckpointStore
from agent.runtime.managed_workspace_mission_controller import (
    ManagedWorkspaceMissionController,
)
from agent.runtime.production_execution_reporter import ProductionExecutionReporter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MITIGATE isolated autonomous production worker"
    )
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--worker-id", default="production-worker")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--heartbeat-path", default=None)
    args = parser.parse_args()

    if args.poll_interval <= 0:
        raise SystemExit("poll-interval must be > 0")

    data_root = Path(
        os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")
    ).expanduser().resolve()
    project_id = str(
        os.environ.get("MITIGATE_AI_DEFAULT_PROJECT_ID", "mitigate-ai-platform")
    ).strip() or "mitigate-ai-platform"

    reporter = ProductionExecutionReporter(
        storage_dir=data_root / "runtime" / "execution-reports",
        project_id=project_id,
    )
    checkpoint_store = DurableCheckpointStore(
        storage_dir=data_root / "runtime" / "checkpoints",
    )

    worker = BackgroundWorker(
        queue=AutonomousMissionQueue(args.queue_path),
        controller=ManagedWorkspaceMissionController(),
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        heartbeat_path=args.heartbeat_path,
        execution_reporter=reporter,
        checkpoint_store=checkpoint_store,
        checkpoint_project_id=project_id,
    )
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
