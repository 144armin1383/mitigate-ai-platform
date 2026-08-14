from __future__ import annotations

import json
import os
import time
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
        self.data_root = Path(
            os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")
        ).expanduser().resolve()
        super().__init__(
            repository_root=root,
            timeout_seconds=timeout_seconds,
            adapter=ManagedOpenHandsRuntimeAdapter(repository_root=root),
            review_callback=review_callback,
        )

    @staticmethod
    def _bounded(value: Any, depth: int = 0) -> Any:
        if depth > 4:
            return "<bounded>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            text = value[:4000]
            lowered = text.lower()
            if any(marker in lowered for marker in ("api_key=", "authorization: bearer", "password=")):
                return "<redacted-sensitive-output>"
            return text
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in list(value.items())[:60]:
                name = str(key)[:200]
                if any(secret in name.lower() for secret in ("token", "secret", "password", "api_key")):
                    result[name] = "<redacted>"
                else:
                    result[name] = ManagedWorkspaceMissionController._bounded(item, depth + 1)
            return result
        if isinstance(value, (list, tuple)):
            return [ManagedWorkspaceMissionController._bounded(item, depth + 1) for item in list(value)[:100]]
        return str(value)[:1000]

    def _persist_failure_evidence(
        self,
        *,
        mission: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        mission_id = str(mission.get("id") or "").strip()
        if not mission_id:
            return
        status = str(result.get("status") or "").strip().lower()
        if status == "success":
            return

        root = self.data_root / "runtime" / "failure-evidence"
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{mission_id}.json"
        temporary = root / f".{mission_id}.{os.getpid()}.tmp"
        payload = {
            "mission_id": mission_id,
            "status": status,
            "reason": str(result.get("reason") or status)[:2000],
            "provider": str(result.get("provider") or "")[:200],
            "failure_class": str(result.get("failure_class") or status)[:200],
            "request_id": str(result.get("request_id") or "")[:200],
            "task_type": str(result.get("task_type") or "")[:100],
            "runtime_status": str(result.get("runtime_status") or "")[:100],
            "runtime_retryable": bool(result.get("runtime_retryable", False)),
            "runtime_evidence": self._bounded(result.get("runtime_evidence") or {}),
            "attempts_done": int(mission.get("attempts_done", 0)),
            "max_retries": int(mission.get("max_retries", 0)),
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)

    def execute(self, mission: dict[str, Any]) -> dict[str, Any]:
        result = super().execute(mission)
        if not isinstance(result, dict):
            result = {"status": "blocked", "reason": "invalid_controller_result"}

        status = str(result.get("status") or "").lower()
        reason = str(result.get("reason") or "").lower()

        if status == "exhausted" and any(
            marker in reason
            for marker in (
                "managed_openhands_execution_failed",
                "managed_openhands_runtime_unavailable",
                "managed_openhands_process_start_failed",
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
        elif any(
            marker in reason
            for marker in (
                "runtime_incompatible",
                "permission_denied",
                "refuses_canonical_workspace",
                "workspace_unavailable",
            )
        ):
            result["status"] = "exhausted"
            result["failure_class"] = "runtime_integration_defect"
        else:
            result["failure_class"] = str(result.get("failure_class") or status or "unknown")

        try:
            self._persist_failure_evidence(mission=mission, result=result)
        except Exception as exc:
            # Evidence persistence is fail-soft for mission authority, but its
            # failure is still visible in the controller result/checkpoint path.
            result["failure_evidence_error"] = type(exc).__name__

        return result


__all__ = ["ManagedWorkspaceMissionController"]
