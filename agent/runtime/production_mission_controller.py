from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


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

    def _restore_main(self) -> bool:
        result = subprocess.run(
            ["git", "switch", "main"],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

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
            return {
                "status": "success",
                "reason": None,
                "returncode": 0,
            }

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
