from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent.runtime.mission_diagnostics import collect_mission_diagnostics


def _definition_metadata(data_root: Path, mission_id: str) -> dict[str, Any]:
    path = data_root / "runtime" / "mission-definitions" / f"{mission_id}.md"
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"exists": True, "path": str(path), "readable": False}

    task = re.search(r"^Task Type:\s*(.+?)\s*$", text, re.MULTILINE)
    request = re.search(r"^Request ID:\s*(.+?)\s*$", text, re.MULTILINE)
    objective = re.search(
        r"## Objective\s*\n\s*(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL,
    )
    return {
        "exists": True,
        "path": str(path),
        "readable": True,
        "task_type": task.group(1).strip() if task else None,
        "request_id": request.group(1).strip() if request else None,
        "objective": (objective.group(1).strip()[:12000] if objective else None),
    }


def _failure_evidence(data_root: Path, mission_id: str) -> dict[str, Any]:
    path = data_root / "runtime" / "failure-evidence" / f"{mission_id}.json"
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"exists": True, "path": str(path), "readable": False}
    if not isinstance(value, dict):
        return {"exists": True, "path": str(path), "readable": False}
    allowed = {
        key: value.get(key)
        for key in (
            "mission_id",
            "status",
            "reason",
            "provider",
            "failure_class",
            "request_id",
            "task_type",
        )
        if key in value
    }
    return {"exists": True, "path": str(path), "readable": True, **allowed}


def collect_autonomous_mission_diagnostics(
    mission_id: str,
    *,
    repository_root: str | Path | None = None,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(
        data_root
        or os.environ.get("MITIGATE_AI_DATA_ROOT")
        or "/srv/mitigate/data"
    ).expanduser().resolve()
    result = collect_mission_diagnostics(
        mission_id,
        repository_root=repository_root,
        data_root=root,
    )
    result["durable_mission_definition"] = _definition_metadata(root, mission_id)
    result["failure_evidence"] = _failure_evidence(root, mission_id)
    return result


__all__ = ["collect_autonomous_mission_diagnostics"]
