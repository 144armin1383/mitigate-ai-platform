from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict


class ReadOnlyInspectionExecutor:
    """
    Deterministic repository inspection executor.

    Security properties:
    - never executes user-provided shell text;
    - never writes repository files;
    - never commits, pushes, deploys, or restarts services;
    - only fixed git commands defined in this module are executed.
    """

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = Path(repository_root).resolve()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return completed.stdout.strip()

    def execute(
        self,
        mission_id: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        del context

        try:
            revision = self._git("rev-parse", "HEAD")
            branch = self._git("branch", "--show-current")
            porcelain = self._git("status", "--porcelain")
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "status": "exhausted",
                "provider": "read_only_inspection",
                "reason": f"inspection_failed:{type(exc).__name__}",
                "retryable": False,
                "changed_files": [],
                "mission_id": mission_id,
            }

        dirty_entries = [
            line
            for line in porcelain.splitlines()
            if line.strip()
        ]

        return {
            "status": "success",
            "provider": "read_only_inspection",
            "reason": "inspection_completed",
            "retryable": False,
            "changed_files": [],
            "mission_id": mission_id,
            "evidence": {
                "revision": revision,
                "branch": branch,
                "repository_clean": not dirty_entries,
                "dirty_entry_count": len(dirty_entries),
            },
        }
