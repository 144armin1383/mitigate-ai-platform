from __future__ import annotations

import json
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
                subprocess.CompletedProcess(
                    ["git", "rev-parse", branch],
                    0,
                    stdout=f"{'b' * 40}\n",
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
                7,
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
                subprocess.CompletedProcess(
                    ["git", "rev-parse", branch],
                    0,
                    stdout=f"{'b' * 40}\n",
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


class ProductionMissionControllerReportingContractTests(unittest.TestCase):

    def build_controller(
        self,
        root: Path,
    ) -> ProductionMissionController:
        (root / "agent").mkdir(
            parents=True,
            exist_ok=True,
        )

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
    def test_success_returns_execution_report_metadata(
        self,
        run_mock,
        review_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(root)

            missions_root = root / "agent" / "missions"
            missions_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            mission_name = "report_contract"

            mission_definition = (
                "# Reporting Contract\n\n"
                "Mission ID: report_contract\n"
                "Task Type: documentation\n\n"
                "## Objective\n\n"
                "Test reporting metadata.\n\n"
                "## Deliverables\n\n"
                "- docs/runtime/REPORT_CONTRACT.md\n\n"
                "## Context\n\n"
                "```json\n"
                "{\n"
                '  "project_id": "mitigate-ai-platform",\n'
                '  "request_id": "req-report-contract-001"\n'
                "}\n"
                "```\n"
            )

            (
                missions_root
                / f"{mission_name}.md"
            ).write_text(
                mission_definition,
                encoding="utf-8",
            )

            branch = (
                "agent/mission-report-contract-"
                "20260811-090500"
            )

            original_head = "a" * 40
            mission_commit = "b" * 40

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
                subprocess.CompletedProcess(
                    ["git", "rev-parse", branch],
                    0,
                    stdout=f"{mission_commit}\n",
                    stderr="",
                ),
            ]

            review_mock.return_value = {
                "validation": {
                    "ok": True,
                    "errors": [],
                },
                "files": {
                    "added": [
                        {
                            "path": (
                                "agent/missions/"
                                "report_contract.md"
                            ),
                            "status": "A",
                            "insertions": 12,
                            "deletions": 0,
                        },
                        {
                            "path": (
                                "docs/runtime/"
                                "REPORT_CONTRACT.md"
                            ),
                            "status": "A",
                            "insertions": 8,
                            "deletions": 0,
                        },
                    ],
                    "modified": [],
                    "deleted": [],
                    "renamed": [],
                },
                "risk_level": "low",
                "merge_recommendation": "approve",
            }

            result = controller.execute(
                {"id": mission_name}
            )

            self.assertEqual(
                "success",
                result["status"],
            )
            self.assertEqual(
                "req-report-contract-001",
                result["request_id"],
            )
            self.assertEqual(
                "documentation",
                result["task_type"],
            )
            self.assertEqual(
                [
                    "docs/runtime/"
                    "REPORT_CONTRACT.md"
                ],
                result["changed_files"],
            )

            self.assertEqual(
                [
                    "agent/missions/"
                    "report_contract.md"
                ],
                result["internal_files"],
            )
            self.assertEqual(
                branch,
                result["branch"],
            )
            self.assertEqual(
                mission_commit,
                result["git_commit"],
            )
            self.assertEqual(
                "low",
                result["risk_level"],
            )
            self.assertEqual(
                "approve",
                result["merge_recommendation"],
            )
            self.assertTrue(
                result["merged_to_main"]
            )


class ProductionMissionControllerTechnologyEvaluationAutoMergeContractTests(
    unittest.TestCase
):

    def build_controller(
        self,
        root: Path,
    ) -> ProductionMissionController:
        (root / "agent" / "missions").mkdir(
            parents=True,
            exist_ok=True,
        )

        return ProductionMissionController(
            repository_root=root,
            timeout_seconds=30,
        )

    def write_mission(
        self,
        root: Path,
        mission_name: str,
        *,
        task_type: str = "technology_evaluation",
        deliverable: str = (
            "docs/technology/evaluations/"
            "ruflo/3.37.0.json"
        ),
    ) -> None:
        content = (
            "# Evaluate technology ruflo\n\n"
            f"Mission ID: {mission_name}\n"
            f"Task Type: {task_type}\n\n"
            "## Context\n\n"
            "```json\n"
            + json.dumps(
                {
                    "deliverables": [
                        deliverable
                    ]
                }
            )
            + "\n```\n"
        )

        (
            root
            / "agent"
            / "missions"
            / f"{mission_name}.md"
        ).write_text(
            content,
            encoding="utf-8",
        )

    @staticmethod
    def medium_review(
        deliverable: str = (
            "docs/technology/evaluations/"
            "ruflo/3.37.0.json"
        ),
    ):
        return {
            "validation": {
                "ok": True,
                "errors": [],
            },
            "risk_level": "medium",
            "merge_recommendation": "manual_review",
            "files": {
                "added": [
                    {
                        "path": deliverable,
                    }
                ],
                "modified": [],
                "deleted": [],
                "renamed": [],
            },
            "categories": {
                "findings": [],
                "high_risk_files": [],
            },
        }

    def test_medium_technology_evaluation_artifact_is_allowed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(
                root
            )

            mission_name = (
                "technology-evaluation-test"
            )

            self.write_mission(
                root,
                mission_name,
            )

            allowed = (
                controller
                ._technology_evaluation_medium_risk_allowed(
                    mission_name=mission_name,
                    review=self.medium_review(),
                )
            )

            self.assertTrue(
                allowed
            )

    def test_general_medium_mission_remains_blocked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(
                root
            )

            mission_name = "general-test"

            self.write_mission(
                root,
                mission_name,
                task_type="general",
            )

            allowed = (
                controller
                ._technology_evaluation_medium_risk_allowed(
                    mission_name=mission_name,
                    review=self.medium_review(),
                )
            )

            self.assertFalse(
                allowed
            )

    def test_unexpected_changed_file_is_blocked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(
                root
            )

            mission_name = (
                "technology-evaluation-test"
            )

            self.write_mission(
                root,
                mission_name,
            )

            review = self.medium_review()

            review["files"]["modified"].append(
                {
                    "path":
                    "agent/runtime/background_worker.py"
                }
            )

            allowed = (
                controller
                ._technology_evaluation_medium_risk_allowed(
                    mission_name=mission_name,
                    review=review,
                )
            )

            self.assertFalse(
                allowed
            )

    def test_high_risk_finding_is_blocked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(
                root
            )

            mission_name = (
                "technology-evaluation-test"
            )

            self.write_mission(
                root,
                mission_name,
            )

            review = self.medium_review()

            review["categories"]["findings"] = [
                "Dependency manifest changed"
            ]

            allowed = (
                controller
                ._technology_evaluation_medium_risk_allowed(
                    mission_name=mission_name,
                    review=review,
                )
            )

            self.assertFalse(
                allowed
            )

    def test_multiple_deliverables_are_blocked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            controller = self.build_controller(
                root
            )

            mission_name = (
                "technology-evaluation-test"
            )

            mission_path = (
                root
                / "agent"
                / "missions"
                / f"{mission_name}.md"
            )

            mission_path.write_text(
                (
                    "# Evaluation\n\n"
                    f"Mission ID: {mission_name}\n"
                    "Task Type: technology_evaluation\n\n"
                    "## Context\n\n"
                    "```json\n"
                    + json.dumps(
                        {
                            "deliverables": [
                                (
                                    "docs/technology/"
                                    "evaluations/ruflo/"
                                    "3.37.0.json"
                                ),
                                "README.md",
                            ]
                        }
                    )
                    + "\n```\n"
                ),
                encoding="utf-8",
            )

            allowed = (
                controller
                ._technology_evaluation_medium_risk_allowed(
                    mission_name=mission_name,
                    review=self.medium_review(),
                )
            )

            self.assertFalse(
                allowed
            )
