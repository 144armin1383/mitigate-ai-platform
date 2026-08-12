from __future__ import annotations

from typing import Any, Mapping


TECHNOLOGY_EVALUATION_TASK_TYPE = (
    "technology_evaluation"
)

NATIVE_REPLACEMENT_TASK_TYPE = (
    "native_capability_replacement"
)


class ProductionLifecycleDispatcher:
    """
    Route persisted mission execution results to the appropriate
    MITIGATE-owned lifecycle reconciler.

    This dispatcher:
    - executes no missions
    - enqueues no missions
    - creates no scheduler
    - accesses no network
    - introduces no external runtime dependency
    """

    def __init__(
        self,
        *,
        evaluation_reconciler: Any,
        assimilation_hook: Any,
    ) -> None:
        if evaluation_reconciler is None:
            raise ValueError(
                "evaluation_reconciler is required"
            )

        if assimilation_hook is None:
            raise ValueError(
                "assimilation_hook is required"
            )

        self._evaluation_reconciler = (
            evaluation_reconciler
        )

        self._assimilation_hook = (
            assimilation_hook
        )

    def after_persist(
        self,
        *,
        mission: Mapping[str, Any],
        report: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(
            mission,
            Mapping,
        ):
            return {
                "handled": False,
                "reason": "invalid_mission",
            }

        task_type = str(
            mission.get(
                "task_type",
                "",
            )
        ).strip()

        if (
            task_type
            == TECHNOLOGY_EVALUATION_TASK_TYPE
        ):
            result = (
                self._evaluation_reconciler
                .reconcile(
                    mission=mission,
                    report=report,
                )
            )

            return {
                "handled":
                    result.handled,
                "lifecycle":
                    "technology_evaluation",
                "technology_id":
                    result.technology_id,
                "recommendation":
                    result.recommendation,
                "evaluation_state":
                    result.evaluation_state,
                "assimilation_state":
                    result.assimilation_state,
                "idempotent":
                    result.idempotent,
                "reason":
                    result.reason,
            }

        if (
            task_type
            == NATIVE_REPLACEMENT_TASK_TYPE
        ):
            result = (
                self._assimilation_hook
                .after_persist(
                    mission=mission,
                    report=report,
                )
            )

            return {
                **dict(result),
                "lifecycle":
                    "native_assimilation",
            }

        return {
            "handled": False,
            "reason": "unsupported_task_type",
        }


__all__ = [
    "NATIVE_REPLACEMENT_TASK_TYPE",
    "TECHNOLOGY_EVALUATION_TASK_TYPE",
    "ProductionLifecycleDispatcher",
]
