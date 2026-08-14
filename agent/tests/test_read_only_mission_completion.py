from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.execution.runtime_adapter import ExecutionEvidence, ExecutionResult, RuntimeStatus
from agent.runtime.workspace_production_mission_controller import (
    WorkspaceProductionMissionController,
)


class _SucceededRouter:
    def execute(self, request, *, require, preferred):
        del request, require, preferred
        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider="openhands",
            evidence=ExecutionEvidence(
                summary="Read-only inspection completed.",
                changed_files=(),
                provider_run_id="run-read-only",
            ),
        )


class ReadOnlyMissionCompletionTests(unittest.TestCase):
    def _controller(self, root: Path, *, task_type: str, objective: str):
        controller = object.__new__(WorkspaceProductionMissionController)
        controller.repository_root = root
        controller.timeout_seconds = 60
        controller.router = _SucceededRouter()
        controller.review_callback = None
        controller._mission_name = lambda mission: "m-read-only"
        controller._read_definition = lambda mission_name: f"## Objective\n{objective}\n"
        controller._mission_metadata = lambda mission_name: {
            "task_type": task_type,
            "request_id": "r-read-only",
        }
        return controller

    def test_successful_inspection_without_changes_completes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = self._controller(
                root,
                task_type="inspection",
                objective="Perform a read-only repository inspection.",
            ).execute({"id": "m-read-only"})

        self.assertEqual("success", result["status"])
        self.assertEqual("read_only_execution_completed", result["reason"])
        self.assertEqual("openhands", result["provider"])
        self.assertEqual([], result["runtime_evidence"]["changed_files"])

    def test_writable_backend_without_changes_still_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = self._controller(
                root,
                task_type="backend",
                objective="Fix the implementation defect.",
            ).execute({"id": "m-read-only"})

        self.assertEqual("blocked", result["status"])
        self.assertEqual("runtime_produced_no_changes", result["reason"])


if __name__ == "__main__":
    unittest.main()
