from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.runtime import mission_diagnostics


class MissionDiagnosticsGitWarningTests(unittest.TestCase):
    def test_successful_git_warning_never_becomes_porcelain_output(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="",
            stderr="warning: unable to access '/home/ubuntu/.config/git/ignore': Permission denied\n",
        )

        with patch("agent.runtime.mission_diagnostics.subprocess.run", return_value=completed) as run:
            result = mission_diagnostics._git(Path("/tmp/repo"), "status", "--porcelain")

        self.assertTrue(result["ok"])
        self.assertEqual("", result["output"])
        self.assertIn("Permission denied", result["warning"])

        command = run.call_args.args[0]
        self.assertEqual("git", command[0])
        self.assertIn("core.excludesFile=/dev/null", command)

        env = run.call_args.kwargs["env"]
        self.assertEqual("/dev/null", env["GIT_CONFIG_GLOBAL"])
        self.assertEqual("1", env["GIT_CONFIG_NOSYSTEM"])

    def test_clean_repository_remains_clean_when_git_emits_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            data = root / "data"
            repo.mkdir()
            data.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "README.md").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

            real_run = subprocess.run

            def warning_run(*args, **kwargs):
                completed = real_run(*args, **kwargs)
                command = args[0] if args else kwargs.get("args", [])
                if (
                    isinstance(command, list)
                    and "status" in command
                    and "--porcelain" in command
                    and completed.returncode == 0
                ):
                    return subprocess.CompletedProcess(
                        args=completed.args,
                        returncode=0,
                        stdout=completed.stdout,
                        stderr="warning: unable to access '/home/ubuntu/.config/git/ignore': Permission denied\n",
                    )
                return completed

            with patch("agent.runtime.mission_diagnostics.subprocess.run", side_effect=warning_run):
                result = mission_diagnostics.collect_mission_diagnostics(
                    "m123",
                    repository_root=repo,
                    data_root=data,
                )

            repository = result["repository"]
            self.assertTrue(repository["clean"])
            self.assertEqual([], repository["dirty_entries"])
            self.assertTrue(any("Permission denied" in item for item in repository["git_warnings"]))


if __name__ == "__main__":
    unittest.main()
