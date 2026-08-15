from __future__ import annotations

import datetime as dt
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
    """Human-triggered, fail-closed manual-review decision service.

    The caller supplies an already-authenticated human identity. The browser
    never supplies Git refs or shell commands. Approval resolves the governed
    mission branch and integrates it into ``main``. A direct fast-forward is
    preferred; when ``main`` advanced after the mission branch was created, a
    controlled non-fast-forward merge is allowed only if Git can complete it
    without conflicts. Rejection performs no Git mutation and removes the
    mission from active work by transitioning the durable queue record to
    ``cancelled``.

    Every decision is persisted both as a per-mission JSON record and in an
    append-only JSONL history so future agents can reconstruct recent human
    decisions when diagnosing regressions or unexpected behavior.
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

    def _failure_evidence(self, mission_id: str) -> dict[str, Any]:
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
        return payload

    def _failure_reason(self, mission_id: str) -> str:
        return str(
            self._failure_evidence(mission_id).get("reason") or ""
        ).strip().lower()

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

    def _changed_files(self, branch: str) -> list[str]:
        return [
            line.strip()
            for line in self._git(
                "diff",
                "--name-only",
                f"main...{branch}",
            ).stdout.splitlines()
            if line.strip()
        ]

    def _decision_directory(self) -> Path:
        directory = self.data_root / "runtime" / "approvals"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _write_decision_record(
        self,
        *,
        mission_id: str,
        decided_by: str,
        decision: str,
        request_id: str,
        branch: str | None,
        commit: str | None,
        before: str,
        after: str,
        changed_files: list[str],
        already_merged: bool,
        result_state: str,
        integration_mode: str | None = None,
    ) -> Path:
        directory = self._decision_directory()
        path = directory / f"{mission_id}.json"
        timestamp = dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")
        payload = {
            "schema_version": 1,
            "record_type": "manual_review_decision",
            "mission_id": mission_id,
            "request_id": request_id,
            "decision": decision,
            "decided_by": decided_by,
            "decided_at": timestamp,
            "branch": branch,
            "commit": commit,
            "main_before": before,
            "main_after": after,
            "changed_files": changed_files,
            "already_merged": bool(already_merged),
            "result_state": result_state,
        }
        if integration_mode:
            payload["integration_mode"] = integration_mode

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

        history = directory / "decision-history.jsonl"
        line = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        history_fd = os.open(
            history,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(history_fd, line.encode("utf-8"))
            os.fsync(history_fd)
        finally:
            os.close(history_fd)

        return path

    def _validate_manual_review(
        self,
        mission_id: str,
        actor: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        mission_id = str(mission_id or "").strip()
        actor = str(actor or "").strip()
        if not _SAFE_MISSION_ID.fullmatch(mission_id):
            raise ValueError("invalid_mission_id")
        if not actor or len(actor) > 160:
            raise ValueError("invalid_approver")

        mission = self.queue.get(mission_id)
        evidence = self._failure_evidence(mission_id)
        state = str(mission.get("state") or "").lower()
        if state not in {"blocked", "completed", "cancelled"}:
            raise RuntimeError("approval_requires_manual_review")
        if (
            state == "blocked"
            and str(evidence.get("reason") or "").strip().lower()
            != _MANUAL_REVIEW_REASON
        ):
            raise RuntimeError("approval_requires_manual_review")
        return mission, evidence

    def _integrate_mission_commit(
        self,
        *,
        mission_id: str,
        commit: str,
        before: str,
    ) -> tuple[str, str]:
        """Integrate a reviewed mission commit and return (mode, main_after)."""
        if (
            self._git(
                "merge-base",
                "--is-ancestor",
                "main",
                commit,
                check=False,
            ).returncode
            == 0
        ):
            self._git("merge", "--ff-only", commit, timeout=60)
            return "fast_forward", self._git("rev-parse", "HEAD").stdout.strip()

        merge = self._git(
            "merge",
            "--no-ff",
            "--no-edit",
            "-m",
            f"Approve governed mission {mission_id}",
            commit,
            check=False,
            timeout=90,
        )
        if merge.returncode != 0:
            self._git("merge", "--abort", check=False, timeout=30)
            self._git("reset", "--hard", before, timeout=30)
            raise RuntimeError("approval_merge_conflict")

        after = self._git("rev-parse", "HEAD").stdout.strip()
        if (
            self._git(
                "merge-base",
                "--is-ancestor",
                commit,
                after,
                check=False,
            ).returncode
            != 0
        ):
            self._git("reset", "--hard", before, timeout=30)
            raise RuntimeError("approval_merge_verification_failed")
        return "merge_commit", after

    def approve(self, mission_id: str, *, approved_by: str) -> dict[str, Any]:
        mission, evidence = self._validate_manual_review(
            mission_id,
            approved_by,
        )
        state = str(mission.get("state") or "").lower()
        if state == "completed":
            return {
                "approved": True,
                "mission_id": mission_id,
                "state": "completed",
                "idempotent": True,
            }
        if state == "cancelled":
            raise RuntimeError("approval_mission_was_rejected")

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
        diff_check = self._git(
            "diff",
            "--check",
            f"main...{branch}",
            check=False,
        )
        if (
            diff_check.returncode != 0
            or diff_check.stdout.strip()
        ):
            raise RuntimeError("approval_diff_check_failed")

        changed_files = self._changed_files(branch)
        forbidden = (".git", ".env", "secrets")
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

        integration_mode = "already_merged"
        if not already_merged:
            integration_mode, local_after = self._integrate_mission_commit(
                mission_id=mission_id,
                commit=commit,
                before=before,
            )
            try:
                self._git("push", "origin", "main", timeout=90)
            except Exception:
                self._git("reset", "--hard", before, timeout=30)
                raise

            self._git("fetch", "origin", "main", timeout=60)
            remote_after = self._git("rev-parse", "origin/main").stdout.strip()
            verified_local = self._git("rev-parse", "HEAD").stdout.strip()
            if verified_local != local_after or remote_after != local_after:
                self._git("reset", "--hard", before, timeout=30)
                raise RuntimeError("approval_remote_verification_failed")
            if (
                self._git(
                    "merge-base",
                    "--is-ancestor",
                    commit,
                    verified_local,
                    check=False,
                ).returncode
                != 0
            ):
                self._git("reset", "--hard", before, timeout=30)
                raise RuntimeError("approval_remote_verification_failed")

        after = self._git("rev-parse", "HEAD").stdout.strip()
        record = self._write_decision_record(
            mission_id=mission_id,
            decided_by=approved_by,
            decision="approved",
            request_id=str(evidence.get("request_id") or ""),
            branch=branch,
            commit=commit,
            before=before,
            after=after,
            changed_files=changed_files,
            already_merged=already_merged,
            result_state="completed",
            integration_mode=integration_mode,
        )
        self.queue.approve_manual_review(mission_id)

        return {
            "approved": True,
            "mission_id": mission_id,
            "state": "completed",
            "branch": branch,
            "commit": commit,
            "main_after": after,
            "integration_mode": integration_mode,
            "changed_files": changed_files,
            "already_merged": already_merged,
            "approval_record": str(record),
        }

    def reject(self, mission_id: str, *, rejected_by: str) -> dict[str, Any]:
        mission, evidence = self._validate_manual_review(
            mission_id,
            rejected_by,
        )
        state = str(mission.get("state") or "").lower()
        if state == "cancelled":
            return {
                "rejected": True,
                "mission_id": mission_id,
                "state": "cancelled",
                "idempotent": True,
            }
        if state == "completed":
            raise RuntimeError("rejection_mission_already_completed")

        if self._git("branch", "--show-current").stdout.strip() != "main":
            raise RuntimeError("approval_canonical_not_on_main")
        if self._git("status", "--porcelain").stdout.strip():
            raise RuntimeError("approval_canonical_not_clean")

        before = self._git("rev-parse", "HEAD").stdout.strip()
        branch: str | None = None
        commit: str | None = None
        changed_files: list[str] = []
        try:
            branch, commit = self._mission_ref(mission_id)
            changed_files = self._changed_files(branch)
        except RuntimeError:
            branch = None
            commit = None
            changed_files = []

        record = self._write_decision_record(
            mission_id=mission_id,
            decided_by=rejected_by,
            decision="rejected",
            request_id=str(evidence.get("request_id") or ""),
            branch=branch,
            commit=commit,
            before=before,
            after=before,
            changed_files=changed_files,
            already_merged=False,
            result_state="cancelled",
            integration_mode="none",
        )
        self.queue.reject_manual_review(mission_id)

        return {
            "rejected": True,
            "mission_id": mission_id,
            "state": "cancelled",
            "branch": branch,
            "commit": commit,
            "changed_files": changed_files,
            "decision_record": str(record),
        }
