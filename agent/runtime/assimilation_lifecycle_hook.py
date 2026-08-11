from __future__ import annotations

from typing import Any, Mapping, Protocol


NATIVE_REPLACEMENT_TASK_TYPE = (
    "native_capability_replacement"
)


class AssimilationReconcilerProtocol(
    Protocol
):
    def reconcile(
        self,
        technology_id: str,
    ) -> Any:
        ...


class RuntimeAssimilationLifecycleHook:
    """
    Post-persistence lifecycle observer.

    The hook has no mission execution, queue transition,
    scheduling, retry, or network authority.

    Ordinary MITIGATE missions are ignored.

    Native replacement missions are reconciled only after
    their execution report has already been persisted.
    """

    def __init__(
        self,
        *,
        reconciler: AssimilationReconcilerProtocol,
    ) -> None:
        self._reconciler = reconciler

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
            != NATIVE_REPLACEMENT_TASK_TYPE
        ):
            return {
                "handled": False,
                "reason": "not_native_replacement",
            }

        technology_id = (
            self._technology_id(
                mission
            )
        )

        if not technology_id:
            return {
                "handled": False,
                "reason": "technology_context_missing",
            }

        if not isinstance(
            report,
            Mapping,
        ):
            return {
                "handled": False,
                "reason": "invalid_report",
            }

        mission_id = str(
            mission.get(
                "id"
            )
            or mission.get(
                "mission_id"
            )
            or ""
        ).strip()

        report_mission_id = str(
            report.get(
                "mission_id",
                "",
            )
        ).strip()

        if (
            not mission_id
            or report_mission_id
            != mission_id
        ):
            return {
                "handled": False,
                "reason": "mission_report_mismatch",
            }

        result = (
            self._reconciler.reconcile(
                technology_id
            )
        )

        return {
            "handled": True,
            "technology_id":
                technology_id,
            "status": getattr(
                result,
                "status",
                None,
            ),
        }

    @staticmethod
    def _technology_id(
        mission: Mapping[str, Any],
    ) -> str | None:
        payload = mission.get(
            "payload"
        )

        if not isinstance(
            payload,
            Mapping,
        ):
            return None

        resilience = payload.get(
            "resilience"
        )

        if not isinstance(
            resilience,
            Mapping,
        ):
            return None

        source_context = (
            resilience.get(
                "source_context"
            )
        )

        if not isinstance(
            source_context,
            Mapping,
        ):
            return None

        technology_id = str(
            source_context.get(
                "technology",
                "",
            )
        ).strip()

        return (
            technology_id
            or None
        )


__all__ = [
    "RuntimeAssimilationLifecycleHook",
]
