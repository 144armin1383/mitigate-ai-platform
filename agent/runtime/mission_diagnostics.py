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
    """Run a read-only Git probe with deterministic user/global configuration.

    Successful porcelain output is always taken from stdout only. Git warnings
    are retained separately as bounded diagnostic metadata and can never become
    repository status entries.
    """
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"

    try:
        result = subprocess.run(
            ["git", "-c", f"core.excludesFile={os.devnull}", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "ok": False,
            "output": "",
            "warning": "git_probe_failed",
        }

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    return {
        "ok": result.returncode == 0,
        "output": stdout[:12000],
        "warning": stderr[:4000] if stderr else "",
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


def _bounded_runtime_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose the failure facts an autonomous repair agent actually needs.

    This is intentionally bounded and allow-listed. It does not dump arbitrary
    mission context or secrets; it surfaces provider/result classification plus
    the already bounded stdout/stderr tails written by the runtime controller.
    """
    result: dict[str, Any] = {}
    for key in (
        "status",
        "failure_class",
        "reason",
        "provider",
        "runtime_status",
        "runtime_retryable",
        "attempts_done",
        "max_retries",
        "task_type",
        "request_id",
    ):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            if key in payload:
                result[key] = value

    runtime_evidence = payload.get("runtime_evidence")
    if not isinstance(runtime_evidence, dict):
        return result

    provider_metadata = runtime_evidence.get("provider_metadata")
    if isinstance(provider_metadata, dict):
        metadata: dict[str, Any] = {}
        for key in (
            "error_code",
            "mode",
            "runtime",
            "returncode",
            "working_directory",
            "python_executable",
            "virtual_env",
        ):
            value = provider_metadata.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                if key in provider_metadata:
                    metadata[key] = value

        for key in ("stdout_tail", "stderr_tail"):
            value = provider_metadata.get(key)
            if isinstance(value, str):
                metadata[key] = value[-4000:]

        site_packages = provider_metadata.get("site_packages")
        if isinstance(site_packages, list):
            metadata["site_packages"] = [str(item)[:1000] for item in site_packages[:20]]

        preflight = provider_metadata.get("runtime_preflight")
        if isinstance(preflight, dict):
            metadata["runtime_preflight"] = {
                str(k): v
                for k, v in preflight.items()
                if k in {
                    "executable",
                    "prefix",
                    "base_prefix",
                    "sitepackages",
                    "openhands_spec",
                }
                and isinstance(v, (str, int, float, bool, list, type(None)))
            }

        if metadata:
            result["provider_metadata"] = metadata

    diagnostics = runtime_evidence.get("diagnostics")
    if isinstance(diagnostics, list):
        result["diagnostics"] = [str(item)[:1000] for item in diagnostics[:20]]
    return result


def _failure_evidence(data_root: Path, mission_id: str) -> dict[str, Any]:
    path = data_root / "runtime" / "failure-evidence" / f"{mission_id}.json"
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"exists": True, "path": str(path), "readable": False}
    if not isinstance(payload, dict):
        return {"exists": True, "path": str(path), "readable": False}
    return {
        "exists": True,
        "path": str(path),
        "readable": True,
        **_bounded_runtime_evidence(payload),
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
    git_warnings = [
        str(item.get("warning") or "")
        for item in (branch, porcelain, head, branches)
        if str(item.get("warning") or "").strip()
    ]

    return {
        "mission_id": mission_id,
        "repository": {
            "available": repo.is_dir() and (repo / ".git").exists(),
            "path": str(repo),
            "branch": branch.get("output") if branch.get("ok") else None,
            "head": head.get("output") if head.get("ok") else None,
            "clean": clean,
            "dirty_entries": _dirty_entries(porcelain_output),
            "git_warnings": git_warnings[:10],
            "mission_branches": branch_matches,
        },
        "mission_artifact": _mission_metadata(repo, mission_id),
        "failure_evidence": _failure_evidence(root, mission_id),
        "runtime_artifacts": _runtime_artifacts(root, mission_id),
    }


__all__ = ["collect_mission_diagnostics"]
