from __future__ import annotations

import os
import urllib.parse
from typing import Any

from agent.runtime.mission_diagnostics import collect_mission_diagnostics
from agent.runtime.runtime_mcp_server import (
    _runtime_api_request,
    _safe_identifier,
    mcp,
)


@mcp.tool()
def mitigate_mission_diagnostics(
    mission_id: str,
) -> dict[str, Any]:
    """Return bounded read-only evidence for diagnosing a MITIGATE mission.

    Combines the authoritative mission record with controlled repository,
    mission-artifact, branch and structured runtime-artifact observations.
    It never executes a mission, modifies Git state, or exposes arbitrary
    canonical-repository file content.
    """
    mission_id = _safe_identifier(
        mission_id,
        field="mission_id",
    )

    mission = _runtime_api_request(
        "/v1/missions/"
        + urllib.parse.quote(
            mission_id,
            safe="",
        ),
        method="GET",
    )

    diagnostics = collect_mission_diagnostics(
        mission_id,
        repository_root=os.environ.get(
            "MITIGATE_AI_REPOSITORY_ROOT"
        ),
        data_root=os.environ.get(
            "MITIGATE_AI_DATA_ROOT"
        ),
    )

    return {
        "ok": True,
        "mission": mission.get("data", mission),
        "diagnostics": diagnostics,
    }


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
