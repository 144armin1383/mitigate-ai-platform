from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import ExecutionEvidence, ExecutionRequest, ExecutionResult, RuntimeStatus
from agent.execution.runtime_branch_publisher import RuntimeBranchPublisher
from agent.execution.workspace_manager import ExecutionWorkspace


class RuntimeBranchPublisherTests(unittest.TestCase):
    def test_successful_changes_are_committed_and_pushed_to_isolated_branch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            remote = root / "remote.git"
            repo = root / "repo"
            workspace = root / "workspace"

            subprocess.run(["git", "init", "--bare", "-q", remote], check=True)
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "MITIGATE Test"], check=True)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "README.md"], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "base"], check=True)
            subprocess.run(["git", "-C", repo, "remote", "add", "origin", str(remote)], check=True)
            subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", str(workspace), "HEAD"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", workspace, "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", workspace, "config", "user.name", "MITIGATE Test"], check=True)

            (workspace / "agent").mkdir()
            (workspace / "agent" / "change.py").write_text("VALUE = 1\n", encoding="utf-8")

            request = ExecutionRequest(
                request_id="r1",
                mission_id="m1",
                objective="change",
                repository_root=str(repo),
                base_revision="HEAD",
                allowed_paths=("agent/change.py",),
            )
            result = ExecutionResult(
                status=RuntimeStatus.succeeded,
                provider="fake",
                evidence=ExecutionEvidence(changed_files=("agent/change.py",)),
            )

            published = RuntimeBranchPublisher(repo).publish(
                workspace=ExecutionWorkspace(path=workspace, base_revision="HEAD"),
                request=request,
                result=result,
            )

            self.assertTrue(published.evidence.branch)
            self.assertTrue(published.evidence.commit_sha)
            refs = subprocess.run(
                ["git", "--git-dir", str(remote), "for-each-ref", "--format=%(refname:short)"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertIn(published.evidence.branch, refs)


if __name__ == "__main__":
    unittest.main()
