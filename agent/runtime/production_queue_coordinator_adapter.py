from __future__ import annotations

from typing import Any, Mapping, Sequence


class ProductionQueueCoordinatorAdapter:
    """
    Thin adapter over the existing MITIGATE production mission queue.

    This class does not create a queue, worker, scheduler, retry engine,
    or execution pipeline. It only translates the existing enqueue
    contract expected by NativeReplacementMissionBridge into the
    production queue's existing enqueue interface.
    """

    def __init__(
        self,
        *,
        queue: Any,
        project_id: str,
        queue_reference: str,
    ) -> None:
        project_key = str(
            project_id
        ).strip()

        queue_key = str(
            queue_reference
        ).strip()

        if not project_key:
            raise ValueError(
                "project_id is required"
            )

        if not queue_key:
            raise ValueError(
                "queue_reference is required"
            )

        if queue is None:
            raise ValueError(
                "queue is required"
            )

        self._queue = queue
        self._project_id = project_key
        self._queue_reference = queue_key

    def enqueue(
        self,
        project_id: str,
        queue_reference: str,
        missions: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        if str(project_id).strip() != self._project_id:
            raise ValueError(
                "unknown_project"
            )

        if (
            str(queue_reference).strip()
            != self._queue_reference
        ):
            raise ValueError(
                "unknown_queue"
            )

        if not missions:
            raise ValueError(
                "missions are required"
            )

        enqueue = getattr(
            self._queue,
            "enqueue",
            None,
        )

        if not callable(
            enqueue
        ):
            raise TypeError(
                "production queue does not support enqueue"
            )

        mission_ids: list[str] = []

        for mission in missions:
            payload = dict(
                mission
            )

            mission_id = str(
                payload.get(
                    "mission_id"
                )
                or payload.get(
                    "id"
                )
                or ""
            ).strip()

            if not mission_id:
                raise ValueError(
                    "mission_id is required"
                )

            priority = int(
                payload.get(
                    "priority",
                    100,
                )
            )

            dependencies = payload.get(
                "dependencies"
            )

            max_retries = payload.get(
                "max_retries"
            )

            enqueue(
                mission_id,
                priority,
                dependencies,
                max_retries=max_retries,
            )

            mission_ids.append(
                mission_id
            )

        return {
            "status": "queued",
            "project_id": self._project_id,
            "queue_reference":
                self._queue_reference,
            "mission_ids":
                mission_ids,
        }


__all__ = [
    "ProductionQueueCoordinatorAdapter",
]
