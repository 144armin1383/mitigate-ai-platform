from __future__ import annotations

import os
import urllib.parse
from typing import Any

from agent.runtime.autonomous_mission_diagnostics import (
    collect_autonomous_mission_diagnostics,
)
from agent.runtime.runtime_mcp_server import (
    _runtime_api_request,
    _safe_identifier,
    mitigate_submit_mission,
    mcp,
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


@mcp.tool()
def mitigate_autonomous_task(message: str) -> dict[str, Any]:
    """Accept a natural-language MITIGATE task and start governed execution.

    The caller does not need to choose a runtime, task type, workspace, mission
    identifier or recovery procedure. MITIGATE infers the task class and keeps
    policy, Git, workspace and runtime authority.
    """
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
    """Classify a failed mission and take the next safe governed action.

    External requirements and policy/security boundaries are never bypassed.
    Retryable or implementation failures can be converted into a new governed
    mission without requiring the user to write recovery prompts or commands.
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
    task_type = str(durable.get("task_type") or "backend").strip().lower()

    protected_markers = (
        "quota_exhausted",
        "insufficient_quota",
        "credentials_unavailable",
        "scope",
        "canonical_repository_not_clean",
        "approval",
        "permission",
    )
    if any(marker in reason for marker in protected_markers):
        return {
            "ok": True,
            "action": "external_or_policy_action_required",
            "mission_id": mission_id,
            "state": state,
            "reason": reason[:1000],
            "diagnostics": diagnostics,
        }

    if not objective:
        return {
            "ok": True,
            "action": "diagnostics_only",
            "mission_id": mission_id,
            "state": state,
            "diagnostics": diagnostics,
        }

    repair_message = (
        "Autonomously diagnose and resolve the governed MITIGATE failure for "
        f"mission {mission_id}. Preserve MITIGATE Core authority and disposable "
        "workspace isolation. Do not bypass policy or edit canonical main directly. "
        "Fix the underlying implementation or runtime integration issue when safe, "
        "add regression coverage, validate the result, then complete the original "
        "objective. Original objective:\n\n" + objective
    )
    if task_type not in {
        "inspection", "general", "wordpress", "backend", "frontend", "api",
        "testing", "documentation", "infrastructure", "deployment", "seo",
        "content", "security", "database", "github", "fullstack", "bugfix",
        "maintenance", "refactor", "test", "tests",
    }:
        task_type = _infer_task_type(objective)

    submitted = mitigate_submit_mission(repair_message, task_type=task_type)
    return {
        "ok": True,
        "action": "repair_mission_submitted",
        "failed_mission_id": mission_id,
        "failed_state": state,
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
