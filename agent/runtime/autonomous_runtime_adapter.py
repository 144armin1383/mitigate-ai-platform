from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol


class AutonomousControllerProtocol(Protocol):
    def run(self, mission: Dict[str, Any]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class RuntimeExecutionResult:
    status: str
    final_status: str
    attempts: int


class AutonomousRuntimeAdapter:
    """
    Adapter between BackgroundWorker and AutonomousController.

    The AutonomousController owns execution-level retries.
    The BackgroundWorker owns queue lifecycle transitions.

    Controller final statuses are normalized into the worker contract:

        success  -> success
        failed   -> exhausted
        aborted  -> blocked

    Unknown or malformed controller results fail closed as blocked.
    """

    def __init__(self, controller: AutonomousControllerProtocol) -> None:
        self._controller = controller

    def execute(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        report = self._controller.run(mission)

        if not isinstance(report, Mapping):
            return {
                "status": "blocked",
                "final_status": "invalid_report",
                "attempts": 0,
            }

        final_status = str(report.get("final_status", "")).strip().lower()

        try:
            attempts = int(report.get("attempts", 0))
        except (TypeError, ValueError):
            attempts = 0

        if final_status == "success":
            status = "success"
        elif final_status == "failed":
            status = "exhausted"
        elif final_status == "aborted":
            status = "blocked"
        else:
            status = "blocked"

        return {
            "status": status,
            "final_status": final_status or "unknown",
            "attempts": max(0, attempts),
        }


__all__ = [
    "AutonomousRuntimeAdapter",
    "RuntimeExecutionResult",
]
