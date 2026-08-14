from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

from agent.execution.openhands_adapter import OpenHandsRuntimeAdapter
from agent.execution.runtime_adapter import (
    ExecutionRequest,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)
from agent.execution.runtime_branch_publisher import RuntimeBranchPublisher
from agent.execution.runtime_router import RuntimeRouter
from agent.execution.workspace_manager import DisposableWorkspaceManager
from agent.runtime.production_mission_controller import ProductionMissionController


class _MissionCompatibleRuntimePublisher(RuntimeBranchPublisher):
    @staticmethod
    def _branch_name(mission_id: str) -> str:
        safe = "".join(
            ch if ch.isalnum() or ch in "-_" else "-"
            for ch in mission_id
        )
        safe = (safe.strip("-") or "mission")[:72]
        return (
            f"agent/mission-{safe}-"
            f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
        )


class WorkspaceProductionMissionController(ProductionMissionController):
    """Production controller using replaceable runtimes in disposable worktrees."""

    def __init__(
        self,
        *,
        repository_root: str | Path | None = None,
        timeout_seconds: int = 1800,
        adapter: Any | None = None,
        workspace_manager: Any | None = None,
        publisher: Any | None = None,
        review_callback: Any | None = None,
    ) -> None:
        super().__init__(repository_root=repository_root, timeout_seconds=timeout_seconds)
        data_root = Path(
            os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")
        ).expanduser().resolve()
        configured_definitions = os.environ.get(
            "MITIGATE_AI_MISSION_DEFINITION_ROOT", ""
        ).strip()
        self.definition_root = (
            Path(configured_definitions).expanduser().resolve()
            if configured_definitions
            else data_root / "runtime" / "mission-definitions"
        )
        self.workspace_manager = workspace_manager or DisposableWorkspaceManager(
            self.repository_root,
            workspace_parent=data_root / "runtime" / "workspaces",
        )
        self.adapter = adapter or OpenHandsRuntimeAdapter()
        self.publisher = publisher or _MissionCompatibleRuntimePublisher(self.repository_root)
        self.router = RuntimeRouter(
            RuntimeRegistry([self.adapter]),
            self.workspace_manager,
            publisher=self.publisher,
        )
        self.review_callback = review_callback

    def _definition_path(self, mission_name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", mission_name):
            raise ValueError("invalid_mission_name")
        return (self.definition_root / f"{mission_name}.md").resolve()

    def _read_definition(self, mission_name: str) -> str:
        path = self._definition_path(mission_name)
        if self.definition_root.resolve() not in path.parents:
            raise ValueError("mission_definition_path_escape")
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("mission_definition_not_found") from exc
        if not text:
            raise ValueError("mission_definition_empty")
        return text

    @staticmethod
    def _context(text: str) -> Mapping[str, Any]:
        match = re.search(
            r"## Context\s*\n\s*```json\s*\n(.*?)\n```", text, re.DOTALL
        )
        if not match:
            return {}
        try:
            value = json.loads(match.group(1))
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _field(text: str, label: str) -> str:
        match = re.search(
            rf"^{re.escape(label)}:\s*(.+?)\s*$", text, re.MULTILINE
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _objective(text: str) -> str:
        match = re.search(
            r"## Objective\s*\n\s*(.*?)(?=\n## |\Z)", text, re.DOTALL
        )
        return match.group(1).strip() if match else text[:12000]

    def _mission_metadata(self, mission_name: str) -> dict[str, Any]:
        try:
            text = self._read_definition(mission_name)
        except ValueError:
            return super()._mission_metadata(mission_name)
        metadata: dict[str, Any] = {}
        task_type = self._field(text, "Task Type")
        request_id = self._field(text, "Request ID")
        if task_type:
            metadata["task_type"] = task_type
        if request_id:
            metadata["request_id"] = request_id
        return metadata

    @staticmethod
    def _default_allowed_paths(task_type: str, objective: str) -> tuple[str, ...]:
        if task_type == "documentation" or any(
            marker in objective.lower()
            for marker in ("architecture assessment", "build-vs-adopt assessment", "assessment document")
        ):
            return ("docs", "README.md")
        if task_type == "github":
            return (".github", "agent", "docs")
        if task_type in {"infrastructure", "deployment"}:
            return ("agent", ".github", "docs")
        return ("agent",)

    @staticmethod
    def _runtime_evidence(result: Any) -> dict[str, Any]:
        evidence = result.evidence
        return {
            "summary": str(evidence.summary or "")[:2000],
            "diagnostics": list(evidence.diagnostics)[:50],
            "tests_run": list(evidence.tests_run)[:50],
            "test_results": list(evidence.test_results)[:50],
            "changed_files": list(evidence.changed_files)[:200],
            "provider_run_id": evidence.provider_run_id,
            "provider_metadata": dict(evidence.provider_metadata or {}),
        }

    def execute(self, mission: dict[str, Any]) -> dict[str, Any]:
        try:
            mission_name = self._mission_name(mission)
            text = self._read_definition(mission_name)
        except ValueError as exc:
            return {"status": "blocked", "reason": str(exc)}

        metadata = self._mission_metadata(mission_name)
        context = dict(self._context(text))
        objective = self._objective(text)
        deliverables_raw = context.get("deliverables", [])
        deliverables = tuple(
            str(item).strip()
            for item in deliverables_raw
            if isinstance(item, str) and str(item).strip()
        ) if isinstance(deliverables_raw, list) else ()

        task_type = str(metadata.get("task_type") or "backend").lower()
        software_task = task_type in {
            "backend", "frontend", "api", "testing", "documentation",
            "infrastructure", "security", "database", "fullstack",
            "bugfix", "maintenance", "refactor", "test", "tests", "github",
            "deployment",
        }
        allowed_paths = deliverables
        if software_task and not allowed_paths:
            allowed_paths = self._default_allowed_paths(task_type, objective)

        request_id = str(
            metadata.get("request_id") or context.get("request_id") or mission_name
        ).strip()
        request = ExecutionRequest(
            request_id=request_id,
            mission_id=mission_name,
            objective=objective,
            repository_root=str(self.repository_root),
            base_revision="main",
            allowed_paths=allowed_paths,
            denied_paths=(".git", ".env", "secrets"),
            acceptance_criteria=(
                "Inspect the existing repository before modifying files.",
                "Implement the smallest architecture-consistent fix.",
                "Run relevant automated tests and validation.",
                "Do not commit, push or merge from the external runtime.",
            ),
            timeout_seconds=self.timeout_seconds,
            metadata={
                "task_type": task_type,
                "model": os.environ.get("MITIGATE_OPENHANDS_MODEL", "gpt-5.5"),
            },
        )

        result = self.router.execute(
            request,
            require=RuntimeCapabilities(
                coding=True,
                terminal=True,
                file_editing=True,
                tests=True,
                isolated_workspace=True,
            ),
            preferred=("openhands",),
        )
        runtime_evidence = self._runtime_evidence(result)

        if result.status == RuntimeStatus.succeeded:
            if not result.evidence.changed_files:
                return {
                    "status": "blocked",
                    "reason": "runtime_produced_no_changes",
                    "provider": result.provider,
                    "request_id": request_id,
                    "task_type": task_type,
                    "runtime_evidence": runtime_evidence,
                }
            review = (
                self.review_callback(mission_name)
                if self.review_callback is not None
                else self._review_and_merge(mission_name)
            )
            review["provider"] = result.provider
            review["runtime_branch"] = result.evidence.branch
            review["runtime_commit"] = result.evidence.commit_sha
            review["request_id"] = request_id
            review["task_type"] = task_type
            review["runtime_evidence"] = runtime_evidence
            return review

        if result.status == RuntimeStatus.blocked:
            status = "blocked"
        elif result.status == RuntimeStatus.unavailable:
            status = "retry"
        elif result.retryable:
            status = "retry"
        else:
            status = "exhausted"

        return {
            "status": status,
            "reason": result.reason or result.status.value,
            "provider": result.provider,
            "request_id": request_id,
            "task_type": task_type,
            "runtime_status": result.status.value,
            "runtime_retryable": bool(result.retryable),
            "runtime_evidence": runtime_evidence,
        }


__all__ = ["WorkspaceProductionMissionController"]
