from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.runtime.production_planner_contract_adapter import (
    ProductionPlannerContractAdapter,
)
from agent.runtime.production_runtime_api import StaticProviderRegistry
from agent.runtime.read_only_inspection_executor import (
    ReadOnlyInspectionExecutor,
)
from agent.runtime.runtime_consolidation_controller import (
    RuntimeConsolidationController,
)


class RuntimeReadOnlyInspectionTests(unittest.TestCase):
    def _repository(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)

        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(root)],
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tests@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "MITIGATE Tests"],
            cwd=root,
            check=True,
        )

        (root / "README.md").write_text(
            "base\n",
            encoding="utf-8",
        )

        subprocess.run(
            ["git", "add", "README.md"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "base"],
            cwd=root,
            check=True,
        )

        return td, root

    def test_static_provider_registry_supports_inspection(self) -> None:
        registry = StaticProviderRegistry(
            project_id="mitigate-ai-platform",
            provider_id="production",
            model_id="production",
        )

        self.assertTrue(
            registry.is_task_supported(
                "mitigate-ai-platform",
                "inspection",
            )
        )

    def test_planner_preserves_inspection_task_type(self) -> None:
        self.assertEqual(
            "inspection",
            ProductionPlannerContractAdapter._normalize_task_type(
                "inspection"
            ),
        )

    def test_inspection_executor_is_read_only(self) -> None:
        td, root = self._repository()

        with td:
            before = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
            )

            executor = ReadOnlyInspectionExecutor(root)

            result = executor.execute(
                "inspection-1",
                {
                    "user_request": "Inspect repository state only.",
                },
            )

            after = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
            )

            self.assertEqual("success", result["status"])
            self.assertEqual(
                "read_only_inspection",
                result["provider"],
            )
            self.assertEqual([], result["changed_files"])
            self.assertTrue(
                result["evidence"]["repository_clean"]
            )
            self.assertEqual(before, after)

    def test_inspection_reports_dirty_repository_without_modifying_it(self) -> None:
        td, root = self._repository()

        with td:
            (root / "untracked.txt").write_text(
                "runtime state\n",
                encoding="utf-8",
            )

            before = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
            )

            executor = ReadOnlyInspectionExecutor(root)
            result = executor.execute(
                "inspection-2",
                {},
            )

            after = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
            )

            self.assertEqual("success", result["status"])
            self.assertFalse(
                result["evidence"]["repository_clean"]
            )
            self.assertEqual(
                1,
                result["evidence"]["dirty_entry_count"],
            )
            self.assertEqual(before, after)

    def test_user_text_is_never_executed_as_shell_command(self) -> None:
        td, root = self._repository()

        with td:
            marker = root / "SHOULD_NOT_EXIST"

            executor = ReadOnlyInspectionExecutor(root)

            result = executor.execute(
                "inspection-3",
                {
                    "user_request": (
                        f"touch {marker}; "
                        f"rm -rf {root / 'anything'}; "
                        "git push origin main"
                    ),
                },
            )

            self.assertEqual("success", result["status"])
            self.assertFalse(marker.exists())

    def test_controller_dispatches_inspection_before_normal_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missions = root / "agent" / "missions"
            missions.mkdir(parents=True)

            mission_id = "inspection-controller-test"

            context = {
                "request_id": "request-1",
                "deliverables": [],
                "user_request": "Read-only inspection.",
            }

            (missions / f"{mission_id}.md").write_text(
                (
                    "# Inspection\n\n"
                    f"Mission ID: {mission_id}\n"
                    "Request ID: request-1\n"
                    "Task Type: inspection\n\n"
                    "## Objective\n\n"
                    "Inspect only.\n\n"
                    "## Deliverables\n\n"
                    "## Context\n\n"
                    "```json\n"
                    f"{json.dumps(context)}\n"
                    "```\n"
                ),
                encoding="utf-8",
            )

            controller = object.__new__(
                RuntimeConsolidationController
            )
            controller.agent_root = root / "agent"
            controller.repository_root = root

            calls = []

            def fake_inspection(mid, ctx):
                calls.append((mid, ctx))
                return {
                    "status": "success",
                    "provider": "read_only_inspection",
                    "changed_files": [],
                }

            controller._execute_read_only_inspection = (
                fake_inspection
            )

            result = controller.execute(
                {
                    "id": mission_id,
                }
            )

            self.assertEqual("success", result["status"])
            self.assertEqual(
                "read_only_inspection",
                result["provider"],
            )
            self.assertEqual(1, len(calls))
            self.assertEqual(mission_id, calls[0][0])


if __name__ == "__main__":
    unittest.main()
