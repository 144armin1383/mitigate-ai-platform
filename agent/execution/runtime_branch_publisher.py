from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from pathlib import Path

from agent.execution.runtime_adapter import ExecutionRequest, ExecutionResult, RuntimeStatus
from agent.execution.workspace_manager import ExecutionWorkspace


class RuntimePublishError(RuntimeError):
    pass


class RuntimeBranchPublisher:
    """Publish successful external-runtime changes to an isolated Git branch.

    External providers never commit, push, merge or touch canonical main. MITIGATE
    performs those actions after scope validation and while the disposable
    worktree is still alive.
    """

    def __init__(self, repository_root: str | Path, *, remote: str = "origin") -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.remote = str(remote).strip() or "origin"

    def publish(
        self,
        *,
        workspace: ExecutionWorkspace,
        request: ExecutionRequest,
        result: ExecutionResult,
    ) -> ExecutionResult:
        if result.status != RuntimeStatus.succeeded:
            return result

        changed = tuple(result.evidence.changed_files)
        if not changed:
            return result

        branch = self._branch_name(request.mission_id)
        path = workspace.path

        self._git(path, "switch", "-c", branch)
        self._git(path, "add", "--all")

        staged = self._git(path, "diff", "--cached", "--name-only").stdout.splitlines()
        staged_paths = tuple(sorted(line.strip() for line in staged if line.strip()))
        if staged_paths != tuple(sorted(changed)):
            raise RuntimePublishError("published_scope_does_not_match_runtime_evidence")

        self._git(path, "commit", "-m", f"Runtime mission: {request.mission_id}")
        commit = self._git(path, "rev-parse", "HEAD").stdout.strip()
        if not commit:
            raise RuntimePublishError("runtime_commit_resolution_failed")

        self._git(path, "push", "-u", self.remote, branch)

        return replace(
            result,
            evidence=replace(
                result.evidence,
                branch=branch,
                commit_sha=commit,
            ),
        )

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()[-800:]
            raise RuntimePublishError(f"runtime_git_failed:{args[0]}:{detail}")
        return proc

    @staticmethod
    def _branch_name(mission_id: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in mission_id)
        safe = (safe.strip("-") or "mission")[:72]
        return f"agent/runtime-{safe}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"


__all__ = ["RuntimeBranchPublisher", "RuntimePublishError"]
