from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")


def _safe_id(value: str, field: str) -> str:
    value = str(value or "").strip()
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid_{field}")
    return value


def _git(repo: Path, *args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "output": "git_probe_failed"}

    output = (result.stdout or "").strip()
    if not output:
        output = (result.stderr or "").strip()
    return {
        "ok": result.returncode == 0,
        "output": output[:12000],
    }


def _dirty_entries(porcelain_output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw in str(porcelain_output or "").splitlines():
        if len(raw) < 4:
            continue
        entries.append({
            "status": raw[:2],
            "path": raw[3:][:500],
        })
        if len(entries) >= 50:
            break
    return entries


def _mission_metadata(repo: Path, mission_id: str) -> dict[str, Any]:
    path = repo / "agent" / "missions" / f"{mission_id}.md"
    if not path.is_file():
        return {"exists": False, "path": str(path)}

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"exists": True, "path": str(path), "readable": False}

    task_match = re.search(r"^Task Type:\s*(.+?)\s*$", text, re.MULTILINE)
    context_match = re.search(
        r"## Context\s*\n\s*```json\s*\n(.*?)\n```",
        text,
        re.DOTALL,
    )
    context: dict[str, Any] = {}
    if context_match:
        try:
            candidate = json.loads(context_match.group(1))
            if isinstance(candidate, dict):
                context = candidate
        except (TypeError, ValueError):
            pass

    deliverables = context.get("deliverables")
    if not isinstance(deliverables, list):
        deliverables = []

    return {
        "exists": True,
        "path": str(path),
        "readable": True,
        "task_type": task_match.group(1).strip() if task_match else None,
        "request_id": context.get("request_id"),
        "project_id": context.get("project_id"),
        "deliverables": [str(item) for item in deliverables[:50]],
        "context_keys": sorted(str(key) for key in context.keys()),
    }


def _runtime_artifacts(data_root: Path, mission_id: str) -> list[dict[str, Any]]:
    runtime_root = data_root / "runtime"
    if not runtime_root.is_dir():
        return []

    matches: list[dict[str, Any]] = []
    try:
        paths = runtime_root.rglob("*")
        for path in paths:
            if len(matches) >= 40:
                break
            if not path.is_file() or mission_id not in str(path):
                continue

            item: dict[str, Any] = {"path": str(path)}
            if path.suffix.lower() == ".json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        item["json_keys"] = sorted(str(k) for k in payload.keys())
                        for key in (
                            "status",
                            "state",
                            "reason",
                            "blocked_reason",
                            "phase",
                            "controller_status",
                            "queue_state",
                            "provider",
                            "provider_id",
                            "execution_provider",
                            "git_commit",
                        ):
                            value = payload.get(key)
                            if isinstance(value, (str, int, float, bool)) or value is None:
                                if key in payload:
                                    item[key] = value
                        state = payload.get("state")
                        if isinstance(state, dict):
                            item["checkpoint_state"] = {
                                str(k): v
                                for k, v in state.items()
                                if k in {
                                    "phase",
                                    "mission_id",
                                    "attempts_done",
                                    "max_retries",
                                    "controller_status",
                                    "queue_state",
                                    "reason",
                                }
                                and isinstance(v, (str, int, float, bool))
                            }
                except (OSError, ValueError, TypeError):
                    item["json_readable"] = False
            matches.append(item)
    except OSError:
        return matches

    return matches


def collect_mission_diagnostics(
    mission_id: str,
    *,
    repository_root: str | Path | None = None,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Collect read-only, bounded diagnostics for one MITIGATE mission."""
    mission_id = _safe_id(mission_id, "mission_id")
    repo = Path(
        repository_root
        or os.environ.get("MITIGATE_AI_REPOSITORY_ROOT")
        or "/srv/mitigate/mitigate-ai-platform"
    ).resolve()
    root = Path(
        data_root
        or os.environ.get("MITIGATE_AI_DATA_ROOT")
        or "/srv/mitigate/data"
    ).resolve()

    branch = _git(repo, "branch", "--show-current")
    porcelain = _git(repo, "status", "--porcelain", "--untracked-files=all")
    head = _git(repo, "rev-parse", "HEAD")
    branches = _git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads/agent/mission-*",
    )

    branch_matches: list[str] = []
    if branches.get("ok"):
        branch_matches = [
            line.strip()
            for line in str(branches.get("output") or "").splitlines()
            if mission_id in line
        ][:20]

    porcelain_output = str(porcelain.get("output") or "")
    clean = bool(porcelain.get("ok")) and not porcelain_output.strip()

    return {
        "mission_id": mission_id,
        "repository": {
            "available": repo.is_dir() and (repo / ".git").exists(),
            "path": str(repo),
            "branch": branch.get("output") if branch.get("ok") else None,
            "head": head.get("output") if head.get("ok") else None,
            "clean": clean,
            "dirty_entries": _dirty_entries(porcelain_output),
            "mission_branches": branch_matches,
        },
        "mission_artifact": _mission_metadata(repo, mission_id),
        "runtime_artifacts": _runtime_artifacts(root, mission_id),
    }


__all__ = ["collect_mission_diagnostics"]
