from __future__ import annotations

import argparse
import datetime as _dt
import hmac
import json
import os
import signal
import socket
import sys
import threading
from dataclasses import dataclass, field, fields
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Deque, Dict, List, MutableMapping, Optional, Tuple
from collections import deque
from urllib.parse import urlsplit

# Types
TokenResolver = Callable[[], Optional[str]]


@dataclass(slots=True)
class RuntimeAPIConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    request_body_limit_bytes: int = 1048576
    response_body_limit_bytes: int = 1048576
    request_timeout_seconds: int = 30
    graceful_shutdown_timeout_seconds: int = 15
    enable_lifecycle_endpoints: bool = False
    # Authentication configuration reference, e.g., environment variable name.
    auth_token_reference: Optional[str] = None

    def validate(self) -> None:
        # Host validation
        if not isinstance(self.host, str) or not self.host:
            raise ValueError("invalid_host")
        # Reject public wildcards
        if self.host in ("0.0.0.0", "::"):
            raise ValueError("public_wildcard_host_not_allowed")
        try:
            # Validate it is a valid IP or hostname; do not resolve here
            # Basic check: no spaces and reasonable length
            if any(c.isspace() for c in self.host) or len(self.host) > 255:
                raise ValueError
        except Exception as e:  # pragma: no cover - defensive
            raise ValueError("invalid_host") from e

        # Port validation
        if not isinstance(self.port, int) or self.port < 0 or self.port > 65535:
            raise ValueError("invalid_port")

        # Limits validation
        if not isinstance(self.request_body_limit_bytes, int) or self.request_body_limit_bytes <= 0:
            raise ValueError("invalid_request_body_limit")
        if not isinstance(self.response_body_limit_bytes, int) or self.response_body_limit_bytes <= 0:
            raise ValueError("invalid_response_body_limit")

        # Timeouts validation
        if not isinstance(self.request_timeout_seconds, int) or self.request_timeout_seconds <= 0:
            raise ValueError("invalid_request_timeout")
        if (
            not isinstance(self.graceful_shutdown_timeout_seconds, int)
            or self.graceful_shutdown_timeout_seconds <= 0
        ):
            raise ValueError("invalid_graceful_shutdown_timeout")

        # auth_token_reference may be empty or None at construction time per contract
        if self.auth_token_reference is not None and not isinstance(self.auth_token_reference, str):
            raise ValueError("invalid_auth_token_reference")
        if isinstance(self.auth_token_reference, str) and self.auth_token_reference == "":
            # Explicit empty string is considered invalid; None means not provided
            raise ValueError("invalid_auth_token_reference")


# Failure code to HTTP status mapping
_FAILURE_STATUS_MAP: Dict[str, int] = {
    "invalid_request": 400,
    "invalid_execution_outcome": 400,
    "runtime_not_running": 409,
    "invalid_runtime_transition": 409,
    "duplicate_execution": 409,
    "invalid_status_transition": 409,
    "mission_not_found": 404,
    "budget_blocked": 429,
    "rate_limit_blocked": 429,
    "unknown_project": 404,
    "cross_project_reference": 403,
    "no_model_available": 503,
    "planner_failed": 503,
    "queue_resolution_failed": 503,
    "queue_failed": 503,
    "usage_recording_failed": 503,
    "report_persistence_failed": 503,
    "dependency_failed": 503,
}


def _utc_now_iso() -> str:
    # RFC3339 basic UTC timestamp without microseconds
    return _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _APIServer(ThreadingHTTPServer):
    # Allow clean shutdown; use daemon threads for handlers
    daemon_threads = True
    # HTTP/1.1 supported by BaseHTTPRequestHandler

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass: type[BaseHTTPRequestHandler], bind_and_activate: bool = True):
        super().__init__(server_address, RequestHandlerClass, bind_and_activate=bind_and_activate)
        # Will be set by RuntimePrivateAPI after construction
        self.api: Optional[RuntimePrivateAPI] = None


class RuntimePrivateAPI:
    def __init__(
        self,
        config: RuntimeAPIConfig,
        runtime: Any,
        token_resolver: Optional[TokenResolver] = None,
    ) -> None:
        self._config = config
        self._runtime = runtime
        self._token_resolver = token_resolver
        self._resolved_auth_token: Optional[str] = None  # lazily resolved and cached

        self._server: Optional[_APIServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.RLock()
        self._started_event = threading.Event()
        self._stopped_event = threading.Event()
        self._address: Optional[Tuple[str, int]] = None

        self._events: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self._emit_event("api_created")

    # Context manager support
    def __enter__(self) -> "RuntimePrivateAPI":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.stop()
        finally:
            self.close()

    # Public API lifecycle
    def start(self) -> None:
        with self._lifecycle_lock:
            if self._server is not None and self._server_thread is not None:
                # Idempotent
                return
            self._emit_event("api_starting")
            try:
                server = self._create_server()
                self._server = server
                self._address = (server.server_address[0], int(server.server_address[1]))
                # Start serving in a background daemon thread
                t = threading.Thread(target=self._serve_forever_internal, name="RuntimePrivateAPI-HTTPServer", daemon=True)
                self._server_thread = t
                # Mark not stopped yet
                self._stopped_event.clear()
                t.start()
                # Ensure readiness deterministically: server is already bound/activated by constructor
                # Signal started after thread start
                self._started_event.set()
                self._emit_event("api_started")
            except Exception as e:
                # Clean up partial initialization
                self._emit_event("api_start_failed")
                # Attempt to close any partially created server
                srv = self._server
                self._server = None
                self._server_thread = None
                if srv is not None:
                    try:
                        srv.server_close()
                    except Exception:
                        pass
                raise RuntimeError("api_start_failed") from e

    def serve_forever(self) -> None:
        # Provided to allow external blocking if needed
        thr = self._server_thread
        if thr is None:
            return
        try:
            thr.join()
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        # Gracefully shutdown the HTTP server
        server: Optional[_APIServer]
        thread: Optional[threading.Thread]
        with self._lifecycle_lock:
            server = self._server
            thread = self._server_thread
        if server is None or thread is None:
            return
        self._emit_event("api_stopping")
        # Do not hold the lock while shutting down to avoid deadlocks
        try:
            # Initiate shutdown; this will stop serve_forever loop
            server.shutdown()
        except Exception:
            # Continue with best-effort shutdown
            pass
        # Join with timeout
        timeout = float(self._config.graceful_shutdown_timeout_seconds)
        thread.join(timeout=timeout)
        self._stopped_event.set()

    def close(self) -> None:
        with self._lifecycle_lock:
            srv = self._server
            thr = self._server_thread
            self._server = None
            self._server_thread = None
            self._address = None
        # Close server resources outside lock
        if srv is not None:
            try:
                srv.server_close()
            except Exception:
                pass
        if thr is not None and thr.is_alive():
            # As a safeguard, do not forcefully kill thread; it should have stopped via shutdown()
            pass
        self._emit_event("api_stopped")

    def status(self) -> Dict[str, Any]:
        addr = self._address
        return {
            "ok": self._server is not None,
            "host": addr[0] if addr else None,
            "port": addr[1] if addr else None,
            "timestamp": _utc_now_iso(),
        }

    def address(self) -> Optional[Tuple[str, int]]:
        return self._address

    def latest_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        res: List[Dict[str, Any]] = []
        # Copy tail
        for i, ev in enumerate(list(self._events)[-limit:]):
            res.append(dict(ev))
        return res

    # Internal methods
    def _create_server(self) -> _APIServer:
        # Build handler class bound to this API instance
        api = self
        request_timeout = float(self._config.request_timeout_seconds)

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            # Suppress default logging to stdout and avoid sensitive info
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - override
                # Intentionally no request/authorization/body logging
                return

            def _write_json_response(self, status_code: int, payload: Dict[str, Any]) -> None:
                # Deterministic JSON, UTF-8 bytes
                body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                # Enforce response body size limit
                limit = api._config.response_body_limit_bytes
                if len(body_bytes) > limit:
                    # Replace with a minimal safe error response
                    payload_safe = {
                        "ok": False,
                        "status": 500,
                        "timestamp": _utc_now_iso(),
                        "error": {"code": "response_too_large", "message": "Response exceeds limit"},
                    }
                    body_bytes = json.dumps(payload_safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                    status_code = 500
                # Always close connection
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    self.wfile.write(body_bytes)
                    self.wfile.flush()
                finally:
                    # Ensure connection closed after response
                    self.close_connection = True

            def _immediate_error(self, http_code: int, code: str, message: str) -> None:
                payload = {
                    "ok": False,
                    "status": int(http_code),
                    "timestamp": _utc_now_iso(),
                    "error": {"code": code, "message": message},
                }
                self._write_json_response(http_code, payload)

            def _read_json_body(self, require_object: bool) -> Tuple[Optional[Dict[str, Any]], bool]:
                # Returns (obj or None, success)
                # Enforce content-type
                ctype = self.headers.get("Content-Type", "")
                if not ctype:
                    self._immediate_error(415, "unsupported_media_type", "Unsupported Content-Type")
                    return None, False
                base_type = ctype.split(";")[0].strip().lower()
                if base_type != "application/json":
                    self._immediate_error(415, "unsupported_media_type", "Unsupported Content-Type")
                    return None, False
                # Enforce content-length
                raw_len = self.headers.get("Content-Length")
                if raw_len is None:
                    self._immediate_error(400, "invalid_request", "Missing Content-Length")
                    return None, False
                try:
                    length = int(raw_len)
                except Exception:
                    self._immediate_error(400, "invalid_request", "Invalid Content-Length")
                    return None, False
                if length < 0:
                    self._immediate_error(400, "invalid_request", "Invalid Content-Length")
                    return None, False
                limit = api._config.request_body_limit_bytes
                if length > limit:
                    self._immediate_error(413, "request_too_large", "Request body too large")
                    return None, False
                # Set socket timeout for request processing
                try:
                    self.connection.settimeout(request_timeout)
                except Exception:
                    pass
                # Read exactly length bytes
                try:
                    data = self.rfile.read(length)
                except socket.timeout:
                    self._immediate_error(408, "request_timeout", "Request timeout")
                    return None, False
                except Exception:
                    self._immediate_error(400, "invalid_request", "Failed to read body")
                    return None, False
                # Parse JSON
                try:
                    decoded = data.decode("utf-8")
                except Exception:
                    self._immediate_error(400, "invalid_request", "Body must be UTF-8 JSON")
                    return None, False
                try:
                    obj = json.loads(decoded)
                except Exception:
                    self._immediate_error(400, "invalid_request", "Malformed JSON")
                    return None, False
                if require_object and not isinstance(obj, dict):
                    self._immediate_error(400, "invalid_request", "JSON body must be an object")
                    return None, False
                return obj if isinstance(obj, dict) else {}, True

            def _emit_request_event(self, name: str, http_status: Optional[int] = None, failure_code: Optional[str] = None) -> None:
                api._emit_event(
                    name,
                    endpoint=urlsplit(self.path).path,
                    method=self.command,
                    status=http_status,
                    failure_code=failure_code,
                )

            def _require_auth(self) -> Tuple[bool, Optional[str]]:
                # Returns (authorized, failure_code)
                # Allow GET /health/live unauthenticated - handled per endpoint
                # Header format: Authorization: Bearer <token>
                authz = self.headers.get("Authorization")
                # Lazily resolve expected token
                expected: Optional[str] = None
                try:
                    expected = api._get_expected_token()
                except Exception:
                    expected = None
                if not authz:
                    # If no header provided, treat as missing auth
                    return False, "missing_authentication"
                parts = authz.split()
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    return False, "invalid_authentication"
                provided = parts[1]
                if expected is None or expected == "":
                    # Authentication required but server not configured with a token -> 401
                    return False, "missing_authentication"
                try:
                    if not hmac.compare_digest(provided, expected):
                        return False, "invalid_authentication"
                except Exception:
                    return False, "invalid_authentication"
                return True, None

            # Route handlers
            def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
                try:
                    path = urlsplit(self.path).path
                    if path == "/health/live":
                        # No authentication required
                        self._emit_request_event("request_received")
                        payload = {
                            "ok": True,
                            "status": 200,
                            "timestamp": _utc_now_iso(),
                            "data": {"alive": True},
                        }
                        self._write_json_response(200, payload)
                        self._emit_request_event("request_completed", http_status=200)
                        return

                    # All other GET endpoints require authentication
                    authorized, failure_code = self._require_auth()
                    if not authorized:
                        code = 401 if failure_code == "missing_authentication" else 403
                        self._emit_request_event("authentication_failed", http_status=code, failure_code=failure_code)
                        self._immediate_error(code, failure_code or "authentication_failed", "Authentication required")
                        return

                    if path == "/health/ready":
                        self._emit_request_event("request_received")
                        status_obj = _safe_runtime_status(api._runtime)
                        is_ready = False
                        try:
                            state = str(status_obj.get("state")) if isinstance(status_obj, dict) else ""
                            app_ready = bool(status_obj.get("application_ready")) if isinstance(status_obj, dict) else False
                            is_ready = state.lower() == "running" and app_ready is True
                        except Exception:
                            is_ready = False
                        http_code = 200 if is_ready else 503
                        payload = {
                            "ok": is_ready,
                            "status": http_code,
                            "timestamp": _utc_now_iso(),
                            "data": {"ready": is_ready},
                        }
                        self._write_json_response(http_code, payload)
                        self._emit_request_event("request_completed", http_status=http_code)
                        return

                    if path == "/v1/runtime/status":
                        self._emit_request_event("request_received")
                        status_obj = _safe_runtime_status(api._runtime)
                        payload = {
                            "ok": True,
                            "status": 200,
                            "timestamp": _utc_now_iso(),
                            "data": status_obj,
                        }
                        self._write_json_response(200, payload)
                        self._emit_request_event("request_completed", http_status=200)
                        return

                    # Unknown route
                    self._emit_request_event("request_received")
                    self._emit_request_event("request_rejected", http_status=404, failure_code="not_found")
                    self._immediate_error(404, "not_found", "Not found")
                except Exception:
                    self._emit_request_event("api_operation_failed", http_status=500, failure_code="internal_error")
                    self._immediate_error(500, "internal_error", "Internal server error")

            def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
                try:
                    path = urlsplit(self.path).path
                    # Authentication required for all POST endpoints
                    authorized, failure_code = self._require_auth()
                    if not authorized:
                        code = 401 if failure_code == "missing_authentication" else 403
                        self._emit_request_event("authentication_failed", http_status=code, failure_code=failure_code)
                        self._immediate_error(code, failure_code or "authentication_failed", "Authentication required")
                        return

                    self._emit_request_event("request_received")

                    # Routing
                    if path == "/v1/requests":
                        body, ok = self._read_json_body(require_object=True)
                        if not ok:
                            self._emit_request_event("request_rejected", http_status=self._last_response_status(), failure_code="invalid_request")
                            return
                        try:
                            result = _call_runtime(api._runtime, "submit_request", body)
                            # Try to extract request_id if available
                            request_id: Optional[str] = None
                            if isinstance(result, dict):
                                rid = result.get("request_id") or result.get("id")
                                if isinstance(rid, str):
                                    request_id = rid
                            payload = {
                                "ok": True,
                                "status": 202,
                                "timestamp": _utc_now_iso(),
                                "data": {"accepted": True},
                            }
                            if request_id:
                                payload["request_id"] = request_id
                            self._write_json_response(202, payload)
                            self._emit_request_event("request_completed", http_status=202)
                        except Exception as ex:  # Map failures safely
                            http_code, code = _map_failure(ex)
                            self._emit_request_event("request_rejected", http_status=http_code, failure_code=code)
                            self._immediate_error(http_code, code, _safe_error_message(code))
                        return

                    if path == "/v1/execution-outcomes":
                        body, ok = self._read_json_body(require_object=True)
                        if not ok:
                            self._emit_request_event("request_rejected", http_status=self._last_response_status(), failure_code="invalid_request")
                            return
                        try:
                            _call_runtime(api._runtime, "process_execution_outcome", body)
                            payload = {
                                "ok": True,
                                "status": 200,
                                "timestamp": _utc_now_iso(),
                                "data": {"processed": True},
                            }
                            self._write_json_response(200, payload)
                            self._emit_request_event("request_completed", http_status=200)
                        except Exception as ex:
                            http_code, code = _map_failure(ex)
                            self._emit_request_event("request_rejected", http_status=http_code, failure_code=code)
                            self._immediate_error(http_code, code, _safe_error_message(code))
                        return

                    if api._config.enable_lifecycle_endpoints and path in (
                        "/v1/runtime/start",
                        "/v1/runtime/stop",
                        "/v1/components/background-worker/start",
                        "/v1/components/background-worker/stop",
                        "/v1/components/autonomous-controller/start",
                        "/v1/components/autonomous-controller/stop",
                    ):
                        # These endpoints do not require a request body
                        try:
                            if path == "/v1/runtime/start":
                                _call_runtime(api._runtime, "start")
                            elif path == "/v1/runtime/stop":
                                _call_runtime(api._runtime, "stop")
                            elif path == "/v1/components/background-worker/start":
                                _call_runtime(api._runtime, "start_background_worker")
                            elif path == "/v1/components/background-worker/stop":
                                _call_runtime(api._runtime, "stop_background_worker")
                            elif path == "/v1/components/autonomous-controller/start":
                                _call_runtime(api._runtime, "start_autonomous_controller")
                            elif path == "/v1/components/autonomous-controller/stop":
                                _call_runtime(api._runtime, "stop_autonomous_controller")
                            payload = {
                                "ok": True,
                                "status": 200,
                                "timestamp": _utc_now_iso(),
                                "data": {"ok": True},
                            }
                            self._write_json_response(200, payload)
                            self._emit_request_event("request_completed", http_status=200)
                        except Exception as ex:
                            http_code, code = _map_failure(ex)
                            self._emit_request_event("request_rejected", http_status=http_code, failure_code=code)
                            self._immediate_error(http_code, code, _safe_error_message(code))
                        return

                    # Unknown route
                    self._emit_request_event("request_rejected", http_status=404, failure_code="not_found")
                    self._immediate_error(404, "not_found", "Not found")
                except Exception:
                    self._emit_request_event("api_operation_failed", http_status=500, failure_code="internal_error")
                    self._immediate_error(500, "internal_error", "Internal server error")

            # Helper to get the last status sent if needed; limited utility due to encapsulation
            def _last_response_status(self) -> int:
                # Not directly available; return 400 for generic client error path
                return 400

        # Create server bound to host/port; constructor binds and activates
        try:
            server = _APIServer((self._config.host, int(self._config.port)), Handler)
            # Attach api instance for handler access
            server.api = self
            # Enforce timeout on server socket accepts
            try:
                server.timeout = float(self._config.request_timeout_seconds)
            except Exception:
                pass
            return server
        except OSError as e:
            # Re-raise as a controlled error
            raise RuntimeError("api_start_failed") from e

    def _serve_forever_internal(self) -> None:
        srv = self._server
        if srv is None:
            return
        try:
            # Use a small poll interval to allow timely shutdown
            srv.serve_forever(poll_interval=0.5)
        except Exception:
            # Swallow internal server exceptions to keep thread exiting cleanly
            pass

    def _emit_event(self, name: str, **kwargs: Any) -> None:
        ev = {
            "event": name,
            "timestamp": _utc_now_iso(),
        }
        # Only allow safe keys
        for key in ("endpoint", "method", "status", "failure_code"):
            if key in kwargs and kwargs[key] is not None:
                ev[key] = kwargs[key]
        self._events.append(ev)

    def _get_expected_token(self) -> Optional[str]:
        # Lazy resolve and cache; never log token
        if self._resolved_auth_token is not None:
            return self._resolved_auth_token
        resolver = self._token_resolver
        token: Optional[str] = None
        if resolver is not None:
            try:
                token = resolver()
            except Exception:
                token = None
        # Cache the token; if None, keep None to force 401
        self._resolved_auth_token = token
        return token


def _safe_error_message(code: str) -> str:
    # Generic safe, non-revealing messages
    messages = {
        "missing_authentication": "Authentication required",
        "invalid_authentication": "Invalid authentication",
        "invalid_request": "Invalid request",
        "invalid_execution_outcome": "Invalid execution outcome",
        "runtime_not_running": "Runtime not running",
        "invalid_runtime_transition": "Invalid runtime transition",
        "duplicate_execution": "Duplicate execution",
        "invalid_status_transition": "Invalid status transition",
        "mission_not_found": "Not found",
        "budget_blocked": "Resource temporarily unavailable",
        "rate_limit_blocked": "Rate limited",
        "unknown_project": "Not found",
        "cross_project_reference": "Forbidden",
        "no_model_available": "Service unavailable",
        "planner_failed": "Service unavailable",
        "queue_resolution_failed": "Service unavailable",
        "queue_failed": "Service unavailable",
        "usage_recording_failed": "Service unavailable",
        "report_persistence_failed": "Service unavailable",
        "dependency_failed": "Service unavailable",
        "not_found": "Not found",
        "unsupported_media_type": "Unsupported Content-Type",
        "request_too_large": "Request body too large",
        "request_timeout": "Request timeout",
        "internal_error": "Internal server error",
        "response_too_large": "Response exceeds limit",
    }
    return messages.get(code, "Request failed")


def _map_failure(ex: Exception) -> Tuple[int, str]:
    # Attempt to map based on known attributes
    code = getattr(ex, "code", None)
    if not isinstance(code, str) or not code:
        code = getattr(ex, "error_code", None)
    if not isinstance(code, str) or not code:
        # Try class-name based mapping (optional)
        name = ex.__class__.__name__.lower()
        # Map a few common aliases if available
        alias_map = {
            "invalidrequest": "invalid_request",
            "invalidexecutionoutcome": "invalid_execution_outcome",
            "runtimenotrunning": "runtime_not_running",
        }
        code = alias_map.get(name, "internal_error")
    http_code = _FAILURE_STATUS_MAP.get(code, 500 if code == "internal_error" else _FAILURE_STATUS_MAP.get(code, 500))
    if http_code == 500 and code != "internal_error":
        # Unknown code -> generic internal error to avoid leaking details
        code = "internal_error"
    return int(http_code), code


def _call_runtime(runtime: Any, method: str, *args: Any, **kwargs: Any) -> Any:
    # Do not hold any API locks while calling runtime methods
    fn = getattr(runtime, method, None)
    if fn is None or not callable(fn):
        raise RuntimeError("invalid_runtime_transition")
    return fn(*args, **kwargs)


def _safe_runtime_status(runtime: Any) -> Dict[str, Any]:
    # Try to import the provided runtime_status function lazily
    func = None
    try:  # First, common expected path
        from agent.runtime import runtime_status as _rs  # type: ignore
        func = _rs
    except Exception:
        try:
            from agent import runtime as _runtime_mod  # type: ignore
            func = getattr(_runtime_mod, "runtime_status", None)
        except Exception:
            func = None
    if callable(func):
        try:
            res = func(runtime)  # type: ignore[misc]
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    # Fallback to runtime.status() if available
    try:
        st = runtime.status()  # type: ignore[attr-defined]
        if isinstance(st, dict):
            return st
    except Exception:
        pass
    return {}


def _validate_config_input(config: RuntimeAPIConfig | MutableMapping[str, Any]) -> RuntimeAPIConfig:
    if isinstance(config, RuntimeAPIConfig):
        config.validate()
        return config
    if not isinstance(config, dict):
        raise ValueError("invalid_config")
    valid_keys = {f.name for f in fields(RuntimeAPIConfig)}
    unknown = set(config.keys()) - valid_keys
    if unknown:
        raise ValueError("unknown_config_fields")
    cfg = RuntimeAPIConfig(**config)
    cfg.validate()
    return cfg


def build_runtime_private_api(config: RuntimeAPIConfig | MutableMapping[str, Any], runtime: Optional[Any] = None) -> RuntimePrivateAPI:
    """
    Build the RuntimePrivateAPI without eagerly resolving authentication.

    The token is resolved lazily from the environment using the provided auth_token_reference
    when protected endpoints are accessed.
    """
    cfg = _validate_config_input(config)

    # Lazy token resolver closure; do not resolve now
    def resolver() -> Optional[str]:
        ref = cfg.auth_token_reference
        if not ref:
            return None
        # Resolve safely from environment; never execute dynamic code
        return os.environ.get(ref)

    api = RuntimePrivateAPI(config=cfg, runtime=runtime, token_resolver=resolver)
    return api


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime Private API")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (0 for ephemeral)")
    parser.add_argument("--data-root", dest="data_root", default=None, help="Application data root")
    parser.add_argument("--repository-root", dest="repository_root", default=None, help="Repository root")
    parser.add_argument("--default-project-id", dest="default_project_id", default=None, help="Default project id")
    parser.add_argument("--environment-name", dest="environment_name", default=None, help="Environment name")
    parser.add_argument("--auth-token-env", dest="auth_token_env", default=None, help="Environment variable name holding bearer token")
    parser.add_argument("--enable-lifecycle-endpoints", dest="enable_lifecycle_endpoints", action="store_true", help="Enable lifecycle endpoints")

    args = parser.parse_args(argv)

    # Validate host and port early
    host = str(args.host)
    if host in ("0.0.0.0", "::"):
        print("Refusing to bind to public wildcard host", file=sys.stderr)
        return 2
    port = int(args.port)
    if port < 0 or port > 65535:
        print("Invalid port", file=sys.stderr)
        return 2

    # Build configs using existing public interfaces; import lazily to avoid import-time failures
    try:
        from agent.runtime import build_runtime as _build_runtime  # type: ignore
        from agent.runtime import ApplicationConfig as _ApplicationConfig  # type: ignore
        from agent.runtime import RuntimeConfig as _RuntimeConfig  # type: ignore
    except Exception as e:
        # If components are unavailable in this environment, exit with code 2
        print("Required runtime components are unavailable: " + str(e), file=sys.stderr)
        return 2

    # Create application and runtime config objects safely using keyword arguments if available
    try:
        app_cfg = _ApplicationConfig(
            data_root=args.data_root,
            repository_root=args.repository_root,
            default_project_id=args.default_project_id,
            environment_name=args.environment_name,
        )
    except Exception:
        # Fallback: try minimal constructor
        try:
            app_cfg = _ApplicationConfig()
        except Exception as e:
            print("Failed to construct ApplicationConfig: " + str(e), file=sys.stderr)
            return 2

    try:
        runtime_cfg = _RuntimeConfig()
    except Exception:
        try:
            runtime_cfg = _RuntimeConfig(application=app_cfg)  # type: ignore
        except Exception as e:
            print("Failed to construct RuntimeConfig: " + str(e), file=sys.stderr)
            return 2

    # Build runtime service
    try:
        runtime = _build_runtime(app_cfg, runtime_cfg)
    except Exception as e:
        print("Failed to build runtime: " + str(e), file=sys.stderr)
        return 1

    # Start runtime service if start() exists
    try:
        if hasattr(runtime, "start") and callable(getattr(runtime, "start")):
            runtime.start()  # type: ignore[attr-defined]
    except Exception as e:
        print("Failed to start runtime: " + str(e), file=sys.stderr)
        return 1

    # Build API config and API
    api_cfg = RuntimeAPIConfig(
        host=host,
        port=port,
        enable_lifecycle_endpoints=bool(args.enable_lifecycle_endpoints),
        auth_token_reference=args.auth_token_env if args.auth_token_env else None,
    )
    try:
        api = build_runtime_private_api(api_cfg, runtime=runtime)
    except Exception as e:
        print("Failed to build API: " + str(e), file=sys.stderr)
        # Attempt to stop runtime
        try:
            if hasattr(runtime, "stop"):
                runtime.stop()  # type: ignore[attr-defined]
        except Exception:
            pass
        return 1

    # Start API
    try:
        api.start()
    except Exception as e:
        print("Failed to start API: " + str(e), file=sys.stderr)
        try:
            if hasattr(runtime, "stop"):
                runtime.stop()  # type: ignore[attr-defined]
        except Exception:
            pass
        return 1

    # Install signal handlers to stop gracefully
    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: Any) -> None:  # noqa: ARG001 - frame unused
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except Exception:
        # Some platforms may not support signals in certain contexts
        pass

    # Wait until interrupted
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        pass

    # Stop API then runtime
    try:
        api.stop()
    except Exception:
        pass
    try:
        api.close()
    except Exception:
        pass

    try:
        if hasattr(runtime, "stop") and callable(getattr(runtime, "stop")):
            runtime.stop()  # type: ignore[attr-defined]
    except Exception:
        pass

    return 0


# If executed as a script
if __name__ == "__main__":
    sys.exit(main())
