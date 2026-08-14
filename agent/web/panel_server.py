from __future__ import annotations

import base64
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agent.web.external_runtime_probe import probe_external_runtimes


@dataclass(frozen=True)
class PanelConfig:
    host: str = "127.0.0.1"
    port: int = 8766
    runtime_base_url: str = "http://127.0.0.1:8765"
    project_id: str = "mitigate-ai-platform"
    username: str = "admin"
    password: str = ""
    api_token: str = ""

    def validate(self) -> None:
        if self.host in {"0.0.0.0", "::"}:
            raise ValueError("public_bind_not_allowed")
        if not self.password:
            raise ValueError("missing_panel_password")
        if not self.api_token:
            raise ValueError("missing_api_token")
        if not (1 <= int(self.port) <= 65535):
            raise ValueError("invalid_port")


class PanelServer:
    """Loopback-only API used by MITIGATE overlays inside Agent Canvas.

    This service intentionally has no standalone HTML control panel. User-facing
    MITIGATE controls are injected into Agent Canvas by the repository-managed
    Nginx overlay integration.
    """

    def __init__(self, config: PanelConfig) -> None:
        config.validate()
        self.config = config

    def _upstream(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, bytes, str]:
        url = self.config.runtime_base_url.rstrip("/") + path
        data = None
        headers = {"Authorization": f"Bearer {self.config.api_token}"}
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", "application/json"),
                )
        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                exc.read(),
                exc.headers.get("Content-Type", "application/json"),
            )
        except Exception as exc:
            body = json.dumps(
                {
                    "ok": False,
                    "status": 502,
                    "error": {
                        "code": "runtime_unavailable",
                        "message": type(exc).__name__,
                    },
                }
            ).encode("utf-8")
            return 502, body, "application/json"

    def _authorized(self, header: str | None) -> bool:
        if not header or not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(
                header[6:].strip(),
                validate=True,
            ).decode("utf-8")
            username, password = raw.split(":", 1)
        except Exception:
            return False
        return hmac.compare_digest(
            username,
            self.config.username,
        ) and hmac.compare_digest(password, self.config.password)

    def handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _headers(
                self,
                code: int,
                content_type: str,
                length: int,
            ) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Connection", "close")
                self.end_headers()

            def _write(
                self,
                code: int,
                body: bytes,
                content_type: str = "application/json; charset=utf-8",
            ) -> None:
                self._headers(code, content_type, len(body))
                self.wfile.write(body)
                self.close_connection = True

            def _json(self, code: int, value: dict[str, Any]) -> None:
                self._write(
                    code,
                    json.dumps(
                        value,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode("utf-8"),
                )

            def _require_auth(self) -> bool:
                if outer._authorized(self.headers.get("Authorization")):
                    return True
                body = b"Authentication required"
                self.send_response(401)
                self.send_header(
                    "WWW-Authenticate",
                    'Basic realm="MITIGATE AI", charset="UTF-8"',
                )
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True
                return False

            def _proxy(
                self,
                path: str,
                *,
                method: str = "GET",
                payload: dict[str, Any] | None = None,
            ) -> None:
                code, body, content_type = outer._upstream(
                    path,
                    method=method,
                    payload=payload,
                )
                self._write(code, body, content_type)

            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path == "/healthz":
                    self._json(200, {"ok": True, "status": 200})
                    return
                if not self._require_auth():
                    return
                if parsed.path in {"/", "/index.html"}:
                    self._json(
                        404,
                        {
                            "ok": False,
                            "error": {
                                "code": "standalone_panel_removed",
                                "message": "Use the MITIGATE controls inside Agent Canvas.",
                            },
                        },
                    )
                    return
                if parsed.path == "/api/health":
                    code, body, content_type = outer._upstream("/health/live")
                    self._write(code, body, content_type)
                    return
                if parsed.path == "/api/runtime":
                    self._proxy("/v1/runtime/status")
                    return
                if parsed.path == "/api/providers":
                    params = urllib.parse.parse_qs(parsed.query)
                    deep = params.get("deep", ["0"])[0] == "1"
                    updates = params.get("updates", ["1"])[0] != "0"
                    self._json(
                        200,
                        probe_external_runtimes(
                            deep=deep,
                            check_updates=updates,
                        ),
                    )
                    return
                if parsed.path == "/api/requests":
                    query = ("?" + parsed.query) if parsed.query else ""
                    self._proxy("/v1/requests" + query)
                    return
                if (
                    parsed.path.startswith("/api/requests/")
                    and parsed.path.endswith("/status")
                ):
                    request_id = parsed.path[
                        len("/api/requests/") : -len("/status")
                    ]
                    if not request_id or "/" in request_id:
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": {
                                    "code": "invalid_request_id",
                                    "message": "Invalid request id",
                                },
                            },
                        )
                        return
                    self._proxy(
                        "/v1/requests/"
                        + urllib.parse.quote(request_id, safe="")
                        + "/status"
                    )
                    return
                if parsed.path == "/api/executions":
                    query = ("?" + parsed.query) if parsed.query else ""
                    self._proxy("/v1/executions" + query)
                    return
                self._json(
                    404,
                    {
                        "ok": False,
                        "error": {
                            "code": "not_found",
                            "message": "Not found",
                        },
                    },
                )

            def do_POST(self) -> None:
                if not self._require_auth():
                    return
                self._json(
                    404,
                    {
                        "ok": False,
                        "error": {
                            "code": "not_found",
                            "message": "Not found",
                        },
                    },
                )

        return Handler

    def serve_forever(self) -> None:
        server = ThreadingHTTPServer(
            (self.config.host, self.config.port),
            self.handler(),
        )
        server.daemon_threads = True
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()


def build_config_from_env() -> PanelConfig:
    return PanelConfig(
        host=os.environ.get("MITIGATE_AI_PANEL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MITIGATE_AI_PANEL_PORT", "8766")),
        runtime_base_url=os.environ.get(
            "MITIGATE_AI_RUNTIME_BASE_URL",
            "http://127.0.0.1:8765",
        ),
        project_id=os.environ.get(
            "MITIGATE_PROJECT_ID",
            "mitigate-ai-platform",
        ),
        username=os.environ.get("MITIGATE_AI_PANEL_USERNAME", "admin"),
        password=os.environ.get("MITIGATE_AI_PANEL_PASSWORD", ""),
        api_token=os.environ.get("MITIGATE_AI_API_TOKEN", ""),
    )


__all__ = ["PanelConfig", "PanelServer", "build_config_from_env"]
