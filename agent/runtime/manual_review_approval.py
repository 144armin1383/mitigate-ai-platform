from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


_SAFE_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
_MANUAL_REVIEW_REASON = "manual_review_required"


class ManualReviewApprovalService:
    """Human-triggered, fail-closed approval and fast-forward merge service.

    The caller supplies an already-authenticated human identity. This service
    never accepts arbitrary Git refs or commands from the client: the mission
    identifier determines the only eligible mission branch.
    """

    def __init__(
        self,
        *,
        queue: Any,
        repository_root: str | Path | None = None,
        data_root: str | Path | None = None,
    ) -> None:
        self.queue = queue
        self.repository_root = Path(
            repository_root
            or os.environ.get("MITIGATE_AI_REPOSITORY_ROOT")
            or "/srv/mitigate/mitigate-ai-platform"
        ).expanduser().resolve()
        self.data_root = Path(
            data_root
            or os.environ.get("MITIGATE_AI_DATA_ROOT")
            or "/srv/mitigate/data"
        ).expanduser().resolve()

    def _git(
        self,
        *args: str,
        check: bool = True,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise RuntimeError("approval_git_operation_failed")
        return result

    def _failure_reason(self, mission_id: str) -> str:
        path = (
            self.data_root
            / "runtime"
            / "failure-evidence"
            / f"{mission_id}.json"
        )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise RuntimeError("approval_evidence_unavailable") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("approval_evidence_unavailable")
        return str(payload.get("reason") or "").strip().lower()

    def _mission_ref(self, mission_id: str) -> tuple[str, str]:
        patterns = (
            f"refs/heads/agent/mission-{mission_id}-*",
            f"refs/remotes/origin/agent/mission-{mission_id}-*",
        )
        refs: list[tuple[str, str]] = []
        for pattern in patterns:
            result = self._git(
                "for-each-ref",
                "--format=%(refname:short) %(objectname)",
                pattern,
            )
            for line in result.stdout.splitlines():
                value = line.strip()
                if not value or " " not in value:
                    continue
                ref, sha = value.rsplit(" ", 1)
                refs.append((ref.strip(), sha.strip()))

        by_sha: dict[str, list[str]] = {}
        for ref, sha in refs:
            by_sha.setdefault(sha, []).append(ref)

        if len(by_sha) != 1:
            raise RuntimeError("approval_mission_branch_ambiguous")

        sha, names = next(iter(by_sha.items()))
        preferred = next(
            (name for name in names if not name.startswith("origin/")),
            names[0],
        )
        return preferred, sha

    def _write_approval_record(
        self,
        *,
        mission_id: str,
        approved_by: str,
        branch: str,
        commit: str,
        before: str,
        changed_files: list[str],
        already_merged: bool,
    ) -> Path:
        directory = self.data_root / "runtime" / "approvals"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{mission_id}.json"
        payload = {
            "mission_id": mission_id,
            "action": "approved_and_merged",
            "approved_by": approved_by,
            "branch": branch,
            "commit": commit,
            "main_before": before,
            "main_after": commit,
            "changed_files": changed_files,
            "already_merged": bool(already_merged),
        }
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{mission_id}.",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return path

    def approve(self, mission_id: str, *, approved_by: str) -> dict[str, Any]:
        mission_id = str(mission_id or "").strip()
        approved_by = str(approved_by or "").strip()
        if not _SAFE_MISSION_ID.fullmatch(mission_id):
            raise ValueError("invalid_mission_id")
        if not approved_by or len(approved_by) > 160:
            raise ValueError("invalid_approver")

        mission = self.queue.get(mission_id)
        state = str(mission.get("state") or "").lower()
        if state == "completed":
            return {
                "approved": True,
                "mission_id": mission_id,
                "state": "completed",
                "idempotent": True,
            }
        if state != "blocked":
            raise RuntimeError("approval_requires_manual_review")
        if self._failure_reason(mission_id) != _MANUAL_REVIEW_REASON:
            raise RuntimeError("approval_requires_manual_review")

        if self._git("branch", "--show-current").stdout.strip() != "main":
            raise RuntimeError("approval_canonical_not_on_main")
        if self._git("status", "--porcelain").stdout.strip():
            raise RuntimeError("approval_canonical_not_clean")

        self._git("fetch", "origin", "main", timeout=60)
        before = self._git("rev-parse", "HEAD").stdout.strip()
        origin_main = self._git("rev-parse", "origin/main").stdout.strip()
        if before != origin_main:
            raise RuntimeError("approval_main_not_synced")

        branch, commit = self._mission_ref(mission_id)
        diff_check = self._git("diff", "--check", f"main...{branch}", check=False)
        if diff_check.returncode != 0 or diff_check.stdout.strip() or diff_check.stderr.strip():
            raise RuntimeError("approval_diff_check_failed")

        changed_files = [
            line.strip()
            for line in self._git(
                "diff",
                "--name-only",
                f"main...{branch}",
            ).stdout.splitlines()
            if line.strip()
        ]
        forbidden = (
            ".git",
            ".env",
            "secrets",
        )
        for path in changed_files:
            lowered = path.lower()
            if any(
                lowered == marker
                or lowered.startswith(marker + "/")
                or "/" + marker + "/" in "/" + lowered
                for marker in forbidden
            ):
                raise RuntimeError("approval_forbidden_path")

        already_merged = (
            self._git(
                "merge-base",
                "--is-ancestor",
                commit,
                "main",
                check=False,
            ).returncode
            == 0
        )

        if not already_merged:
            if (
                self._git(
                    "merge-base",
                    "--is-ancestor",
                    "main",
                    commit,
                    check=False,
                ).returncode
                != 0
            ):
                raise RuntimeError("approval_not_fast_forward")

            self._git("merge", "--ff-only", commit, timeout=60)
            try:
                self._git("push", "origin", "main", timeout=90)
            except Exception:
                self._git("reset", "--hard", before, timeout=30)
                raise

            self._git("fetch", "origin", "main", timeout=60)
            local_after = self._git("rev-parse", "HEAD").stdout.strip()
            remote_after = self._git("rev-parse", "origin/main").stdout.strip()
            if local_after != commit or remote_after != commit:
                raise RuntimeError("approval_remote_verification_failed")

        record = self._write_approval_record(
            mission_id=mission_id,
            approved_by=approved_by,
            branch=branch,
            commit=commit,
            before=before,
            changed_files=changed_files,
            already_merged=already_merged,
        )
        self.queue.approve_manual_review(mission_id)

        return {
            "approved": True,
            "mission_id": mission_id,
            "state": "completed",
            "branch": branch,
            "commit": commit,
            "changed_files": changed_files,
            "already_merged": already_merged,
            "approval_record": str(record),
        }
