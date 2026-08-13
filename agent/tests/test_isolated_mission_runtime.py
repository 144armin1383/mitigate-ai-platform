from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeStatus,
)
from agent.runtime.isolated_request_queue_adapter import (
    IsolatedProductionRequestQueueAdapter,
)
from agent.runtime.workspace_production_mission_controller import (
    WorkspaceProductionMissionController,
)


class _FakeOpenHands:
    name = "openhands"

    def __init__(self) -> None:
        self.workspace_root = ""

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            coding=True,
            terminal=True,
            file_editing=True,
            tests=True,
            isolated_workspace=True,
        )

    def healthcheck(self):
        return {"available": True}

    def execute(self, request):
        self.workspace_root = str(request.metadata["workspace_root"])
        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider="openhands",
            evidence=ExecutionEvidence(
                changed_files=(),
            ),
        )

    def cancel(self, provider_run_id: str) -> bool:
        return False


class IsolatedMissionRuntimeTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _repo(self, root: Path) -> None:
        self._git(root, "init", "-b", "main")
        self._git(root, "config", "user.email", "test@example.invalid")
        self._git(root, "config", "user.name", "MITIGATE Test")
        (root / "agent" / "missions").mkdir(parents=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        self._git(root, "add", "README.md")
        self._git(root, "commit", "-m", "base")

    def _mission(self, mission_id: str, request_id: str = "req-1"):
        return {
            "mission_id": mission_id,
            "project_id": "project",
            "request_id": request_id,
            "title": "Fix runtime lifecycle",
            "description": "Fix the isolated mission runtime lifecycle.",
            "task_type": "backend",
            "priority": 2,
            "dependencies": [],
            "payload": {
                "deliverables": ["agent/runtime/example.py"],
            },
        }

    def test_enqueue_keeps_canonical_checkout_clean(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            self._repo(root)
            queue = Path(td) / "data" / "missions.json"

            adapter = IsolatedProductionRequestQueueAdapter(
                project_id="project",
                queue_path=queue,
                repository_root=root,
            )
            adapter.enqueue_batch([self._mission("m100")])

            self.assertEqual(
                self._git(root, "status", "--porcelain", "--untracked-files=all"),
                "",
            )
            self.assertFalse((root / "agent/missions/m100.md").exists())
            self.assertTrue((Path(td) / "data/mission-definitions/m100.md").is_file())

    def test_legacy_migration_preserves_unrelated_untracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            self._repo(root)
            queue = Path(td) / "data" / "missions.json"

            first = IsolatedProductionRequestQueueAdapter(
                project_id="project",
                queue_path=queue,
                repository_root=root,
            )
            first.queue.enqueue("m200", 2, [], max_retries=0)

            legacy = root / "agent/missions/m200.md"
            legacy.write_text("legacy generated mission\n", encoding="utf-8")
            unrelated = root / "operator-note.txt"
            unrelated.write_text("preserve me\n", encoding="utf-8")

            second = IsolatedProductionRequestQueueAdapter(
                project_id="project",
                queue_path=queue,
                repository_root=root,
            )

            self.assertFalse(legacy.exists())
            self.assertTrue(unrelated.is_file())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve me\n")
            self.assertEqual(
                second._definition_path("m200").read_text(encoding="utf-8"),
                "legacy generated mission\n",
            )
            status = self._git(root, "status", "--porcelain", "--untracked-files=all")
            self.assertIn("?? operator-note.txt", status)
            self.assertNotIn("agent/missions/m200.md", status)

    def test_runtime_router_gives_provider_disposable_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            self._repo(root)
            data = Path(td) / "data"
            definitions = data / "runtime" / "mission-definitions"
            definitions.mkdir(parents=True)
            mission_id = "m300"
            (definitions / f"{mission_id}.md").write_text(
                "# Workspace test\n\n"
                f"Mission ID: {mission_id}\n"
                "Request ID: req-300\n"
                "Task Type: backend\n\n"
                "## Objective\n\nInspect safely.\n\n"
                "## Deliverables\n\n- agent/runtime/example.py\n\n"
                "## Context\n\n```json\n"
                '{"deliverables":["agent/runtime/example.py"]}'
                "\n```\n",
                encoding="utf-8",
            )

            fake = _FakeOpenHands()
            old_data = os.environ.get("MITIGATE_AI_DATA_ROOT")
            old_defs = os.environ.get("MITIGATE_AI_MISSION_DEFINITION_ROOT")
            os.environ["MITIGATE_AI_DATA_ROOT"] = str(data)
            os.environ["MITIGATE_AI_MISSION_DEFINITION_ROOT"] = str(definitions)
            try:
                controller = WorkspaceProductionMissionController(
                    repository_root=root,
                    adapter=fake,
                )
                result = controller.execute({"id": mission_id})
            finally:
                if old_data is None:
                    os.environ.pop("MITIGATE_AI_DATA_ROOT", None)
                else:
                    os.environ["MITIGATE_AI_DATA_ROOT"] = old_data
                if old_defs is None:
                    os.environ.pop("MITIGATE_AI_MISSION_DEFINITION_ROOT", None)
                else:
                    os.environ["MITIGATE_AI_MISSION_DEFINITION_ROOT"] = old_defs

            # Fake provider intentionally produced no changes, so governance
            # blocks publication, but it must still have received an isolated
            # worktree that is cleaned after execution.
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], "runtime_produced_no_changes")
            self.assertTrue(fake.workspace_root)
            self.assertNotEqual(Path(fake.workspace_root).resolve(), root.resolve())
            self.assertFalse(Path(fake.workspace_root).exists())
            self.assertEqual(
                self._git(root, "status", "--porcelain", "--untracked-files=all"),
                "",
            )


if __name__ == "__main__":
    unittest.main()
