from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_ROOT = Path(__file__).resolve().parents[1]

if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import ai.mission_runner as mr


class MissionRunnerProductionContractTests(unittest.TestCase):

    def _status_result(
        self,
        output: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            ["git", "status"],
            0,
            stdout=output,
            stderr="",
        )

    @patch("ai.mission_runner.run_git")
    def test_current_runtime_mission_definition_is_allowed(
        self,
        run_git_mock,
    ) -> None:
        mission_path = (
            mr.REPOSITORY_ROOT
            / "agent"
            / "missions"
            / "runtime-current.md"
        )

        run_git_mock.return_value = self._status_result(
            "?? agent/missions/runtime-current.md\n"
        )

        mr.require_clean_repository(
            allowed_untracked_path=mission_path,
        )

    @patch("ai.mission_runner.run_git")
    def test_current_mission_plus_dirty_file_is_blocked(
        self,
        run_git_mock,
    ) -> None:
        mission_path = (
            mr.REPOSITORY_ROOT
            / "agent"
            / "missions"
            / "runtime-current.md"
        )

        run_git_mock.return_value = self._status_result(
            "?? agent/missions/runtime-current.md\n"
            " M agent/runtime/background_worker.py\n"
        )

        with self.assertRaisesRegex(
            mr.MissionError,
            "Repository is not clean",
        ):
            mr.require_clean_repository(
                allowed_untracked_path=mission_path,
            )

    @patch("ai.mission_runner.run_git")
    def test_different_untracked_mission_is_blocked(
        self,
        run_git_mock,
    ) -> None:
        mission_path = (
            mr.REPOSITORY_ROOT
            / "agent"
            / "missions"
            / "runtime-current.md"
        )

        run_git_mock.return_value = self._status_result(
            "?? agent/missions/runtime-other.md\n"
        )

        with self.assertRaisesRegex(
            mr.MissionError,
            "Repository is not clean",
        ):
            mr.require_clean_repository(
                allowed_untracked_path=mission_path,
            )

    @patch("ai.mission_runner.run_git")
    def test_tracked_current_mission_definition_is_not_allowed(
        self,
        run_git_mock,
    ) -> None:
        mission_path = (
            mr.REPOSITORY_ROOT
            / "agent"
            / "missions"
            / "runtime-current.md"
        )

        run_git_mock.return_value = self._status_result(
            " M agent/missions/runtime-current.md\n"
        )

        with self.assertRaisesRegex(
            mr.MissionError,
            "Repository is not clean",
        ):
            mr.require_clean_repository(
                allowed_untracked_path=mission_path,
            )


if __name__ == "__main__":
    unittest.main()
