from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from pathlib import Path, PurePosixPath

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeStatus,
)
from agent.execution.workspace_manager import ExecutionWorkspace


class RuntimePublishError(RuntimeError):
    pass


class RuntimeBranchPublisher:
    """Publish successful external-runtime changes to an isolated Git branch.

    External providers never commit, push, merge or touch canonical main. MITIGATE
    performs those actions after scope validation and while the disposable
    worktree is still alive. Publication is allowlist-based: provider-created
    workspace/runtime artifacts outside the mission's authorized paths are never
    staged or published and disappear with the disposable workspace.
    """

    def __init__(self, repository_root: str | Path, *, remote: str = "origin") -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.remote = str(remote).strip() or "origin"

    @staticmethod
    def _normalized_path(value: str) -> str:
        text = str(value or "").strip().replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        path = PurePosixPath(text)
        if not text or path.is_absolute() or ".." in path.parts:
            return ""
        return str(path)

    @classmethod
    def _matches_scope(cls, path: str, scopes: tuple[str, ...]) -> bool:
        candidate = cls._normalized_path(path)
        if not candidate:
            return False
        for raw_scope in scopes:
            scope = cls._normalized_path(raw_scope).rstrip("/")
            if not scope:
                continue
            if candidate == scope or candidate.startswith(scope + "/"):
                return True
        return False

    @classmethod
    def _denied(cls, path: str, denied_paths: tuple[str, ...]) -> bool:
        candidate = cls._normalized_path(path).lower()
        if not candidate:
            return True
        parts = PurePosixPath(candidate).parts
        for raw_scope in denied_paths:
            scope = cls._normalized_path(raw_scope).lower().rstrip("/")
            if not scope:
                continue
            if candidate == scope or candidate.startswith(scope + "/"):
                return True
            if "/" not in scope and scope in parts:
                return True
        return False

    def publish(
        self,
        *,
        workspace: ExecutionWorkspace,
        request: ExecutionRequest,
        result: ExecutionResult,
    ) -> ExecutionResult:
        if result.status != RuntimeStatus.succeeded:
            return result

        runtime_changed = tuple(
            path
            for path in (
                self._normalized_path(item)
                for item in result.evidence.changed_files
            )
            if path
        )
        if not runtime_changed:
            return result

        denied = tuple(
            path for path in runtime_changed if self._denied(path, request.denied_paths)
        )
        if denied:
            evidence = replace(
                result.evidence,
                diagnostics=tuple(result.evidence.diagnostics)
                + ("runtime_changed_denied_paths:" + ",".join(denied[:20]),),
            )
            return replace(
                result,
                status=RuntimeStatus.blocked,
                retryable=False,
                reason="runtime_changed_denied_paths",
                evidence=evidence,
            )

        if request.allowed_paths:
            authorized = tuple(
                path
                for path in runtime_changed
                if self._matches_scope(path, request.allowed_paths)
            )
            ignored = tuple(path for path in runtime_changed if path not in authorized)
        else:
            authorized = runtime_changed
            ignored = ()

        # Scope expansion is never silently accepted or partially published.
        # Return the exact missing path delta so Core can request only the
        # exceptional authorization rather than forcing the user to diagnose
        # an opaque generic block.
        if ignored:
            diagnostics = tuple(result.evidence.diagnostics) + tuple(
                f"scope_violation:{path}" for path in ignored[:50]
            )
            evidence = replace(
                result.evidence,
                diagnostics=diagnostics,
                provider_metadata={
                    **dict(result.evidence.provider_metadata or {}),
                    "missing_scope_paths": list(ignored[:200]),
                    "authorized_scope_paths": list(request.allowed_paths[:200]),
                },
            )
            return replace(
                result,
                status=RuntimeStatus.blocked,
                retryable=False,
                reason="runtime_changed_paths_outside_authorized_scope",
                evidence=evidence,
            )

        if not authorized:
            evidence = replace(
                result.evidence,
                changed_files=(),
                diagnostics=tuple(result.evidence.diagnostics)
                + ("runtime_changes_outside_authorized_scope",),
            )
            return replace(result, evidence=evidence)

        branch = self._branch_name(request.mission_id)
        path = workspace.path

        self._git(path, "switch", "-c", branch)
        self._git(path, "add", "--", *authorized)

        staged = self._git(path, "diff", "--cached", "--name-only").stdout.splitlines()
        staged_paths = tuple(sorted(line.strip() for line in staged if line.strip()))
        expected_paths = tuple(sorted(authorized))
        if staged_paths != expected_paths:
            raise RuntimePublishError("published_scope_does_not_match_authorized_changes")

        self._git(path, "commit", "-m", f"Runtime mission: {request.mission_id}")
        commit = self._git(path, "rev-parse", "HEAD").stdout.strip()
        if not commit:
            raise RuntimePublishError("runtime_commit_resolution_failed")

        self._git(path, "push", "-u", self.remote, branch)

        return replace(
            result,
            evidence=replace(
                result.evidence,
                changed_files=staged_paths,
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
