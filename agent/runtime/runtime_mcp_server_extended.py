from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any

from agent.runtime.autonomous_mission_diagnostics import (
    collect_autonomous_mission_diagnostics,
)
from agent.runtime.host_recovery_supervisor import HostRecoverySupervisor
from agent.runtime.runtime_mcp_server import (
    _runtime_api_request,
    _safe_identifier,
    mitigate_submit_mission,
    mcp,
)


_RECOVERY_MARKER_RE = re.compile(
    r"\[MITIGATE_RECOVERY_ROOT=([A-Za-z0-9_-]{1,160});DEPTH=([0-9]+)\]"
)


def _infer_task_type(message: str) -> str:
    text = str(message or "").lower()
    rules = (
        ("deployment", ("deploy", "release", "production rollout")),
        ("security", ("security", "vulnerability", "permission", "secret")),
        ("testing", ("test", "regression", "validation")),
        ("documentation", ("document", "assessment", "architecture report", "readme")),
        ("frontend", ("frontend", "ui", "css", "react", "component")),
        ("database", ("database", "schema", "migration", "sql")),
        ("infrastructure", ("systemd", "nginx", "server", "infrastructure", "runtime")),
        ("wordpress", ("wordpress", "woocommerce", "plugin", "theme")),
        ("seo", ("seo", "sitemap", "robots", "canonical url")),
        ("github", ("github", "branch", "pull request", "workflow")),
    )
    for task_type, markers in rules:
        if any(marker in text for marker in markers):
            return task_type
    return "backend"


def _recovery_depth_limit() -> int:
    try:
        value = int(os.environ.get("MITIGATE_AI_RECOVERY_CHAIN_LIMIT", "2"))
    except ValueError:
        value = 2
    return max(1, min(value, 3))


def _recovery_lineage(objective: str, mission_id: str) -> tuple[str, int]:
    match = _RECOVERY_MARKER_RE.search(str(objective or ""))
    if not match:
        return mission_id, 0
    return match.group(1), int(match.group(2))


def _with_recovery_marker(objective: str, *, root: str, depth: int) -> str:
    text = _RECOVERY_MARKER_RE.sub("", str(objective or "")).strip()
    return f"{text}\n\n[MITIGATE_RECOVERY_ROOT={root};DEPTH={int(depth)}]"


def _valid_task_type(task_type: str, objective: str) -> str:
    allowed = {
        "inspection", "general", "wordpress", "backend", "frontend", "api",
        "testing", "documentation", "infrastructure", "deployment", "seo",
        "content", "security", "database", "github", "fullstack", "bugfix",
        "maintenance", "refactor", "test", "tests",
    }
    value = str(task_type or "").strip().lower()
    return value if value in allowed else _infer_task_type(objective)


@mcp.tool()
def mitigate_autonomous_task(message: str) -> dict[str, Any]:
    """Accept natural-language work and start governed MITIGATE execution."""
    message = str(message or "").strip()
    if not message:
        raise ValueError("invalid_mission_message")
    task_type = _infer_task_type(message)
    result = mitigate_submit_mission(message, task_type=task_type)
    result["autonomous"] = True
    result["inferred_task_type"] = task_type
    return result


@mcp.tool()
def mitigate_mission_diagnostics(mission_id: str) -> dict[str, Any]:
    """Return bounded evidence for autonomous MITIGATE failure diagnosis."""
    mission_id = _safe_identifier(mission_id, field="mission_id")
    mission = _runtime_api_request(
        "/v1/missions/" + urllib.parse.quote(mission_id, safe=""),
        method="GET",
    )
    diagnostics = collect_autonomous_mission_diagnostics(
        mission_id,
        repository_root=os.environ.get("MITIGATE_AI_REPOSITORY_ROOT"),
        data_root=os.environ.get("MITIGATE_AI_DATA_ROOT"),
    )
    return {
        "ok": True,
        "mission": mission.get("data", mission),
        "diagnostics": diagnostics,
    }


@mcp.tool()
def mitigate_autonomous_recovery(mission_id: str) -> dict[str, Any]:
    """Diagnose a failed mission and take one bounded safe recovery action.

    Recovery is finite. MITIGATE may retry normal execution, quarantine only
    provably generated runtime artifacts, or submit a governed repair mission.
    Unknown canonical changes, credentials, billing, approvals and destructive
    boundaries stop with precise evidence rather than looping indefinitely.
    """
    mission_id = _safe_identifier(mission_id, field="mission_id")
    status_payload = _runtime_api_request(
        "/v1/missions/" + urllib.parse.quote(mission_id, safe=""),
        method="GET",
    )
    mission = status_payload.get("data", status_payload)
    state = str(mission.get("state") or "").lower() if isinstance(mission, dict) else ""
    diagnostics = collect_autonomous_mission_diagnostics(
        mission_id,
        repository_root=os.environ.get("MITIGATE_AI_REPOSITORY_ROOT"),
        data_root=os.environ.get("MITIGATE_AI_DATA_ROOT"),
    )

    if state in {"pending", "running", "retrying"}:
        return {
            "ok": True,
            "action": "wait",
            "mission_id": mission_id,
            "state": state,
            "diagnostics": diagnostics,
        }

    failure = diagnostics.get("failure_evidence") or {}
    reason = str(failure.get("reason") or "").lower()
    durable = diagnostics.get("durable_mission_definition") or {}
    objective = str(durable.get("objective") or "").strip()
    task_type = _valid_task_type(str(durable.get("task_type") or "backend"), objective)
    root_mission_id, depth = _recovery_lineage(objective, mission_id)
    depth_limit = _recovery_depth_limit()

    repository = diagnostics.get("repository") or {}
    if repository.get("clean") is False or "canonical_repository_not_clean" in reason:
        supervisor = HostRecoverySupervisor(
            repository_root=os.environ.get("MITIGATE_AI_REPOSITORY_ROOT"),
            data_root=os.environ.get("MITIGATE_AI_DATA_ROOT"),
        )
        host_recovery = supervisor.recover(mission_id)
        if not host_recovery.get("ok"):
            return {
                "ok": True,
                "action": "terminal_blocker",
                "mission_id": mission_id,
                "root_mission_id": root_mission_id,
                "state": state,
                "reason": host_recovery.get("reason"),
                "host_recovery": host_recovery,
                "diagnostics": diagnostics,
            }
        if not objective:
            return {
                "ok": True,
                "action": "host_recovered_diagnostics_only",
                "mission_id": mission_id,
                "root_mission_id": root_mission_id,
                "host_recovery": host_recovery,
                "diagnostics": diagnostics,
            }
        if depth >= depth_limit:
            return {
                "ok": True,
                "action": "terminal_blocker",
                "mission_id": mission_id,
                "root_mission_id": root_mission_id,
                "state": state,
                "reason": "autonomous_recovery_chain_exhausted",
                "recovery_depth": depth,
                "recovery_depth_limit": depth_limit,
                "host_recovery": host_recovery,
                "diagnostics": diagnostics,
            }
        resumed = mitigate_submit_mission(
            _with_recovery_marker(
                objective,
                root=root_mission_id,
                depth=depth + 1,
            ),
            task_type=task_type,
        )
        return {
            "ok": True,
            "action": "host_recovered_mission_resubmitted",
            "failed_mission_id": mission_id,
            "root_mission_id": root_mission_id,
            "recovery_depth": depth + 1,
            "recovery_depth_limit": depth_limit,
            "host_recovery": host_recovery,
            "resubmitted": resumed,
            "diagnostics": diagnostics,
        }

    protected_markers = (
        "quota_exhausted",
        "insufficient_quota",
        "credentials_unavailable",
        "approval",
        "permission",
        "runtime_changed_paths_outside_authorized_scope",
    )
    if any(marker in reason for marker in protected_markers):
        return {
            "ok": True,
            "action": "external_or_policy_action_required",
            "mission_id": mission_id,
            "root_mission_id": root_mission_id,
            "state": state,
            "reason": reason[:1000],
            "diagnostics": diagnostics,
        }

    if not objective:
        return {
            "ok": True,
            "action": "diagnostics_only",
            "mission_id": mission_id,
            "root_mission_id": root_mission_id,
            "state": state,
            "diagnostics": diagnostics,
        }

    if depth >= depth_limit:
        return {
            "ok": True,
            "action": "terminal_blocker",
            "mission_id": mission_id,
            "root_mission_id": root_mission_id,
            "state": state,
            "reason": "autonomous_recovery_chain_exhausted",
            "recovery_depth": depth,
            "recovery_depth_limit": depth_limit,
            "diagnostics": diagnostics,
        }

    repair_message = (
        "Autonomously diagnose and resolve the governed MITIGATE failure for "
        f"mission {mission_id}. Preserve MITIGATE Core authority and disposable "
        "workspace isolation. Do not bypass policy or edit canonical main directly. "
        "Fix the underlying implementation or runtime integration issue when safe, "
        "add regression coverage, validate the result, then complete the original "
        "objective. Original objective:\n\n"
        + _with_recovery_marker(
            objective,
            root=root_mission_id,
            depth=depth + 1,
        )
    )
    submitted = mitigate_submit_mission(repair_message, task_type=task_type)
    return {
        "ok": True,
        "action": "repair_mission_submitted",
        "failed_mission_id": mission_id,
        "root_mission_id": root_mission_id,
        "failed_state": state,
        "recovery_depth": depth + 1,
        "recovery_depth_limit": depth_limit,
        "repair": submitted,
        "diagnostics": diagnostics,
    }


if __name__ == "__main__":
    host = os.environ.get("MITIGATE_MCP_HOST", "172.18.0.1")
    port = int(os.environ.get("MITIGATE_MCP_PORT", "8771"))
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
