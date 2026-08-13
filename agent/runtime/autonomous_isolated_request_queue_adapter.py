from __future__ import annotations

from pathlib import Path

from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.isolated_request_queue_adapter import (
    IsolatedProductionRequestQueueAdapter,
)


class AutonomousIsolatedProductionRequestQueueAdapter(
    IsolatedProductionRequestQueueAdapter
):
    """Production request adapter with isolated definitions and bounded retries."""

    def __init__(
        self,
        *,
        project_id: str,
        queue_path: str | Path,
        repository_root: str | Path,
    ) -> None:
        super().__init__(
            project_id=project_id,
            queue_path=queue_path,
            repository_root=repository_root,
        )
        # Parent enqueue_batch uses self.queue. Rebind it after legacy migration
        # so newly planned missions receive the bounded autonomous retry policy.
        self.queue = AutonomousMissionQueue(
            str(Path(queue_path).expanduser().resolve())
        )


__all__ = ["AutonomousIsolatedProductionRequestQueueAdapter"]
