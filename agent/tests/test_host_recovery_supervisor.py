from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.runtime.host_recovery_supervisor import HostRecoverySupervisor


class HostRecoverySupervisorTests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "README.md").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo

    def test_quarantines_only_identical_generated_mission_definition(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = self._repo(root)
            data = root / "data"
            durable = data / "runtime" / "mission-definitions"
            legacy = repo / "agent" / "missions"
            durable.mkdir(parents=True)
            legacy.mkdir(parents=True)
            content = "# generated mission\n"
            (durable / "m123.md").write_text(content, encoding="utf-8")
            (legacy / "m123.md").write_text(content, encoding="utf-8")

            result = HostRecoverySupervisor(
                repository_root=repo,
                data_root=data,
            ).recover("m123")

            self.assertTrue(result["ok"])
            self.assertEqual("recovered", result["action"])
            self.assertTrue(result["repository_clean"])
            self.assertEqual(["agent/missions/m123.md"], result["quarantined"])
            self.assertFalse((legacy / "m123.md").exists())
            self.assertTrue(Path(result["recovery_dir"]).joinpath("agent/missions/m123.md").is_file())

    def test_unrelated_untracked_file_is_preserved_and_blocks_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = self._repo(root)
            data = root / "data"
            unrelated = repo / "notes.txt"
            unrelated.write_text("human work\n", encoding="utf-8")

            result = HostRecoverySupervisor(
                repository_root=repo,
                data_root=data,
            ).recover("m123")

            self.assertFalse(result["ok"])
            self.assertEqual("blocked", result["action"])
            self.assertTrue(unrelated.is_file())
            self.assertIn(
                {"status": "??", "path": "notes.txt"},
                result["unresolved"],
            )

    def test_tracked_modification_is_never_reset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = self._repo(root)
            data = root / "data"
            tracked = repo / "README.md"
            tracked.write_text("changed by human\n", encoding="utf-8")

            result = HostRecoverySupervisor(
                repository_root=repo,
                data_root=data,
            ).recover("m123")

            self.assertFalse(result["ok"])
            self.assertEqual("blocked", result["action"])
            self.assertEqual("changed by human\n", tracked.read_text(encoding="utf-8"))
            self.assertTrue(any(item["path"] == "README.md" for item in result["unresolved"]))


if __name__ == "__main__":
    unittest.main()
