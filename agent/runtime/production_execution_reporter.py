from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from agent.execution.execution_report_writer import (
    ExecutionReportWriter,
)


class ProductionExecutionReporter:
    """
    Thin production adapter over ExecutionReportWriter.

    Mission queue state remains owned by BackgroundWorker/MissionQueue.
    This adapter has no mission transition or execution authority.
    """

    def __init__(
        self,
        *,
        storage_dir: str | Path,
        project_id: str,
    ) -> None:
        normalized_project_id = str(project_id).strip()

        if not normalized_project_id:
            raise ValueError("invalid_project_id")

        self.project_id = normalized_project_id
        self.storage_dir = Path(storage_dir).resolve()

        self._writer = ExecutionReportWriter(
            storage_dir=str(self.storage_dir),
            project_resolver=self._resolve_project,
        )

    def _resolve_project(
        self,
        project_id: str,
    ) -> Optional[str]:
        candidate = str(project_id).strip()

        if candidate == self.project_id:
            return self.project_id

        return None

    @staticmethod
    def _require_utc(
        value: datetime,
        field_name: str,
    ) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError(
                f"{field_name} must be datetime"
            )

        if value.tzinfo is None:
            raise ValueError(
                f"{field_name} must be timezone-aware"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _status_flags(
        status: str,
    ) -> tuple[bool, bool]:
        normalized = str(status).strip().lower()

        if normalized == "completed":
            return True, False

        if normalized == "retrying":
            return False, True

        if normalized in {
            "failed",
            "blocked",
            "cancelled",
        }:
            return False, False

        raise ValueError("unsupported_status")

    def persist(
        self,
        *,
        execution_id: str,
        mission_id: str,
        request_id: str,
        started_at: datetime,
        completed_at: datetime,
        status: str,
        task_type: Optional[str] = None,
        worker_id: Optional[str] = None,
        changed_files: Sequence[str] = (),
        git_branch: Optional[str] = None,
        git_commit: Optional[str] = None,
        validation_status: Optional[str] = None,
        safe_error_code: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        started = self._require_utc(
            started_at,
            "started_at",
        )
        completed = self._require_utc(
            completed_at,
            "completed_at",
        )

        if completed < started:
            raise ValueError(
                "completed_at_before_started_at"
            )

        success, retryable = self._status_flags(
            status
        )

        report: dict[str, Any] = {
            "execution_id": str(execution_id).strip(),
            "project_id": self.project_id,
            "request_id": str(request_id).strip(),
            "mission_id": str(mission_id).strip(),
            "started_at": started,
            "completed_at": completed,
            "status": str(status).strip().lower(),
            "success": success,
            "retryable": retryable,
            "fallback_used": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": None,
            "changed_files": list(changed_files),
            "metadata": dict(metadata or {}),
        }

        optional_values = {
            "task_type": task_type,
            "worker_id": worker_id,
            "git_branch": git_branch,
            "git_commit": git_commit,
            "validation_status": validation_status,
            "safe_error_code": safe_error_code,
            "summary": summary,
        }

        for key, value in optional_values.items():
            if value is None:
                continue

            normalized = str(value).strip()

            if normalized:
                report[key] = normalized

        stored = self._writer.store_report(report)

        if not isinstance(stored, dict):
            raise RuntimeError(
                "execution_report_persistence_failed"
            )

        return stored

    def persist_result(
        self,
        *,
        mission: Mapping[str, Any],
        controller_result: Mapping[str, Any],
        worker_id: str,
        final_status: str,
    ) -> dict[str, Any]:
        mission_id = str(
            mission.get("id") or ""
        ).strip()

        if not mission_id:
            raise ValueError("invalid_mission_id")

        request_id = str(
            controller_result.get("request_id")
            or mission.get("request_id")
            or mission_id
        ).strip()

        now = datetime.now(timezone.utc)

        branch = controller_result.get("branch")
        commit = controller_result.get("git_commit")

        changed_files = controller_result.get(
            "changed_files",
            [],
        )

        if not isinstance(changed_files, list):
            changed_files = []

        internal_files = controller_result.get(
            "internal_files",
            [],
        )

        if not isinstance(internal_files, list):
            internal_files = []

        metadata = {
            "risk_level": controller_result.get(
                "risk_level"
            ),
            "merge_recommendation": (
                controller_result.get(
                    "merge_recommendation"
                )
            ),
            "merged_to_main": bool(
                controller_result.get(
                    "merged_to_main",
                    False,
                )
            ),
            "reason": controller_result.get(
                "reason"
            ),
            "internal_files": internal_files,
        }

        return self.persist(
            execution_id=(
                f"exec-{mission_id}-"
                f"{int(now.timestamp())}"
            ),
            mission_id=mission_id,
            request_id=request_id,
            started_at=now,
            completed_at=now,
            status=final_status,
            task_type=controller_result.get(
                "task_type"
            ),
            worker_id=worker_id,
            changed_files=changed_files,
            git_branch=(
                str(branch)
                if branch
                else None
            ),
            git_commit=(
                str(commit)
                if commit
                else None
            ),
            validation_status=(
                "validated"
                if controller_result.get(
                    "merged_to_main"
                )
                else None
            ),
            safe_error_code=(
                str(
                    controller_result.get(
                        "reason"
                    )
                )
                if controller_result.get(
                    "reason"
                )
                else None
            ),
            metadata=metadata,
        )

    def get_report(
        self,
        execution_id: str,
    ) -> dict[str, Any]:
        return self._writer.get_report(
            execution_id
        )

    def find_by_mission_id(
        self,
        mission_id: str,
    ) -> Optional[dict[str, Any]]:
        candidate = str(mission_id).strip()

        if not candidate:
            raise ValueError("invalid_mission_id")

        reports_dir = (
            self.storage_dir
            / "reports"
            / "by-execution"
        )

        if not reports_dir.exists():
            return None

        matches: list[dict[str, Any]] = []

        for path in sorted(
            reports_dir.glob("*.json")
        ):
            try:
                import json

                report = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                continue

            if not isinstance(report, dict):
                continue

            if (
                report.get("project_id")
                == self.project_id
                and report.get("mission_id")
                == candidate
            ):
                matches.append(report)

        if not matches:
            return None

        matches.sort(
            key=lambda item: (
                str(
                    item.get(
                        "completed_at",
                        "",
                    )
                ),
                str(
                    item.get(
                        "execution_id",
                        "",
                    )
                ),
            ),
            reverse=True,
        )

        return matches[0]

    def find_by_request_id(
        self,
        request_id: str,
    ) -> list[dict[str, Any]]:
        candidate = str(request_id).strip()

        if not candidate:
            raise ValueError("invalid_request_id")

        reports_dir = (
            self.storage_dir
            / "reports"
            / "by-execution"
        )

        if not reports_dir.exists():
            return []

        reports: list[dict[str, Any]] = []

        for path in sorted(
            reports_dir.glob("*.json")
        ):
            try:
                import json

                report = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                continue

            if not isinstance(report, dict):
                continue

            if (
                report.get("project_id")
                == self.project_id
                and report.get("request_id")
                == candidate
            ):
                reports.append(report)

        reports.sort(
            key=lambda item: (
                str(
                    item.get(
                        "completed_at",
                        "",
                    )
                ),
                str(
                    item.get(
                        "execution_id",
                        "",
                    )
                ),
            ),
            reverse=True,
        )

        return reports

    def list_reports(
        self,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > 100
        ):
            raise ValueError("invalid_limit")

        reports_dir = (
            self.storage_dir
            / "reports"
            / "by-execution"
        )

        if not reports_dir.exists():
            return []

        reports: list[dict[str, Any]] = []

        for path in reports_dir.glob("*.json"):
            try:
                import json

                report = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                continue

            if not isinstance(report, dict):
                continue

            if (
                report.get("project_id")
                != self.project_id
            ):
                continue

            reports.append(report)

        reports.sort(
            key=lambda item: (
                str(
                    item.get(
                        "completed_at",
                        "",
                    )
                ),
                str(
                    item.get(
                        "execution_id",
                        "",
                    )
                ),
            ),
            reverse=True,
        )

        return reports[:limit]

    def status(self) -> dict[str, Any]:
        return self._writer.status(
            project_id=self.project_id
        )


__all__ = [
    "ProductionExecutionReporter",
]
