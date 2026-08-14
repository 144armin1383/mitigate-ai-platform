from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.manual_review_approval import ManualReviewApprovalService


class ManualReviewDivergedMergeTests(unittest.TestCase):
    def _run(self, repo: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            list(args),
            cwd=repo,
            text=True,
            capture_output=True,
            check=check,
        )
        return result.stdout.strip()

    def test_diverged_mission_merges_cleanly_and_preserves_both_histories(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            remote = root / "remote.git"
            data = root / "data"
            repo.mkdir()

            self._run(repo, "git", "init", "-q", "-b", "main")
            self._run(repo, "git", "config", "user.email", "tests@example.invalid")
            self._run(repo, "git", "config", "user.name", "MITIGATE Tests")
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            self._run(repo, "git", "add", "README.md")
            self._run(repo, "git", "commit", "-q", "-m", "base")
            self._run(repo, "git", "init", "-q", "--bare", str(remote))
            self._run(repo, "git", "remote", "add", "origin", str(remote))
            self._run(repo, "git", "push", "-q", "-u", "origin", "main")

            mission_id = "m-diverged-approval"
            queue_path = data / "runtime" / "missions.json"
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue = AutonomousMissionQueue(str(queue_path), default_max_retries=2)
            queue.enqueue(mission_id, 8)
            self.assertIsNotNone(queue.claim("test-worker"))
            queue.block(mission_id)

            branch = f"agent/mission-{mission_id}-20260814-190000"
            self._run(repo, "git", "switch", "-q", "-c", branch)
            (repo / "docs").mkdir()
            (repo / "docs" / "smoke.md").write_text("# Smoke\n", encoding="utf-8")
            self._run(repo, "git", "add", "docs/smoke.md")
            self._run(repo, "git", "commit", "-q", "-m", "mission output")
            mission_commit = self._run(repo, "git", "rev-parse", "HEAD")
            self._run(repo, "git", "push", "-q", "-u", "origin", branch)

            self._run(repo, "git", "switch", "-q", "main")
            (repo / "README.md").write_text("base\nmain advanced\n", encoding="utf-8")
            self._run(repo, "git", "add", "README.md")
            self._run(repo, "git", "commit", "-q", "-m", "advance main")
            advanced_main = self._run(repo, "git", "rev-parse", "HEAD")
            self._run(repo, "git", "push", "-q", "origin", "main")

            evidence_dir = data / "runtime" / "failure-evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / f"{mission_id}.json").write_text(
                json.dumps(
                    {
                        "mission_id": mission_id,
                        "request_id": "request-diverged-approval",
                        "reason": "manual_review_required",
                    }
                ),
                encoding="utf-8",
            )

            service = ManualReviewApprovalService(
                queue=queue,
                repository_root=repo,
                data_root=data,
            )
            result = service.approve(mission_id, approved_by="panel-admin")

            self.assertTrue(result["approved"])
            self.assertEqual("merge_commit", result["integration_mode"])
            self.assertEqual("completed", queue.get(mission_id)["state"])
            self.assertTrue((repo / "docs" / "smoke.md").exists())
            main_after = self._run(repo, "git", "rev-parse", "HEAD")
            self.assertNotEqual(advanced_main, main_after)
            self.assertEqual(
                0,
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", mission_commit, main_after],
                    cwd=repo,
                    check=False,
                ).returncode,
            )
            self.assertEqual(
                0,
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", advanced_main, main_after],
                    cwd=repo,
                    check=False,
                ).returncode,
            )
            remote_main = subprocess.check_output(
                ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
                text=True,
            ).strip()
            self.assertEqual(main_after, remote_main)

            record = json.loads(
                (data / "runtime" / "approvals" / f"{mission_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("merge_commit", record["integration_mode"])
            self.assertEqual(mission_commit, record["commit"])
            self.assertEqual(main_after, record["main_after"])

    def test_conflicting_diverged_mission_fails_closed_and_restores_main(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            remote = root / "remote.git"
            data = root / "data"
            repo.mkdir()

            self._run(repo, "git", "init", "-q", "-b", "main")
            self._run(repo, "git", "config", "user.email", "tests@example.invalid")
            self._run(repo, "git", "config", "user.name", "MITIGATE Tests")
            (repo / "shared.txt").write_text("base\n", encoding="utf-8")
            self._run(repo, "git", "add", "shared.txt")
            self._run(repo, "git", "commit", "-q", "-m", "base")
            self._run(repo, "git", "init", "-q", "--bare", str(remote))
            self._run(repo, "git", "remote", "add", "origin", str(remote))
            self._run(repo, "git", "push", "-q", "-u", "origin", "main")

            mission_id = "m-conflict-approval"
            queue_path = data / "runtime" / "missions.json"
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue = AutonomousMissionQueue(str(queue_path), default_max_retries=2)
            queue.enqueue(mission_id, 8)
            self.assertIsNotNone(queue.claim("test-worker"))
            queue.block(mission_id)

            branch = f"agent/mission-{mission_id}-20260814-190100"
            self._run(repo, "git", "switch", "-q", "-c", branch)
            (repo / "shared.txt").write_text("mission\n", encoding="utf-8")
            self._run(repo, "git", "add", "shared.txt")
            self._run(repo, "git", "commit", "-q", "-m", "mission output")
            self._run(repo, "git", "push", "-q", "-u", "origin", branch)

            self._run(repo, "git", "switch", "-q", "main")
            (repo / "shared.txt").write_text("main\n", encoding="utf-8")
            self._run(repo, "git", "add", "shared.txt")
            self._run(repo, "git", "commit", "-q", "-m", "advance main")
            before = self._run(repo, "git", "rev-parse", "HEAD")
            self._run(repo, "git", "push", "-q", "origin", "main")

            evidence_dir = data / "runtime" / "failure-evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / f"{mission_id}.json").write_text(
                json.dumps(
                    {
                        "mission_id": mission_id,
                        "request_id": "request-conflict-approval",
                        "reason": "manual_review_required",
                    }
                ),
                encoding="utf-8",
            )

            service = ManualReviewApprovalService(
                queue=queue,
                repository_root=repo,
                data_root=data,
            )
            with self.assertRaisesRegex(RuntimeError, "approval_merge_conflict"):
                service.approve(mission_id, approved_by="panel-admin")

            self.assertEqual(before, self._run(repo, "git", "rev-parse", "HEAD"))
            self.assertEqual("blocked", queue.get(mission_id)["state"])
            self.assertEqual("main\n", (repo / "shared.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
