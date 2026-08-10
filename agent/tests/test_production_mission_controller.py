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

    @patch(
        "agent.runtime.production_mission_controller.GitReviewEngine.review"
    )
    @patch(
        "agent.runtime.production_mission_controller.subprocess.run"
    )
    def test_success_maps_to_success_and_restores_main(
        self,
        run_mock,
        review_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(root)

            branch = (
                "agent/mission-runtime-smoke-"
                "20260810-190002"
            )

            original_head = "a" * 40

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
                subprocess.CompletedProcess(
                    ["git", "for-each-ref"],
                    0,
                    stdout=f"{branch}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse", "HEAD"],
                    0,
                    stdout=f"{original_head}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "merge"],
                    0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "push"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            review_mock.return_value = {
                "validation": {
                    "ok": True,
                    "errors": [],
                },
                "risk_level": "low",
                "merge_recommendation": "approve",
            }

            result = controller.execute(
                {"id": "runtime_smoke"}
            )

            self.assertEqual(
                "success",
                result["status"],
            )
            self.assertTrue(
                result["merged_to_main"]
            )
            self.assertEqual(
                6,
                run_mock.call_count,
            )

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

            self.assertEqual(
                [
                    "git",
                    "merge",
                    "--ff-only",
                    branch,
                ],
                run_mock.call_args_list[4].args[0],
            )

            self.assertEqual(
                [
                    "git",
                    "push",
                    "origin",
                    "main",
                ],
                run_mock.call_args_list[5].args[0],
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


    @patch(
        "agent.runtime.production_mission_controller.GitReviewEngine.review"
    )
    @patch(
        "agent.runtime.production_mission_controller.subprocess.run"
    )
    def test_push_failure_rolls_back_local_main(
        self,
        run_mock,
        review_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(root)

            branch = (
                "agent/mission-safe-mission-"
                "20260810-190003"
            )

            original_head = "a" * 40

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    0,
                    stdout="MISSION COMPLETED",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "switch", "main"],
                    0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "for-each-ref"],
                    0,
                    stdout=f"{branch}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse", "HEAD"],
                    0,
                    stdout=f"{original_head}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "merge"],
                    0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "push"],
                    1,
                    stdout="",
                    stderr="push rejected",
                ),
                subprocess.CompletedProcess(
                    ["git", "reset"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            review_mock.return_value = {
                "validation": {
                    "ok": True,
                    "errors": [],
                },
                "risk_level": "low",
                "merge_recommendation": "approve",
            }

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual(
                "blocked",
                result["status"],
            )
            self.assertEqual(
                "main_push_failed",
                result["reason"],
            )
            self.assertTrue(
                result["local_main_rolled_back"]
            )

            commands = [
                call.args[0]
                for call in run_mock.call_args_list
            ]

            self.assertIn(
                [
                    "git",
                    "reset",
                    "--hard",
                    original_head,
                ],
                commands,
            )


if __name__ == "__main__":
    unittest.main()


class ProductionMissionControllerAutoMergeTests(unittest.TestCase):

    def build_controller(self, root: Path) -> ProductionMissionController:
        (root / "agent").mkdir(parents=True, exist_ok=True)

        return ProductionMissionController(
            repository_root=root,
            timeout_seconds=30,
        )

    @patch(
        "agent.runtime.production_mission_controller.GitReviewEngine.review"
    )
    @patch(
        "agent.runtime.production_mission_controller.subprocess.run"
    )
    def test_low_risk_success_fast_forwards_and_pushes_main(
        self,
        run_mock,
        review_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(root)

            branch = (
                "agent/mission-safe-mission-"
                "20260810-190000"
            )

            original_head = "a" * 40

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    0,
                    stdout="MISSION COMPLETED",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "switch", "main"],
                    0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "for-each-ref"],
                    0,
                    stdout=f"{branch}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "rev-parse", "HEAD"],
                    0,
                    stdout=f"{original_head}\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "merge"],
                    0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "push"],
                    0,
                    stdout="",
                    stderr="",
                ),
            ]

            review_mock.return_value = {
                "validation": {
                    "ok": True,
                    "errors": [],
                },
                "risk_level": "low",
                "merge_recommendation": "approve",
            }

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual(
                "success",
                result["status"],
            )
            self.assertTrue(
                result["merged_to_main"]
            )
            self.assertEqual(
                "low",
                result["risk_level"],
            )

            commands = [
                call.args[0]
                for call in run_mock.call_args_list
            ]

            self.assertIn(
                [
                    "git",
                    "merge",
                    "--ff-only",
                    branch,
                ],
                commands,
            )

            self.assertIn(
                [
                    "git",
                    "push",
                    "origin",
                    "main",
                ],
                commands,
            )

    @patch(
        "agent.runtime.production_mission_controller.GitReviewEngine.review"
    )
    @patch(
        "agent.runtime.production_mission_controller.subprocess.run"
    )
    def test_medium_risk_requires_manual_review(
        self,
        run_mock,
        review_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(root)

            branch = (
                "agent/mission-safe-mission-"
                "20260810-190001"
            )

            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["python"],
                    0,
                    stdout="MISSION COMPLETED",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "switch", "main"],
                    0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    ["git", "for-each-ref"],
                    0,
                    stdout=f"{branch}\n",
                    stderr="",
                ),
            ]

            review_mock.return_value = {
                "validation": {
                    "ok": True,
                    "errors": [],
                },
                "risk_level": "medium",
                "merge_recommendation": "manual_review",
            }

            result = controller.execute(
                {"id": "safe_mission"}
            )

            self.assertEqual(
                "blocked",
                result["status"],
            )
            self.assertEqual(
                "manual_review_required",
                result["reason"],
            )

            commands = [
                call.args[0]
                for call in run_mock.call_args_list
            ]

            self.assertFalse(
                any(
                    command[:2] == ["git", "merge"]
                    for command in commands
                )
            )

            self.assertFalse(
                any(
                    command[:2] == ["git", "push"]
                    for command in commands
                )
            )
