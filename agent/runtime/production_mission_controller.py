from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from agent.git.review_engine import GitReviewEngine


MISSION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class ProductionMissionController:
    """
    Production adapter from BackgroundWorker missions to the existing
    MITIGATE AI Mission Runner.

    The Mission Runner remains the single execution authority for:
    - repository scanning
    - AI generation
    - deliverable enforcement
    - validation
    - Self-Healing
    - commit
    - branch push

    This adapter owns only runtime process isolation, status normalization,
    and restoring the repository to main after each execution.
    """

    def __init__(
        self,
        *,
        repository_root: Optional[str | Path] = None,
        timeout_seconds: int = 1800,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

        if repository_root is None:
            repository_root = Path(__file__).resolve().parents[2]

        self.repository_root = Path(repository_root).resolve()
        self.agent_root = self.repository_root / "agent"
        self.timeout_seconds = int(timeout_seconds)

    def _mission_name(self, mission: Dict[str, Any]) -> str:
        value = mission.get("mission_name") or mission.get("id")
        name = str(value or "").strip()

        if not MISSION_NAME_RE.fullmatch(name):
            raise ValueError("invalid_mission_name")

        return name

    def _mission_metadata(
        self,
        mission_name: str,
    ) -> Dict[str, Any]:
        path = (
            self.agent_root
            / "missions"
            / f"{mission_name}.md"
        )

        metadata: Dict[str, Any] = {}

        try:
            content = path.read_text(
                encoding="utf-8"
            )
        except OSError:
            return metadata

        task_match = re.search(
            r"^Task Type:\s*(.+?)\s*$",
            content,
            re.MULTILINE,
        )

        if task_match:
            task_type = task_match.group(1).strip()

            if task_type:
                metadata["task_type"] = task_type

        context_match = re.search(
            r"## Context\s*\n\s*```json\s*\n(.*?)\n```",
            content,
            re.DOTALL,
        )

        if context_match:
            try:
                context = json.loads(
                    context_match.group(1)
                )
            except (TypeError, ValueError):
                context = {}

            if isinstance(context, dict):
                request_id = str(
                    context.get("request_id") or ""
                ).strip()

                if request_id:
                    metadata["request_id"] = request_id

        return metadata

    @staticmethod
    def _changed_files_from_review(
        review: Dict[str, Any],
    ) -> list[str]:
        files = review.get("files", {})

        if not isinstance(files, dict):
            return []

        changed: list[str] = []

        for category in (
            "added",
            "modified",
            "deleted",
            "renamed",
        ):
            entries = files.get(category, [])

            if not isinstance(entries, list):
                continue

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                candidate = str(
                    entry.get("path") or ""
                ).strip()

                if candidate and candidate not in changed:
                    changed.append(candidate)

        return changed

    def _git_commit(
        self,
        ref: str,
    ) -> Optional[str]:
        result = subprocess.run(
            [
                "git",
                "rev-parse",
                ref,
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            return None

        commit = result.stdout.strip()

        return commit or None

    def _restore_main(self) -> bool:
        result = subprocess.run(
            ["git", "switch", "main"],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def _mission_branch(self, mission_name: str) -> Optional[str]:
        prefix = f"agent/mission-{mission_name.replace('_', '-')}-"

        result = subprocess.run(
            [
                "git",
                "for-each-ref",
                "--sort=-committerdate",
                "--format=%(refname:short)",
                "refs/heads/agent/mission-*",
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            branch = line.strip()

            if branch.startswith(prefix):
                return branch

        return None

    def _review_and_merge(
        self,
        mission_name: str,
    ) -> Dict[str, Any]:
        branch = self._mission_branch(mission_name)

        if not branch:
            return {
                "status": "blocked",
                "reason": "mission_branch_not_found",
            }

        review = GitReviewEngine(
            str(self.repository_root)
        ).review(
            "main",
            branch,
        )

        validation = review.get(
            "validation",
            {},
        )

        if not validation.get("ok", False):
            return {
                "status": "blocked",
                "reason": "git_review_failed",
                "branch": branch,
                "risk_level": review.get("risk_level"),
                "merge_recommendation": review.get(
                    "merge_recommendation"
                ),
            }

        risk_level = review.get("risk_level")
        recommendation = review.get(
            "merge_recommendation"
        )

        if (
            risk_level != "low"
            or recommendation != "approve"
        ):
            return {
                "status": "blocked",
                "reason": "manual_review_required",
                "branch": branch,
                "risk_level": risk_level,
                "merge_recommendation": recommendation,
            }

        base_head = subprocess.run(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if base_head.returncode != 0:
            return {
                "status": "blocked",
                "reason": "main_head_resolution_failed",
                "branch": branch,
                "risk_level": risk_level,
                "merge_recommendation": recommendation,
            }

        original_main_head = base_head.stdout.strip()

        if not original_main_head:
            return {
                "status": "blocked",
                "reason": "main_head_resolution_failed",
                "branch": branch,
                "risk_level": risk_level,
                "merge_recommendation": recommendation,
            }

        merge = subprocess.run(
            [
                "git",
                "merge",
                "--ff-only",
                branch,
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if merge.returncode != 0:
            return {
                "status": "blocked",
                "reason": "fast_forward_merge_failed",
                "branch": branch,
                "risk_level": risk_level,
                "merge_recommendation": recommendation,
            }

        push = subprocess.run(
            [
                "git",
                "push",
                "origin",
                "main",
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if push.returncode != 0:
            rollback = subprocess.run(
                [
                    "git",
                    "reset",
                    "--hard",
                    original_main_head,
                ],
                cwd=self.repository_root,
                text=True,
                capture_output=True,
                check=False,
            )

            if rollback.returncode != 0:
                return {
                    "status": "blocked",
                    "reason": "main_push_failed_rollback_failed",
                    "branch": branch,
                    "risk_level": risk_level,
                    "merge_recommendation": recommendation,
                }

            return {
                "status": "blocked",
                "reason": "main_push_failed",
                "branch": branch,
                "risk_level": risk_level,
                "merge_recommendation": recommendation,
                "local_main_rolled_back": True,
            }

        return {
            "status": "success",
            "reason": None,
            "branch": branch,
            "risk_level": risk_level,
            "merge_recommendation": recommendation,
            "merged_to_main": True,
            "changed_files": (
                self._changed_files_from_review(
                    review
                )
            ),
            "git_commit": self._git_commit(branch),
        }

    @staticmethod
    def _safe_output(text: str, limit: int = 4000) -> str:
        text = str(text or "")

        replacements = (
            "OPENAI_API_KEY",
            "API_KEY",
            "TOKEN",
            "PASSWORD",
            "SECRET",
        )

        upper = text.upper()
        if any(marker in upper for marker in replacements):
            return "[redacted-runtime-output]"

        return text[-limit:]

    def execute(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mission_name = self._mission_name(mission)
        except ValueError:
            return {
                "status": "blocked",
                "reason": "invalid_mission_name",
            }

        command = [
            sys.executable,
            "-m",
            "ai.mission_runner",
            mission_name,
        ]

        try:
            result = subprocess.run(
                command,
                cwd=self.agent_root,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            restored = self._restore_main()

            return {
                "status": "exhausted",
                "reason": "mission_timeout",
                "repository_restored": restored,
            }
        except OSError:
            restored = self._restore_main()

            return {
                "status": "blocked",
                "reason": "mission_runner_unavailable",
                "repository_restored": restored,
            }

        restored = self._restore_main()

        combined = "\n".join(
            part
            for part in (
                result.stdout,
                result.stderr,
            )
            if part
        )

        safe_output = self._safe_output(combined)

        if not restored:
            return {
                "status": "blocked",
                "reason": "repository_restore_failed",
                "returncode": result.returncode,
            }

        if result.returncode == 0:
            merge_result = self._review_and_merge(
                mission_name
            )

            if merge_result.get("status") == "success":
                metadata = self._mission_metadata(
                    mission_name
                )

                for key in (
                    "request_id",
                    "task_type",
                ):
                    value = metadata.get(key)

                    if value:
                        merge_result[key] = value

            merge_result["returncode"] = 0
            return merge_result

        if "SELF_HEALING_BLOCKED" in safe_output:
            status = "blocked"
            reason = "self_healing_blocked"
        elif "Mission must start from main" in safe_output:
            status = "blocked"
            reason = "unsafe_repository_state"
        elif "Repository is not clean" in safe_output:
            status = "blocked"
            reason = "dirty_repository"
        elif "Unsafe deliverable path" in safe_output:
            status = "blocked"
            reason = "unsafe_deliverable"
        elif "Mission path escapes" in safe_output:
            status = "blocked"
            reason = "unsafe_mission_path"
        else:
            status = "exhausted"
            reason = "mission_execution_failed"

        return {
            "status": status,
            "reason": reason,
            "returncode": result.returncode,
        }


__all__ = ["ProductionMissionController"]
