from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.execution.managed_openhands_adapter import ManagedOpenHandsRuntimeAdapter
from agent.runtime.workspace_production_mission_controller import WorkspaceProductionMissionController


class ManagedWorkspaceMissionController(WorkspaceProductionMissionController):
    def __init__(
        self,
        *,
        repository_root: str | Path | None = None,
        timeout_seconds: int = 1800,
        review_callback: Any | None = None,
    ) -> None:
        root = Path(
            repository_root or "/srv/mitigate/mitigate-ai-platform"
        ).expanduser().resolve()
        super().__init__(
            repository_root=root,
            timeout_seconds=timeout_seconds,
            adapter=ManagedOpenHandsRuntimeAdapter(repository_root=root),
            review_callback=review_callback,
        )

    def execute(self, mission: dict[str, Any]) -> dict[str, Any]:
        result = super().execute(mission)
        if not isinstance(result, dict):
            return {"status": "blocked", "reason": "invalid_controller_result"}

        status = str(result.get("status") or "").lower()
        reason = str(result.get("reason") or "").lower()

        if status == "exhausted" and any(
            marker in reason
            for marker in (
                "managed_openhands_execution_failed",
                "managed_openhands_runtime_unavailable",
                "timeout",
                "connection",
                "network",
            )
        ):
            result["status"] = "retry"
            result["failure_class"] = "transient_runtime"
        elif any(
            marker in reason
            for marker in (
                "quota_exhausted",
                "credentials_unavailable",
                "runtime_changed_paths_outside_authorized_scope",
                "canonical_repository_not_clean",
            )
        ):
            result["status"] = "blocked"
            result["failure_class"] = "policy_or_external_requirement"
        else:
            result["failure_class"] = status or "unknown"

        return result


__all__ = ["ManagedWorkspaceMissionController"]
