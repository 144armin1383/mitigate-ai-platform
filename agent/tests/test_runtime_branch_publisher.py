from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeStatus,
)
from agent.execution.runtime_branch_publisher import RuntimeBranchPublisher
from agent.execution.workspace_manager import ExecutionWorkspace


class RuntimeBranchPublisherTests(unittest.TestCase):
    def _fixture(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
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
        subprocess.run(
            ["git", "-C", repo, "worktree", "add", "--detach", str(workspace), "HEAD"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["git", "-C", workspace, "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", workspace, "config", "user.name", "MITIGATE Test"], check=True)
        return td, remote, repo, workspace

    def test_successful_changes_are_committed_and_pushed_to_isolated_branch(self) -> None:
        td, remote, repo, workspace = self._fixture()
        with td:
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
            self.assertEqual(("agent/change.py",), published.evidence.changed_files)
            refs = subprocess.run(
                ["git", "--git-dir", str(remote), "for-each-ref", "--format=%(refname:short)"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertIn(published.evidence.branch, refs)

    def test_out_of_scope_runtime_artifacts_are_not_published(self) -> None:
        td, _remote, repo, workspace = self._fixture()
        with td:
            (workspace / "docs").mkdir()
            (workspace / "docs" / "smoke.md").write_text("# Smoke\n", encoding="utf-8")
            for name in (
                "AGENTS.md",
                "HEARTBEAT.md",
                "IDENTITY.md",
                "SOUL.md",
                "TOOLS.md",
                "USER.md",
                "openclaw-workspace-state.json",
            ):
                (workspace / name).write_text("runtime state\n", encoding="utf-8")

            runtime_changes = (
                "AGENTS.md",
                "HEARTBEAT.md",
                "IDENTITY.md",
                "SOUL.md",
                "TOOLS.md",
                "USER.md",
                "docs/smoke.md",
                "openclaw-workspace-state.json",
            )
            request = ExecutionRequest(
                request_id="r-openclaw",
                mission_id="m-openclaw",
                objective="Create only docs/smoke.md",
                repository_root=str(repo),
                base_revision="HEAD",
                allowed_paths=("docs",),
                denied_paths=(".git", ".env", "secrets"),
            )
            result = ExecutionResult(
                status=RuntimeStatus.succeeded,
                provider="openclaw",
                evidence=ExecutionEvidence(changed_files=runtime_changes),
            )

            published = RuntimeBranchPublisher(repo).publish(
                workspace=ExecutionWorkspace(path=workspace, base_revision="HEAD"),
                request=request,
                result=result,
            )

            self.assertEqual(("docs/smoke.md",), published.evidence.changed_files)
            self.assertIn("AGENTS.md", published.evidence.provider_metadata["ignored_out_of_scope_files"])
            commit = published.evidence.commit_sha
            tree = subprocess.check_output(
                ["git", "-C", repo, "ls-tree", "-r", "--name-only", commit],
                text=True,
            ).splitlines()
            self.assertIn("docs/smoke.md", tree)
            self.assertNotIn("AGENTS.md", tree)
            self.assertNotIn("openclaw-workspace-state.json", tree)

    def test_denied_path_change_fails_closed(self) -> None:
        td, _remote, repo, workspace = self._fixture()
        with td:
            (workspace / "docs").mkdir()
            (workspace / "docs" / "smoke.md").write_text("# Smoke\n", encoding="utf-8")
            (workspace / ".env").write_text("SECRET=x\n", encoding="utf-8")
            request = ExecutionRequest(
                request_id="r-denied",
                mission_id="m-denied",
                objective="change",
                repository_root=str(repo),
                base_revision="HEAD",
                allowed_paths=("docs",),
                denied_paths=(".git", ".env", "secrets"),
            )
            result = ExecutionResult(
                status=RuntimeStatus.succeeded,
                provider="fake",
                evidence=ExecutionEvidence(changed_files=("docs/smoke.md", ".env")),
            )

            published = RuntimeBranchPublisher(repo).publish(
                workspace=ExecutionWorkspace(path=workspace, base_revision="HEAD"),
                request=request,
                result=result,
            )

            self.assertEqual(RuntimeStatus.blocked, published.status)
            self.assertEqual("runtime_changed_denied_paths", published.reason)
            self.assertFalse(published.retryable)
            self.assertIsNone(published.evidence.branch)


if __name__ == "__main__":
    unittest.main()
