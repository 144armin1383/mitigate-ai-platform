from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


_MISSION_DEF_RE = re.compile(r"^agent/missions/(m[0-9]+)\.md$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")


class HostRecoverySupervisor:
    """Restore safe canonical Git preconditions without becoming a code editor.

    The supervisor is intentionally narrow. It may quarantine only known
    runtime-generated, untracked mission definitions when an identical durable
    copy exists outside Git. Tracked modifications, deletions, renames and
    unrelated untracked files are never reset, deleted or moved automatically.
    """

    def __init__(
        self,
        *,
        repository_root: str | Path | None = None,
        data_root: str | Path | None = None,
    ) -> None:
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
        self.definition_root = self.data_root / "runtime" / "mission-definitions"
        self.recovery_root = self.data_root / "runtime" / "host-recovery"

    def _git_status(self) -> list[dict[str, str]]:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError("git_status_failed")
        entries: list[dict[str, str]] = []
        for raw in result.stdout.splitlines():
            if len(raw) < 4:
                continue
            entries.append({"status": raw[:2], "path": raw[3:]})
        return entries

    def _eligible_generated_definition(self, entry: dict[str, str]) -> tuple[bool, str | None]:
        if entry.get("status") != "??":
            return False, None
        rel = str(entry.get("path") or "").strip()
        match = _MISSION_DEF_RE.fullmatch(rel)
        if not match:
            return False, None
        mission_id = match.group(1)
        source = (self.repository_root / rel).resolve()
        durable = (self.definition_root / f"{mission_id}.md").resolve()
        if not source.is_file() or not durable.is_file():
            return False, mission_id
        try:
            if source.read_bytes() != durable.read_bytes():
                return False, mission_id
        except OSError:
            return False, mission_id
        return True, mission_id

    @staticmethod
    def _fingerprint(entries: list[dict[str, str]]) -> str:
        payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    def recover(self, mission_id: str) -> dict[str, Any]:
        mission_id = str(mission_id or "").strip()
        if not _SAFE_ID_RE.fullmatch(mission_id):
            raise ValueError("invalid_mission_id")
        if not (self.repository_root / ".git").exists():
            return {"ok": False, "action": "blocked", "reason": "canonical_repository_unavailable"}

        before = self._git_status()
        if not before:
            return {
                "ok": True,
                "action": "noop",
                "reason": "canonical_repository_already_clean",
                "repository_clean": True,
                "quarantined": [],
                "unresolved": [],
            }

        fingerprint = self._fingerprint(before)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        recovery_dir = self.recovery_root / f"{mission_id}-{stamp}-{fingerprint}"
        quarantined: list[str] = []
        unresolved: list[dict[str, str]] = []

        for entry in before:
            eligible, generated_mission_id = self._eligible_generated_definition(entry)
            if not eligible:
                unresolved.append(entry)
                continue
            rel = entry["path"]
            source = (self.repository_root / rel).resolve()
            target = (recovery_dir / rel).resolve()
            recovery_dir_resolved = recovery_dir.resolve()
            if recovery_dir_resolved != target and recovery_dir_resolved not in target.parents:
                unresolved.append(entry)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            quarantined.append(rel)

        after = self._git_status()
        clean = not after
        recovery_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "mission_id": mission_id,
            "timestamp": stamp,
            "fingerprint": fingerprint,
            "before": before,
            "quarantined": quarantined,
            "unresolved_before": unresolved,
            "after": after,
            "repository_clean": clean,
        }
        (recovery_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if clean:
            return {
                "ok": True,
                "action": "recovered",
                "reason": "generated_runtime_artifacts_quarantined",
                "repository_clean": True,
                "quarantined": quarantined,
                "unresolved": [],
                "recovery_dir": str(recovery_dir),
                "fingerprint": fingerprint,
            }

        return {
            "ok": False,
            "action": "blocked",
            "reason": "canonical_repository_contains_non_generated_changes",
            "repository_clean": False,
            "quarantined": quarantined,
            "unresolved": after[:50],
            "recovery_dir": str(recovery_dir),
            "fingerprint": fingerprint,
        }


__all__ = ["HostRecoverySupervisor"]
