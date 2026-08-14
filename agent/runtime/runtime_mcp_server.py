from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server import MCPServer


GATEWAY_URL = os.environ.get(
    "MITIGATE_RUNTIME_GATEWAY_URL",
    "http://127.0.0.1:8770",
).rstrip("/")

GATEWAY_TOKEN = os.environ.get(
    "MITIGATE_RUNTIME_GATEWAY_TOKEN",
    "",
).strip()

RUNTIME_API_URL = os.environ.get(
    "MITIGATE_AI_RUNTIME_BASE_URL",
    "http://127.0.0.1:8765",
).rstrip("/")

RUNTIME_API_TOKEN = os.environ.get(
    "MITIGATE_AI_API_TOKEN",
    "",
).strip()

PROJECT_ID = os.environ.get(
    "MITIGATE_PROJECT_ID",
    os.environ.get(
        "MITIGATE_AI_DEFAULT_PROJECT_ID",
        "mitigate-ai-platform",
    ),
).strip() or "mitigate-ai-platform"

MISSION_TASK_TYPES = frozenset(
    {
        "inspection",
        "general",
        "wordpress",
        "backend",
        "frontend",
        "api",
        "testing",
        "documentation",
        "infrastructure",
        "deployment",
        "seo",
        "content",
        "security",
        "database",
        "github",
        "fullstack",
        "bugfix",
        "maintenance",
        "refactor",
        "test",
        "tests",
    }
)


def _gateway_request(
    path: str,
    *,
    method: str = "GET",
) -> dict[str, Any]:
    if not GATEWAY_TOKEN:
        raise RuntimeError(
            "MITIGATE_RUNTIME_GATEWAY_TOKEN is missing"
        )

    request = urllib.request.Request(
        f"{GATEWAY_URL}{path}",
        method=method,
        headers={
            "Authorization": (
                f"Bearer {GATEWAY_TOKEN}"
            ),
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=75,
        ) as response:
            payload = json.load(response)

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(
            "utf-8",
            "replace",
        )[:1000]

        raise RuntimeError(
            f"gateway_http_{exc.code}:{detail}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"gateway_unreachable:{exc.reason}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            "gateway_invalid_response"
        )

    return payload


def _runtime_api_request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not RUNTIME_API_TOKEN:
        raise RuntimeError(
            "MITIGATE_AI_API_TOKEN is missing"
        )

    data = None
    headers = {
        "Authorization": f"Bearer {RUNTIME_API_TOKEN}",
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{RUNTIME_API_URL}{path}",
        data=data,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            result = json.load(response)

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(
            "utf-8",
            "replace",
        )[:1500]
        raise RuntimeError(
            f"runtime_api_http_{exc.code}:{detail}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"runtime_api_unreachable:{exc.reason}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "runtime_api_invalid_response"
        )

    return result


def _new_request_id() -> str:
    stamp = dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    return (
        f"canvas-{stamp}-{secrets.token_hex(3)}"
    )


def _safe_identifier(value: str, *, field: str) -> str:
    value = str(value or "").strip()
    if (
        not value
        or len(value) > 160
        or not all(
            ch.isalnum() or ch in "-_"
            for ch in value
        )
    ):
        raise ValueError(f"invalid_{field}")
    return value


def _explicit_read_only_inspection(message: str) -> bool:
    """Recognize only high-confidence read-only inspection requests."""
    text = " ".join(str(message or "").lower().split())
    has_read_only = "read-only" in text or "read only" in text
    has_inspection = any(
        marker in text
        for marker in (
            "inspection",
            "inspect the repository",
            "inspect this repository",
            "inspect repository",
        )
    )
    forbids_changes = any(
        marker in text
        for marker in (
            "do not modify any files",
            "do not modify files",
            "do not change any files",
            "do not change files",
            "without modifying any files",
            "without modifying files",
        )
    )
    writable_intent = any(
        marker in text
        for marker in (
            "fix the bug",
            "fix this bug",
            "implement",
            "modify the",
            "change the",
            "update the",
            "create a file",
            "delete a file",
        )
    )
    return has_read_only and has_inspection and forbids_changes and not writable_intent


def _effective_task_type(message: str, task_type: str) -> str:
    """Correct the generic MCP default only for explicit read-only inspection."""
    value = str(task_type or "").strip().lower()
    if value == "backend" and _explicit_read_only_inspection(message):
        return "inspection"
    return value


mcp = MCPServer(
    "MITIGATE Runtime Gateway",
    instructions=(
        "MITIGATE Core is the authority for software-engineering missions, "
        "planning, policy, approvals, mission state, Git governance and "
        "runtime routing. Use mitigate_submit_mission for coding, bug-fix, "
        "maintenance, testing and other repository work instead of editing "
        "the local Agent Canvas conversation workspace. Use the request and "
        "mission status tools to follow execution. Runtime verification tools "
        "remain read-only. These tools do not provide arbitrary host shell "
        "access or direct canonical-repository access."
    ),
)


@mcp.tool()
def mitigate_runtime_status() -> dict[str, Any]:
    """Return availability and versions of MITIGATE runtimes."""
    return _gateway_request(
        "/v1/status",
        method="GET",
    )


@mcp.tool()
def mitigate_openclaw_verify() -> dict[str, Any]:
    """Run the approved read-only OpenClaw MCP status verification."""
    return _gateway_request(
        "/v1/openclaw/verify",
        method="POST",
    )


@mcp.tool()
def mitigate_ruflo_verify() -> dict[str, Any]:
    """Run the approved read-only Ruflo doctor/benchmark verification."""
    return _gateway_request(
        "/v1/ruflo/verify",
        method="POST",
    )


@mcp.tool()
def mitigate_submit_mission(
    message: str,
    task_type: str = "backend",
) -> dict[str, Any]:
    """Submit repository work to MITIGATE Core for governed mission execution.

    Use this tool for software-engineering work requested from Agent Canvas.
    MITIGATE Core, not the Canvas conversation, owns planning, provider routing,
    disposable workspace creation, Git governance, execution and reporting.
    """
    message = str(message or "").strip()
    task_type = _effective_task_type(message, task_type)

    if not message or len(message) > 60000:
        raise ValueError("invalid_mission_message")
    if task_type not in MISSION_TASK_TYPES:
        raise ValueError("invalid_mission_task_type")

    request_id = _new_request_id()
    payload = {
        "request_id": request_id,
        "project_id": PROJECT_ID,
        "conversation_id": "agent-canvas-mcp",
        "user_message": message,
        "upload_ids": [],
        "requested_task_type": task_type,
        "created_at": dt.datetime.now(
            dt.timezone.utc
        ).replace(microsecond=0).isoformat().replace(
            "+00:00",
            "Z",
        ),
    }

    result = _runtime_api_request(
        "/v1/requests",
        method="POST",
        payload=payload,
    )

    data = result.get("data")
    if not isinstance(data, dict):
        data = {}

    return {
        "ok": bool(result.get("ok")),
        "request_id": data.get(
            "request_id",
            result.get("request_id", request_id),
        ),
        "project_id": data.get(
            "project_id",
            PROJECT_ID,
        ),
        "task_type": data.get(
            "task_type",
            task_type,
        ),
        "mission_ids": data.get(
            "mission_ids",
            [],
        ),
        "provider_id": data.get("provider_id"),
        "model_id": data.get("model_id"),
        "plan_id": data.get("plan_id"),
        "plan_summary": data.get("plan_summary"),
        "warning": data.get("warning"),
        "status": result.get("status", 202),
    }


@mcp.tool()
def mitigate_request_status(
    request_id: str,
) -> dict[str, Any]:
    """Return MITIGATE Core status and execution evidence for a request."""
    request_id = _safe_identifier(
        request_id,
        field="request_id",
    )
    return _runtime_api_request(
        "/v1/requests/"
        + urllib.parse.quote(
            request_id,
            safe="",
        )
        + "/status",
        method="GET",
    )


@mcp.tool()
def mitigate_mission_status(
    mission_id: str,
) -> dict[str, Any]:
    """Return the authoritative MITIGATE mission record by mission id."""
    mission_id = _safe_identifier(
        mission_id,
        field="mission_id",
    )
    return _runtime_api_request(
        "/v1/missions/"
        + urllib.parse.quote(
            mission_id,
            safe="",
        ),
        method="GET",
    )


if __name__ == "__main__":
    host = os.environ.get(
        "MITIGATE_MCP_HOST",
        "172.18.0.1",
    )

    port = int(
        os.environ.get(
            "MITIGATE_MCP_PORT",
            "8771",
        )
    )

    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
