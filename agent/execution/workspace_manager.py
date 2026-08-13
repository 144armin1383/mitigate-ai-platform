from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    """Raised when MITIGATE cannot create or safely destroy an execution workspace."""


@dataclass(frozen=True)
class ExecutionWorkspace:
    path: Path
    base_revision: str


class DisposableWorkspaceManager:
    """Create isolated Git worktrees for external execution providers.

    The canonical checkout is never used as the execution workspace. Each task
    gets a disposable detached worktree created from an explicit Git revision.
    Cleanup removes the worktree even when the provider fails, preventing failed
    attempts from contaminating the canonical repository.
    """

    def __init__(
        self,
        repository_root: str | Path,
        *,
        workspace_parent: str | Path | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        if workspace_parent is None:
            workspace_parent = Path(tempfile.gettempdir()) / "mitigate-runtime-workspaces"
        self.workspace_parent = Path(workspace_parent).expanduser().resolve()

    def create(self, *, mission_id: str, base_revision: str) -> ExecutionWorkspace:
        if not mission_id.strip():
            raise WorkspaceError("mission_id_must_not_be_empty")
        if not base_revision.strip():
            raise WorkspaceError("base_revision_must_not_be_empty")
        if not (self.repository_root / ".git").exists():
            raise WorkspaceError("repository_root_is_not_git_checkout")

        self._git("rev-parse", "--verify", f"{base_revision}^{{commit}}")
        self.workspace_parent.mkdir(parents=True, exist_ok=True)
        path = Path(
            tempfile.mkdtemp(
                prefix=self._safe_prefix(mission_id) + "-",
                dir=self.workspace_parent,
            )
        ).resolve()

        try:
            # mkdtemp creates the directory; git worktree add requires the target
            # path not to exist.
            path.rmdir()
            self._git("worktree", "add", "--detach", str(path), base_revision)
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise

        if path == self.repository_root:
            self.remove(ExecutionWorkspace(path=path, base_revision=base_revision))
            raise WorkspaceError("workspace_must_not_equal_canonical_repository")

        return ExecutionWorkspace(path=path, base_revision=base_revision)

    def remove(self, workspace: ExecutionWorkspace) -> None:
        path = workspace.path.expanduser().resolve()
        if path == self.repository_root:
            raise WorkspaceError("refusing_to_remove_canonical_repository")

        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            # Prune only metadata for already-gone worktrees. This does not touch
            # tracked or untracked files in the canonical checkout.
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=self.repository_root,
                text=True,
                capture_output=True,
                check=False,
            )
            if path.exists():
                raise WorkspaceError("failed_to_remove_disposable_workspace")

    def canonical_is_clean(self) -> bool:
        result = self._git("status", "--porcelain", "--untracked-files=all")
        return not result.stdout.strip()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:500]
            raise WorkspaceError(f"git_command_failed:{args[0]}:{detail}")
        return result

    @staticmethod
    def _safe_prefix(mission_id: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in mission_id)
        return (safe.strip("-") or "mission")[:80]


__all__ = [
    "DisposableWorkspaceManager",
    "ExecutionWorkspace",
    "WorkspaceError",
]
