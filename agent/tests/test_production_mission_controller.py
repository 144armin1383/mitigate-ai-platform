from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.runtime.production_mission_controller import (
    ProductionMissionController,
)


class ProductionMissionControllerTests(unittest.TestCase):

    def build_controller(self, root: Path) -> ProductionMissionController:
        (root / "agent").mkdir(parents=True, exist_ok=True)

        return ProductionMissionController(
            repository_root=root,
            timeout_seconds=30,
        )

    def test_invalid_mission_name_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            controller = self.build_controller(Path(td))

            result = controller.execute(
                {"id": "../unsafe"}
            )

            self.assertEqual("blocked", result["status"])
            self.assertEqual(
                "invalid_mission_name",
                result["reason"],
            )

    @patch("agent.runtime.production_mission_controller.subprocess.run")
    def test_success_maps_to_success_and_restores_main(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(root)

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    0,
                    stdout="MISSION COMPLETED",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            result = controller.execute(
                {"id": "runtime_smoke"}
            )

            self.assertEqual("success", result["status"])
            self.assertEqual(2, run_mock.call_count)

            first = run_mock.call_args_list[0]
            self.assertIn(
                "ai.mission_runner",
                first.args[0],
            )
            self.assertEqual(
                root / "agent",
                first.kwargs["cwd"],
            )

            second = run_mock.call_args_list[1]
            self.assertEqual(
                ["git", "switch", "main"],
                second.args[0],
            )

    @patch("agent.runtime.production_mission_controller.subprocess.run")
    def test_self_healing_block_maps_to_blocked(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            controller = self.build_controller(Path(td))

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    1,
                    stdout="",
                    stderr="MissionError: SELF_HEALING_BLOCKED",
                ),
                subprocess.CompletedProcess(
                    ["git"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual("blocked", result["status"])
            self.assertEqual(
                "self_healing_blocked",
                result["reason"],
            )

    @patch("agent.runtime.production_mission_controller.subprocess.run")
    def test_general_failure_maps_to_exhausted(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            controller = self.build_controller(Path(td))

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    1,
                    stdout="",
                    stderr="generation failed",
                ),
                subprocess.CompletedProcess(
                    ["git"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual(
                "exhausted",
                result["status"],
            )

    @patch("agent.runtime.production_mission_controller.subprocess.run")
    def test_restore_failure_blocks_runtime(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            controller = self.build_controller(Path(td))

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    0,
                    stdout="MISSION COMPLETED",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git"],
                    1,
                    stdout="",
                    stderr="restore failed",
                ),
            ]

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual("blocked", result["status"])
            self.assertEqual(
                "repository_restore_failed",
                result["reason"],
            )

    @patch("agent.runtime.production_mission_controller.subprocess.run")
    def test_timeout_maps_to_exhausted_and_restores_main(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            controller = self.build_controller(Path(td))

            run_mock.side_effect = [
                subprocess.TimeoutExpired(
                    cmd=["python"],
                    timeout=30,
                ),
                subprocess.CompletedProcess(
                    ["git"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual(
                "exhausted",
                result["status"],
            )
            self.assertEqual(
                "mission_timeout",
                result["reason"],
            )


if __name__ == "__main__":
    unittest.main()
