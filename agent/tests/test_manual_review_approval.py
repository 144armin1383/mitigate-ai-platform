from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.manual_review_approval import ManualReviewApprovalService
from agent.web import panel_server_approval
from agent.web import panel_server


class ManualReviewApprovalTests(unittest.TestCase):
    def _run(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            list(args),
            cwd=root,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()

    def _fixture(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        repo = root / "repo"
        remote = root / "remote.git"
        data = root / "data"
        repo.mkdir()

        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "MITIGATE Tests"], cwd=repo, check=True)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], cwd=repo, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
        subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=repo, check=True)
        return td, repo, remote, data

    def _blocked_mission(
        self,
        *,
        repo: Path,
        data: Path,
        reason: str = "manual_review_required",
    ) -> tuple[AutonomousMissionQueue, str, str]:
        mission_id = "m-review-approval-1"
        queue_path = data / "runtime" / "missions.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue = AutonomousMissionQueue(str(queue_path), default_max_retries=2)
        queue.enqueue(mission_id, 8)
        claimed = queue.claim("test-worker")
        self.assertIsNotNone(claimed)
        queue.block(mission_id)

        branch = f"agent/mission-{mission_id}-20260814-150000"
        subprocess.run(["git", "switch", "-q", "-c", branch], cwd=repo, check=True)
        (repo / "docs").mkdir()
        (repo / "docs" / "assessment.md").write_text("# Approved assessment\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/assessment.md"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "mission output"], cwd=repo, check=True)
        mission_commit = self._run(repo, "git", "rev-parse", "HEAD")
        subprocess.run(["git", "push", "-q", "-u", "origin", branch], cwd=repo, check=True)
        subprocess.run(["git", "switch", "-q", "main"], cwd=repo, check=True)

        evidence_dir = data / "runtime" / "failure-evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / f"{mission_id}.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "request_id": "request-review-1",
                    "reason": reason,
                }
            ),
            encoding="utf-8",
        )
        return queue, mission_id, mission_commit

    def test_approval_fast_forwards_pushes_and_records_decision(self) -> None:
        td, repo, remote, data = self._fixture()
        with td:
            queue, mission_id, mission_commit = self._blocked_mission(repo=repo, data=data)
            before = self._run(repo, "git", "rev-parse", "HEAD")
            service = ManualReviewApprovalService(queue=queue, repository_root=repo, data_root=data)

            result = service.approve(mission_id, approved_by="panel-admin")

            self.assertTrue(result["approved"])
            self.assertEqual("completed", result["state"])
            self.assertEqual(mission_commit, result["commit"])
            self.assertEqual(["docs/assessment.md"], result["changed_files"])
            self.assertEqual("completed", queue.get(mission_id)["state"])
            self.assertEqual(mission_commit, self._run(repo, "git", "rev-parse", "HEAD"))
            self.assertNotEqual(before, mission_commit)
            remote_main = subprocess.check_output(
                ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
                text=True,
            ).strip()
            self.assertEqual(mission_commit, remote_main)

            record_dir = data / "runtime" / "approvals"
            decision = json.loads((record_dir / f"{mission_id}.json").read_text(encoding="utf-8"))
            self.assertEqual("approved", decision["decision"])
            self.assertEqual("panel-admin", decision["decided_by"])
            self.assertEqual("request-review-1", decision["request_id"])
            self.assertEqual(mission_commit, decision["main_after"])
            self.assertTrue(decision["decided_at"].endswith("Z"))

            history = (record_dir / "decision-history.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(history))
            history_record = json.loads(history[0])
            self.assertEqual("approved", history_record["decision"])
            self.assertEqual(mission_id, history_record["mission_id"])

    def test_reject_cancels_without_git_merge_and_records_decision(self) -> None:
        td, repo, remote, data = self._fixture()
        with td:
            queue, mission_id, mission_commit = self._blocked_mission(repo=repo, data=data)
            before = self._run(repo, "git", "rev-parse", "HEAD")
            service = ManualReviewApprovalService(queue=queue, repository_root=repo, data_root=data)

            result = service.reject(mission_id, rejected_by="panel-admin")

            self.assertTrue(result["rejected"])
            self.assertEqual("cancelled", result["state"])
            self.assertEqual(mission_commit, result["commit"])
            self.assertEqual(["docs/assessment.md"], result["changed_files"])
            self.assertEqual("cancelled", queue.get(mission_id)["state"])
            self.assertEqual(before, self._run(repo, "git", "rev-parse", "HEAD"))
            remote_main = subprocess.check_output(
                ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
                text=True,
            ).strip()
            self.assertEqual(before, remote_main)

            record_dir = data / "runtime" / "approvals"
            decision = json.loads((record_dir / f"{mission_id}.json").read_text(encoding="utf-8"))
            self.assertEqual("rejected", decision["decision"])
            self.assertEqual("panel-admin", decision["decided_by"])
            self.assertEqual("cancelled", decision["result_state"])
            self.assertEqual(before, decision["main_before"])
            self.assertEqual(before, decision["main_after"])

            history_record = json.loads(
                (record_dir / "decision-history.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual("rejected", history_record["decision"])

    def test_non_manual_blocker_cannot_be_approved_or_rejected(self) -> None:
        td, repo, _remote, data = self._fixture()
        with td:
            queue, mission_id, _commit = self._blocked_mission(
                repo=repo,
                data=data,
                reason="runtime_changed_paths_outside_authorized_scope",
            )
            service = ManualReviewApprovalService(queue=queue, repository_root=repo, data_root=data)
            with self.assertRaisesRegex(RuntimeError, "approval_requires_manual_review"):
                service.approve(mission_id, approved_by="panel-admin")
            with self.assertRaisesRegex(RuntimeError, "approval_requires_manual_review"):
                service.reject(mission_id, rejected_by="panel-admin")
            self.assertEqual("blocked", queue.get(mission_id)["state"])

    def test_approval_backend_is_api_only_and_supports_reject(self) -> None:
        self.assertFalse(hasattr(panel_server, "PANEL_HTML"))
        self.assertTrue(issubclass(panel_server_approval.ApprovalPanelServer, panel_server.PanelServer))
        source = Path(panel_server.__file__).read_text(encoding="utf-8")
        approval_source = Path(panel_server_approval.__file__).read_text(encoding="utf-8")
        self.assertIn("standalone_panel_removed", source)
        self.assertNotIn("Agent Control Panel", source)
        self.assertIn('parts[3] in {"approve", "reject"}', approval_source)
        self.assertIn("reject_manual_review", approval_source)


if __name__ == "__main__":
    unittest.main()
