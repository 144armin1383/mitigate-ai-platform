from __future__ import annotations

import os
from typing import Optional, Sequence

from agent.runtime.mission_queue import (
    MissionQueue,
    MissionState,
    _FileLock,
)


class AutonomousMissionQueue(MissionQueue):
    """MissionQueue with a bounded default retry budget for governed tasks."""

    def __init__(self, path: str, default_max_retries: int | None = None) -> None:
        if default_max_retries is None:
            default_max_retries = int(
                os.environ.get("MITIGATE_AI_AUTONOMOUS_MAX_RETRIES", "2")
            )
        default_max_retries = max(0, min(int(default_max_retries), 3))
        super().__init__(path, default_max_retries=default_max_retries)
        self.autonomous_default_max_retries = default_max_retries

    def enqueue(
        self,
        mission_id: str,
        priority: int,
        dependencies: Sequence[str] | None = None,
        *,
        max_retries: Optional[int] = None,
    ) -> None:
        # Older planner adapters explicitly passed zero. For newly governed
        # autonomous missions, treat that legacy value as "use bounded policy".
        effective = max_retries
        if effective is None or int(effective) <= 0:
            effective = self.autonomous_default_max_retries
        super().enqueue(
            mission_id,
            priority,
            dependencies,
            max_retries=int(effective),
        )

    def approve_manual_review(self, mission_id: str) -> None:
        """Atomically finalize a human-approved manual-review mission.

        This transition is intentionally unavailable to the autonomous worker.
        The governed approval service calls it only after the mission branch has
        been validated and safely fast-forwarded into canonical ``main``.
        """
        with _FileLock(self._lock_path):
            self._load()
            mission = self._get_mission_or_raise(mission_id)
            if mission.state == MissionState.completed:
                return
            if mission.state != MissionState.blocked:
                raise ValueError(
                    "approve_manual_review() requires mission to be blocked"
                )
            mission.state = MissionState.completed
            self._validate_no_cycles()
            self._save()


__all__ = ["AutonomousMissionQueue"]
