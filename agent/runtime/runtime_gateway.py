from __future__ import annotations

import argparse
import hmac
import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent.execution.openclaw_adapter import OpenClawRuntimeAdapter
from agent.execution.ruflo_adapter import RufloRuntimeAdapter
from agent.execution.runtime_adapter import ExecutionRequest


class RuntimeGatewayCore:
    def __init__(
        self,
        *,
        repository_root: Path,
        runtime_root: Path,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.runtime_root = runtime_root.resolve()

        npm_bin = (
            self.runtime_root
            / "npm"
            / "node_modules"
            / ".bin"
        )

        self.openclaw = OpenClawRuntimeAdapter(
            binary=str(npm_bin / "openclaw")
        )

        self.ruflo = RufloRuntimeAdapter(
            binary=str(npm_bin / "ruflo")
        )

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "providers": {
                "openclaw": dict(
                    self.openclaw.healthcheck()
                ),
                "ruflo": dict(
                    self.ruflo.healthcheck()
                ),
            },
        }

    def verify_openclaw(self) -> dict[str, Any]:
        request = ExecutionRequest(
            request_id="gateway-openclaw-verify",
            mission_id="gateway-openclaw-verify",
            objective=(
                "Perform read-only OpenClaw MCP status "
                "verification."
            ),
            repository_root=str(self.repository_root),
            base_revision="main",
            timeout_seconds=60,
            metadata={
                "openclaw_capability_task": True,
                "openclaw_action": "mcp_status",
            },
        )

        result = self.openclaw.execute(request)

        return self._result_payload(result)

    def verify_ruflo(self) -> dict[str, Any]:
        request = ExecutionRequest(
            request_id="gateway-ruflo-verify",
            mission_id="gateway-ruflo-verify",
            objective=(
                "Perform read-only Ruflo doctor "
                "verification."
            ),
            repository_root=str(self.repository_root),
            base_revision="main",
            timeout_seconds=60,
            metadata={
                "benchmark_mode": True,
            },
        )

        result = self.ruflo.execute(request)

        return self._result_payload(result)

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        evidence = result.evidence

        return {
            "provider": result.provider,
            "status": result.status.value,
            "retryable": bool(result.retryable),
            "reason": result.reason,
            "evidence": {
                "summary": evidence.summary,
                "provider_run_id": (
                    evidence.provider_run_id
                ),
                "provider_metadata": dict(
                    evidence.provider_metadata
                ),
            },
        }


class RuntimeGatewayHandler(BaseHTTPRequestHandler):
    server_version = "MITIGATE-Runtime-Gateway/1"

    @property
    def gateway(self) -> RuntimeGatewayCore:
        return self.server.gateway  # type: ignore[attr-defined]

    @property
    def token(self) -> str:
        return self.server.gateway_token  # type: ignore[attr-defined]

    def log_message(
        self,
        fmt: str,
        *args: Any,
    ) -> None:
        print(
            "%s - %s"
            % (
                self.address_string(),
                fmt % args,
            ),
            flush=True,
        )

    def _authorized(self) -> bool:
        auth = self.headers.get(
            "Authorization",
            "",
        )

        expected = f"Bearer {self.token}"

        return hmac.compare_digest(
            auth,
            expected,
        )

    def _json(
        self,
        status: int,
        payload: dict[str, Any],
    ) -> None:
        raw = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json",
        )
        self.send_header(
            "Content-Length",
            str(len(raw)),
        )
        self.send_header(
            "Cache-Control",
            "no-store",
        )
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": (
                        "mitigate-runtime-gateway"
                    ),
                },
            )
            return

        if not self._authorized():
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "ok": False,
                    "error": "unauthorized",
                },
            )
            return

        if self.path == "/v1/status":
            self._json(
                HTTPStatus.OK,
                self.gateway.status(),
            )
            return

        self._json(
            HTTPStatus.NOT_FOUND,
            {
                "ok": False,
                "error": "not_found",
            },
        )

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "ok": False,
                    "error": "unauthorized",
                },
            )
            return

        if self.headers.get(
            "Content-Length",
            "0",
        ) not in {"", "0"}:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": (
                        "request_body_not_supported"
                    ),
                },
            )
            return

        if self.path == "/v1/openclaw/verify":
            result = (
                self.gateway.verify_openclaw()
            )

        elif self.path == "/v1/ruflo/verify":
            result = (
                self.gateway.verify_ruflo()
            )

        else:
            self._json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "not_found",
                },
            )
            return

        code = (
            HTTPStatus.OK
            if result.get("status")
            == "succeeded"
            else HTTPStatus.BAD_GATEWAY
        )

        self._json(
            code,
            result,
        )


class RuntimeGatewayServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        gateway: RuntimeGatewayCore,
        token: str,
    ) -> None:
        super().__init__(
            address,
            RuntimeGatewayHandler,
        )

        self.gateway = gateway
        self.gateway_token = token


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        default=os.environ.get(
            "MITIGATE_RUNTIME_GATEWAY_HOST",
            "127.0.0.1",
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.environ.get(
                "MITIGATE_RUNTIME_GATEWAY_PORT",
                "8770",
            )
        ),
    )

    args = parser.parse_args()

    token = os.environ.get(
        "MITIGATE_RUNTIME_GATEWAY_TOKEN",
        "",
    ).strip()

    if not token:
        raise SystemExit(
            "MITIGATE_RUNTIME_GATEWAY_TOKEN "
            "is required"
        )

    repository_root = Path(
        os.environ.get(
            "MITIGATE_ROOT",
            "/srv/mitigate/mitigate-ai-platform",
        )
    )

    runtime_root = Path(
        os.environ.get(
            "MITIGATE_EXTERNAL_RUNTIME_ROOT",
            "/srv/mitigate/external-runtimes",
        )
    )

    gateway = RuntimeGatewayCore(
        repository_root=repository_root,
        runtime_root=runtime_root,
    )

    server = RuntimeGatewayServer(
        (args.host, args.port),
        gateway,
        token,
    )

    print(
        (
            "MITIGATE_RUNTIME_GATEWAY=READY "
            f"host={args.host} "
            f"port={args.port}"
        ),
        flush=True,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
