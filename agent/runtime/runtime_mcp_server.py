from __future__ import annotations

import json
import os
import urllib.error
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


mcp = MCPServer(
    "MITIGATE Runtime Gateway",
    instructions=(
        "These tools provide controlled access to "
        "MITIGATE-managed execution runtimes. "
        "Use them when the user explicitly requests "
        "OpenClaw, Ruflo, or MITIGATE runtime status. "
        "They do not provide arbitrary host shell access."
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
