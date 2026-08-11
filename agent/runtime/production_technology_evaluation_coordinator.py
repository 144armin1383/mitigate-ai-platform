from __future__ import annotations

from typing import Any, Mapping, Sequence


class ProductionTechnologyEvaluationCoordinator:
    """
    Thin production coordinator for TechnologyEvaluationMissionBridge.

    It reuses ProductionRequestQueueAdapter so rich MITIGATE mission
    definitions are materialized before the lightweight MissionQueue
    record becomes visible to the production worker.

    This class does not create:
    - a worker
    - a scheduler
    - a queue
    - a mission runner
    - an external runtime dependency
    """

    def __init__(
        self,
        *,
        request_queue_adapter: Any,
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

        if request_queue_adapter is None:
            raise ValueError(
                "request_queue_adapter is required"
            )

        enqueue_batch = getattr(
            request_queue_adapter,
            "enqueue_batch",
            None,
        )

        if not callable(
            enqueue_batch
        ):
            raise TypeError(
                "request_queue_adapter does not support enqueue_batch"
            )

        self._adapter = (
            request_queue_adapter
        )
        self._project_id = (
            project_key
        )
        self._queue_reference = (
            queue_key
        )

    def enqueue(
        self,
        project_id: str,
        queue_reference: str,
        missions: Sequence[
            Mapping[str, Any]
        ],
    ) -> Mapping[str, Any]:
        if (
            str(project_id).strip()
            != self._project_id
        ):
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

        mission_ids = (
            self._adapter.enqueue_batch(
                missions
            )
        )

        return {
            "accepted": True,
            "project_id":
                self._project_id,
            "queue_reference":
                self._queue_reference,
            "mission_ids":
                list(
                    mission_ids
                ),
            "enqueued_count":
                len(
                    mission_ids
                ),
        }


__all__ = [
    "ProductionTechnologyEvaluationCoordinator",
]
