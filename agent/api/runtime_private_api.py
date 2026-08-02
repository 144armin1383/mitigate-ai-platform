from __future__ import annotations

import argparse
import hmac
import json
import os
import signal
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple, Union


JSONType = Union[None, bool, int, float, str, List["JSONType"], Dict[str, "JSONType"]]


@dataclass(frozen=True, slots=True)
class RuntimeAPIConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    request_body_limit_bytes: int = 1_048_576
    response_body_limit_bytes: int = 1_048_576
    request_timeout_seconds: int = 30
    graceful_shutdown_timeout_seconds: int = 15
    enable_lifecycle_endpoints: bool = False
    # Reference to external secret (e.g., environment variable name). Lazy-resolved.
    auth_token_reference: str = ""

    @staticmethod
    def from_mapping(mapping: Mapping[str, Any]) -> "RuntimeAPIConfig":
        allowed = {
            "host",
            "port",
            "request_body_limit_bytes",
            "response_body_limit_bytes",
            "request_timeout_seconds",
            "graceful_shutdown_timeout_seconds",
            "enable_lifecycle_endpoints",
            "auth_token_reference",
        }
        unknown = [k for k in mapping.keys() if k not in allowed]
        if unknown:
            raise ValueError(f"Unknown configuration fields: {', '.join(sorted(unknown))}")

        host = str(mapping.get("host", RuntimeAPIConfig.host))
        port_raw = mapping.get("port", RuntimeAPIConfig.port)
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            raise ValueError("port must be an integer")

        req_limit_raw = mapping.get("request_body_limit_bytes", RuntimeAPIConfig.request_body_limit_bytes)
        try:
            request_body_limit_bytes = int(req_limit_raw)
        except (TypeError, ValueError):
            raise ValueError("request_body_limit_bytes must be an integer")

        resp_limit_raw = mapping.get("response_body_limit_bytes", RuntimeAPIConfig.response_body_limit_bytes)
        try:
            response_body_limit_bytes = int(resp_limit_raw)
        except (TypeError, ValueError):
            raise ValueError("response_body_limit_bytes must be an integer")

        req_timeout_raw = mapping.get("request_timeout_seconds", RuntimeAPIConfig.request_timeout_seconds)
        try:
            request_timeout_seconds = int(req_timeout_raw)
        except (TypeError, ValueError):
            raise ValueError("request_timeout_seconds must be an integer")

        shutdown_timeout_raw = mapping.get(
            "graceful_shutdown_timeout_seconds", RuntimeAPIConfig.graceful_shutdown_timeout_seconds
        )
        try:
            graceful_shutdown_timeout_seconds = int(shutdown_timeout_raw)
        except (TypeError, ValueError):
            raise ValueError("graceful_shutdown_timeout_seconds must be an integer")

        enable_lifecycle_endpoints = bool(mapping.get("enable_lifecycle_endpoints", False))
        auth_token_reference = str(mapping.get("auth_token_reference", ""))

        cfg = RuntimeAPIConfig(
            host=host,
            port=port,
            request_body_limit_bytes=request_body_limit_bytes,
            response_body_limit_bytes=response_body_limit_bytes,
            request_timeout_seconds=request_timeout_seconds,
            graceful_shutdown_timeout_seconds=graceful_shutdown_timeout_seconds,
            enable_lifecycle_endpoints=enable_lifecycle_endpoints,
            auth_token_reference=auth_token_reference,
        )
        # Validation (must not reject empty auth reference; enforced lazily)
        _validate_runtime_api_config(cfg)
        return cfg


def _validate_runtime_api_config(cfg: RuntimeAPIConfig) -> None:
    if not isinstance(cfg.host, str) or not cfg.host:
        raise ValueError("host must be a non-empty string")
    # Reject wildcard public binds
    if cfg.host in ("0.0.0.0", "::"):
        raise ValueError("wildcard public hosts are not allowed; bind to a specific local address")

    if not isinstance(cfg.port, int) or not (0 <= cfg.port <= 65535):
        raise ValueError("port must be an integer between 0 and 65535")

    if not isinstance(cfg.request_body_limit_bytes, int) or cfg.request_body_limit_bytes <= 0:
        raise ValueError("request_body_limit_bytes must be a positive integer")

    if not isinstance(cfg.response_body_limit_bytes, int) or cfg.response_body_limit_bytes <= 0:
        raise ValueError("response_body_limit_bytes must be a positive integer")

    if not isinstance(cfg.request_timeout_seconds, int) or cfg.request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be a positive integer")

    if (
        not isinstance(cfg.graceful_shutdown_timeout_seconds, int)
        or cfg.graceful_shutdown_timeout_seconds <= 0
    ):
        raise ValueError("graceful_shutdown_timeout_seconds must be a positive integer")
    # auth_token_reference is allowed to be empty here (lazy auth enforcement)


class _EventRecorder:
    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event_type: str, **fields: Any) -> None:
        e = {
            "type": event_type,
            "timestamp": _utc_timestamp_iso(),
        }
        for k, v in fields.items():
            # Only safe fields should be included by callers
            e[k] = v
        with self._lock:
            self._events.append(e)
            if len(self._events) > self._capacity:
                # Trim oldest
                del self._events[0 : len(self._events) - self._capacity]

    def latest(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            return list(self._events[-limit:])


def _utc_timestamp_iso() -> str:
    # Deterministic, timezone-aware ISO 8601 UTC timestamp
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


_FAILURE_HTTP_STATUS: Dict[str, int] = {
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

_SAFE_ERROR_MESSAGES: Dict[str, str] = {
    "invalid_request": "The request is invalid.",
    "invalid_execution_outcome": "The execution outcome is invalid.",
    "runtime_not_running": "The runtime is not running.",
    "invalid_runtime_transition": "The requested runtime transition is not allowed.",
    "duplicate_execution": "The execution is a duplicate.",
    "invalid_status_transition": "The requested status transition is not allowed.",
    "mission_not_found": "The requested mission was not found.",
    "budget_blocked": "Operation blocked by budget policy.",
    "rate_limit_blocked": "Operation blocked by rate limit policy.",
    "unknown_project": "The referenced project was not found.",
    "cross_project_reference": "Cross-project reference is not allowed.",
    "no_model_available": "No model is currently available.",
    "planner_failed": "The planner failed to produce a plan.",
    "queue_resolution_failed": "Queue resolution failed.",
    "queue_failed": "Queue operation failed.",
    "usage_recording_failed": "Usage recording failed.",
    "report_persistence_failed": "Report persistence failed.",
    "dependency_failed": "A required dependency failed.",
    "unauthorized": "Authentication is required.",
    "forbidden": "Invalid authentication provided.",
    "unsupported_media_type": "Unsupported content type.",
    "malformed_json": "Malformed JSON body.",
    "payload_not_object": "A JSON object is required.",
    "not_found": "Endpoint not found.",
    "response_too_large": "Response exceeds configured size limit.",
    "request_timeout": "Request timed out.",
    "method_not_allowed": "HTTP method not allowed.",
    "lifecycle_disabled": "Lifecycle endpoints are disabled.",
    "internal_error": "An internal error occurred.",
}


def _extract_failure_code(exc: BaseException) -> Optional[str]:
    # Try to resolve a structured failure code without exposing raw exception details
    for attr in ("code", "error_code", "failure_code", "reason"):
        val = getattr(exc, attr, None)
        if isinstance(val, str) and val:
            return val
    # Heuristic fallback (avoid leaking messages; only match known codes in a safe way)
    msg = str(exc).lower()
    for code in _FAILURE_HTTP_STATUS.keys():
        if code in msg:
            return code
    return None


def _map_failure_to_status(code: Optional[str]) -> Tuple[int, str]:
    if code and code in _FAILURE_HTTP_STATUS:
        return _FAILURE_HTTP_STATUS[code], _SAFE_ERROR_MESSAGES.get(code, "Operation failed.")
    if code == "unauthorized":
        return HTTPStatus.UNAUTHORIZED, _SAFE_ERROR_MESSAGES[code]
    if code == "forbidden":
        return HTTPStatus.FORBIDDEN, _SAFE_ERROR_MESSAGES[code]
    if code == "unsupported_media_type":
        return HTTPStatus.UNSUPPORTED_MEDIA_TYPE, _SAFE_ERROR_MESSAGES[code]
    if code == "malformed_json":
        return HTTPStatus.BAD_REQUEST, _SAFE_ERROR_MESSAGES[code]
    if code == "payload_not_object":
        return HTTPStatus.BAD_REQUEST, _SAFE_ERROR_MESSAGES[code]
    if code == "not_found":
        return HTTPStatus.NOT_FOUND, _SAFE_ERROR_MESSAGES[code]
    if code == "response_too_large":
        return HTTPStatus.INTERNAL_SERVER_ERROR, _SAFE_ERROR_MESSAGES[code]
    if code == "request_timeout":
        return HTTPStatus.REQUEST_TIMEOUT, _SAFE_ERROR_MESSAGES[code]
    if code == "method_not_allowed":
        return HTTPStatus.METHOD_NOT_ALLOWED, _SAFE_ERROR_MESSAGES[code]
    if code == "lifecycle_disabled":
        return HTTPStatus.NOT_FOUND, _SAFE_ERROR_MESSAGES[code]
    # Unknown failure -> 500
    return HTTPStatus.INTERNAL_SERVER_ERROR, _SAFE_ERROR_MESSAGES["internal_error"]


class RuntimePrivateAPI:
    def __init__(
        self,
        config: RuntimeAPIConfig,
        runtime: Optional[Any] = None,
        token_resolver: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        _validate_runtime_api_config(config)
        self._config = config
        self._runtime = runtime
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._bound_host: Optional[str] = None
        self._bound_port: Optional[int] = None
        self._events = _EventRecorder()
        # Lazy resolver; if None, default to environment variable lookup
        self._token_resolver = token_resolver
        self._events.emit("api_created")

    # Context manager support
    def __enter__(self) -> "RuntimePrivateAPI":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        try:
            self.stop()
        finally:
            self.close()

    def start(self) -> None:
        if self._server is not None:
            # Idempotent
            return
        self._events.emit("api_starting")
        try:
            # Build and bind the HTTP server before returning
            handler_cls = self._make_handler_class()
            # Ensure binding happens in constructor
            server = ThreadingHTTPServer((self._config.host, self._config.port), handler_cls, bind_and_activate=True)
            # Attach back-reference for handler access
            setattr(server, "_api", self)
            # Socket timeout for handling requests
            server.timeout = 1.0
            self._server = server
            # Store actual bound address (handles ephemeral port 0)
            sa = server.server_address
            self._bound_host = sa[0]
            self._bound_port = int(sa[1])

            # Start serving thread
            t = threading.Thread(target=server.serve_forever, name="RuntimePrivateAPI-HTTPServer", daemon=True)
            self._thread = t
            t.start()

            # Readiness: server is already bound; thread started
            self._events.emit("api_started")
        except Exception:
            # Ensure cleanup on failure
            try:
                if self._server is not None:
                    self._server.server_close()
            finally:
                self._server = None
                self._thread = None
                self._bound_host = None
                self._bound_port = None
            self._events.emit("api_start_failed")
            raise

    def serve_forever(self) -> None:
        # Blocking serve utilizing existing thread/loop semantics; if not started, start inline server loop
        if self._server is None:
            self.start()
        # The internal ThreadingHTTPServer is already serving in a daemon thread. Block here until interrupted.
        try:
            while self._server is not None and self._thread is not None and self._thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        if server is None:
            return
        self._events.emit("api_stopping")
        # Do not hold locks while calling shutdown to avoid deadlocks
        try:
            server.shutdown()
        except Exception:
            # Suppress to avoid exposing internals; still proceed to close
            self._events.emit("api_operation_failed", endpoint="__shutdown__")
        if thread is not None and thread.is_alive():
            thread.join(timeout=float(self._config.graceful_shutdown_timeout_seconds))
        self._events.emit("api_stopped")

    def close(self) -> None:
        server = self._server
        if server is not None:
            try:
                server.server_close()
            except Exception:
                pass
        # Clear refs for idempotency
        self._server = None
        self._thread = None
        self._bound_host = None
        self._bound_port = None

    def status(self) -> Dict[str, Any]:
        state = "running" if (self._server is not None and self._thread is not None and self._thread.is_alive()) else "stopped"
        return {
            "state": state,
            "timestamp": _utc_timestamp_iso(),
            "address": self.address(),
        }

    def address(self) -> Optional[Tuple[str, int]]:
        if self._bound_host is None or self._bound_port is None:
            return None
        return self._bound_host, int(self._bound_port)

    def latest_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._events.latest(limit)

    # -------- Internal utilities --------

    def _make_handler_class(self):
        api = self
        cfg = self._config

        class Handler(BaseHTTPRequestHandler):  # type: ignore[misc]
            server_version = "RuntimePrivateAPI/1.0"
            protocol_version = "HTTP/1.1"

            def log_request(self, code: Union[int, str] = "-", size: Union[int, str] = "-") -> None:  # noqa: D401
                # Silence default logging to avoid leaking information
                return

            def log_message(self, format: str, *args: Any) -> None:  # noqa: D401
                # Silence default logging to avoid leaking information
                return

            # -------------------- Helpers --------------------
            def _request_id(self) -> str:
                return uuid.uuid4().hex

            def _emit(self, event_type: str, **fields: Any) -> None:
                try:
                    api._events.emit(event_type, **fields)
                except Exception:
                    # Never let event emission break request handling
                    pass

            def _set_common_headers(self, code: int, extra: Optional[Mapping[str, str]] = None) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if extra:
                    for k, v in extra.items():
                        self.send_header(k, v)
                self.end_headers()

            def _write_body(self, payload: Mapping[str, Any]) -> None:
                try:
                    b = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                except Exception:
                    # Fallback to a minimal generic error if serialization fails
                    fb = {
                        "ok": False,
                        "status": int(HTTPStatus.INTERNAL_SERVER_ERROR),
                        "timestamp": _utc_timestamp_iso(),
                        "error": {
                            "code": "internal_error",
                            "message": _SAFE_ERROR_MESSAGES["internal_error"],
                        },
                    }
                    b = json.dumps(fb, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                # Enforce response size cap
                if len(b) > cfg.response_body_limit_bytes:
                    small = {
                        "ok": False,
                        "status": int(HTTPStatus.INTERNAL_SERVER_ERROR),
                        "timestamp": _utc_timestamp_iso(),
                        "error": {
                            "code": "response_too_large",
                            "message": _SAFE_ERROR_MESSAGES["response_too_large"],
                        },
                    }
                    b = json.dumps(small, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                try:
                    self.wfile.write(b)
                except Exception:
                    # Best effort; do not raise further
                    pass

            def _auth_check(self, endpoint: str, request_id: str) -> Optional[Tuple[int, Dict[str, Any], Mapping[str, str]]]:
                # Returns (status_code, body, extra_headers) on failure; None on success
                # Allow unauthenticated access for /health/live only
                path = self.path.split("?", 1)[0]
                if self.command == "GET" and path == "/health/live":
                    return None

                # Lazy resolve expected token
                expected_token: Optional[str] = None
                if cfg.auth_token_reference:
                    try:
                        if api._token_resolver is not None:
                            expected_token = api._token_resolver(cfg.auth_token_reference)
                        else:
                            # Default to environment variable resolver
                            expected_token = os.environ.get(cfg.auth_token_reference)  # type: ignore[str-bytes-safe]
                    except Exception:
                        expected_token = None
                # Extract provided token from Authorization header
                authz = self.headers.get("Authorization")
                if not authz:
                    self._emit(
                        "authentication_failed",
                        endpoint=endpoint,
                        method=self.command,
                        status=int(HTTPStatus.UNAUTHORIZED),
                    )
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.UNAUTHORIZED),
                        request_id=request_id,
                        error_code="unauthorized",
                    )
                    return int(HTTPStatus.UNAUTHORIZED), body, {"WWW-Authenticate": "Bearer"}

                provided_token = None
                if isinstance(authz, str):
                    parts = authz.split(" ")
                    if len(parts) == 2 and parts[0].lower() == "bearer":
                        provided_token = parts[1]

                if not provided_token:
                    self._emit(
                        "authentication_failed",
                        endpoint=endpoint,
                        method=self.command,
                        status=int(HTTPStatus.UNAUTHORIZED),
                    )
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.UNAUTHORIZED),
                        request_id=request_id,
                        error_code="unauthorized",
                    )
                    return int(HTTPStatus.UNAUTHORIZED), body, {"WWW-Authenticate": "Bearer"}

                # If we do not have an expected token configured/resolved, treat as unauthorized (missing auth)
                if not expected_token:
                    self._emit(
                        "authentication_failed",
                        endpoint=endpoint,
                        method=self.command,
                        status=int(HTTPStatus.UNAUTHORIZED),
                    )
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.UNAUTHORIZED),
                        request_id=request_id,
                        error_code="unauthorized",
                    )
                    return int(HTTPStatus.UNAUTHORIZED), body, {"WWW-Authenticate": "Bearer"}

                # Constant-time comparison
                try:
                    if not hmac.compare_digest(str(provided_token), str(expected_token)):
                        self._emit(
                            "authentication_failed",
                            endpoint=endpoint,
                            method=self.command,
                            status=int(HTTPStatus.FORBIDDEN),
                        )
                        body = _make_response_body(
                            ok=False,
                            status=int(HTTPStatus.FORBIDDEN),
                            request_id=request_id,
                            error_code="forbidden",
                        )
                        return int(HTTPStatus.FORBIDDEN), body, {}
                except Exception:
                    self._emit(
                        "authentication_failed",
                        endpoint=endpoint,
                        method=self.command,
                        status=int(HTTPStatus.FORBIDDEN),
                    )
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.FORBIDDEN),
                        request_id=request_id,
                        error_code="forbidden",
                    )
                    return int(HTTPStatus.FORBIDDEN), body, {}
                return None

            def _read_json_object(self, request_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, Dict[str, Any]]]]:
                # Enforce content type
                ct = self.headers.get("Content-Type", "")
                if not isinstance(ct, str) or ("application/json" not in ct.lower()):
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.UNSUPPORTED_MEDIA_TYPE),
                        request_id=request_id,
                        error_code="unsupported_media_type",
                    )
                    return None, (int(HTTPStatus.UNSUPPORTED_MEDIA_TYPE), body)

                # Determine length
                length_header = self.headers.get("Content-Length")
                try:
                    content_length = int(length_header) if length_header is not None else -1
                except (TypeError, ValueError):
                    content_length = -1

                # Apply a hard cap while reading to defend against missing/incorrect length
                max_to_read = cfg.request_body_limit_bytes + 1

                # Set socket timeout for reading body
                try:
                    if hasattr(self.connection, "settimeout"):
                        self.connection.settimeout(float(cfg.request_timeout_seconds))
                except Exception:
                    pass

                try:
                    if content_length >= 0:
                        to_read = min(content_length, max_to_read)
                        data = self.rfile.read(to_read)
                        # If the declared content length exceeds limit or if actual bytes exceed limit
                        if content_length > cfg.request_body_limit_bytes or len(data) > cfg.request_body_limit_bytes:
                            body = _make_response_body(
                                ok=False,
                                status=int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
                                request_id=request_id,
                                error_code="invalid_request",
                            )
                            return None, (int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE), body)
                        raw = data
                    else:
                        # Unknown length; read up to cap
                        chunks: List[bytes] = []
                        total = 0
                        while total <= cfg.request_body_limit_bytes:
                            chunk = self.rfile.read(min(65536, cfg.request_body_limit_bytes - total + 1))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            total += len(chunk)
                            if total > cfg.request_body_limit_bytes:
                                break
                        if total > cfg.request_body_limit_bytes:
                            body = _make_response_body(
                                ok=False,
                                status=int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
                                request_id=request_id,
                                error_code="invalid_request",
                            )
                            return None, (int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE), body)
                        raw = b"".join(chunks)
                except socket.timeout:
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.REQUEST_TIMEOUT),
                        request_id=request_id,
                        error_code="request_timeout",
                    )
                    return None, (int(HTTPStatus.REQUEST_TIMEOUT), body)
                except Exception:
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.BAD_REQUEST),
                        request_id=request_id,
                        error_code="invalid_request",
                    )
                    return None, (int(HTTPStatus.BAD_REQUEST), body)

                try:
                    text = raw.decode("utf-8")
                except Exception:
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.BAD_REQUEST),
                        request_id=request_id,
                        error_code="malformed_json",
                    )
                    return None, (int(HTTPStatus.BAD_REQUEST), body)

                try:
                    parsed = json.loads(text)
                except Exception:
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.BAD_REQUEST),
                        request_id=request_id,
                        error_code="malformed_json",
                    )
                    return None, (int(HTTPStatus.BAD_REQUEST), body)

                if not isinstance(parsed, dict):
                    body = _make_response_body(
                        ok=False,
                        status=int(HTTPStatus.BAD_REQUEST),
                        request_id=request_id,
                        error_code="payload_not_object",
                    )
                    return None, (int(HTTPStatus.BAD_REQUEST), body)

                return parsed, None

            def _runtime(self) -> Any:
                return api._runtime

            # -------------------- Endpoints --------------------
            def do_GET(self) -> None:  # noqa: N802
                req_id = self._request_id()
                path = self.path.split("?", 1)[0]
                self._emit("request_received", endpoint=path, method="GET")

                if path == "/health/live":
                    body = _make_response_body(
                        ok=True,
                        status=int(HTTPStatus.OK),
                        request_id=req_id,
                        data={"alive": True},
                    )
                    self._set_common_headers(int(HTTPStatus.OK))
                    self._write_body(body)
                    self._emit("request_completed", endpoint=path, method="GET", status=int(HTTPStatus.OK))
                    return

                # Auth required for all other GET
                auth_fail = self._auth_check(endpoint=path, request_id=req_id)
                if auth_fail is not None:
                    code, body, extra = auth_fail
                    self._set_common_headers(code, extra)
                    self._write_body(body)
                    return

                if path == "/health/ready":
                    # Determine readiness via runtime status
                    try:
                        runtime = self._runtime()
                        ready = False
                        if runtime is not None:
                            try:
                                st = runtime.status()  # type: ignore[call-arg]
                            except TypeError:
                                # Some runtimes may expose 'status' attribute
                                st = getattr(runtime, "status", None)
                            state = None
                            app_ready = None
                            if isinstance(st, Mapping):
                                state = str(st.get("state") or st.get("runtime_state") or "").lower()
                                ar = st.get("application_ready")
                                app_ready = bool(ar) if isinstance(ar, (bool, int)) else False
                            ready = (state == "running") and bool(app_ready)
                        if ready:
                            body = _make_response_body(
                                ok=True,
                                status=int(HTTPStatus.OK),
                                request_id=req_id,
                                data={"ready": True},
                            )
                            self._set_common_headers(int(HTTPStatus.OK))
                            self._write_body(body)
                            self._emit("request_completed", endpoint=path, method="GET", status=int(HTTPStatus.OK))
                            return
                        else:
                            body = _make_response_body(
                                ok=False,
                                status=int(HTTPStatus.SERVICE_UNAVAILABLE),
                                request_id=req_id,
                                error_code=None,
                            )
                            self._set_common_headers(int(HTTPStatus.SERVICE_UNAVAILABLE))
                            self._write_body(body)
                            self._emit(
                                "request_completed", endpoint=path, method="GET", status=int(HTTPStatus.SERVICE_UNAVAILABLE)
                            )
                            return
                    except Exception as exc:
                        code, msg = _map_failure_to_status(_extract_failure_code(exc))
                        body = _make_response_body(
                            ok=False,
                            status=code,
                            request_id=req_id,
                            error_code=None,
                        )
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("api_operation_failed", endpoint=path, method="GET", status=code)
                        return

                if path == "/v1/runtime/status":
                    try:
                        runtime = self._runtime()
                        if runtime is None:
                            raise RuntimeError("runtime_not_running")
                        # Prefer a safe status view from runtime
                        try:
                            st = runtime.status()  # type: ignore[call-arg]
                        except TypeError:
                            st = getattr(runtime, "status", None)
                        if not isinstance(st, Mapping):
                            st = {"state": str(st)}
                        data = {"runtime": dict(st)}
                        body = _make_response_body(
                            ok=True,
                            status=int(HTTPStatus.OK),
                            request_id=req_id,
                            data=data,
                        )
                        self._set_common_headers(int(HTTPStatus.OK))
                        self._write_body(body)
                        self._emit("request_completed", endpoint=path, method="GET", status=int(HTTPStatus.OK))
                        return
                    except Exception as exc:
                        code, _ = _map_failure_to_status(_extract_failure_code(exc))
                        body = _make_response_body(
                            ok=False,
                            status=code,
                            request_id=req_id,
                            error_code=None,
                        )
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("api_operation_failed", endpoint=path, method="GET", status=code)
                        return

                # Not found
                body = _make_response_body(
                    ok=False,
                    status=int(HTTPStatus.NOT_FOUND),
                    request_id=req_id,
                    error_code="not_found",
                )
                self._set_common_headers(int(HTTPStatus.NOT_FOUND))
                self._write_body(body)
                self._emit("request_rejected", endpoint=path, method="GET", status=int(HTTPStatus.NOT_FOUND))

            def do_POST(self) -> None:  # noqa: N802
                req_id = self._request_id()
                path = self.path.split("?", 1)[0]
                self._emit("request_received", endpoint=path, method="POST")

                # Auth required for all POST endpoints
                auth_fail = self._auth_check(endpoint=path, request_id=req_id)
                if auth_fail is not None:
                    code, body, extra = auth_fail
                    self._set_common_headers(code, extra)
                    self._write_body(body)
                    return

                # Routing
                if path == "/v1/requests":
                    payload, err = self._read_json_object(req_id)
                    if err is not None:
                        code, body = err
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("request_rejected", endpoint=path, method="POST", status=code)
                        return
                    try:
                        runtime = self._runtime()
                        if runtime is None:
                            raise RuntimeError("runtime_not_running")
                        result = runtime.submit_request(payload)  # type: ignore[attr-defined]
                        request_id_val: Optional[str] = None
                        if isinstance(result, Mapping):
                            rid = result.get("request_id")
                            if isinstance(rid, str):
                                request_id_val = rid
                        body = _make_response_body(
                            ok=True,
                            status=int(HTTPStatus.ACCEPTED),
                            request_id=req_id,
                            request_id_out=request_id_val,
                            data=None,
                        )
                        self._set_common_headers(int(HTTPStatus.ACCEPTED))
                        self._write_body(body)
                        self._emit("request_completed", endpoint=path, method="POST", status=int(HTTPStatus.ACCEPTED))
                        return
                    except Exception as exc:
                        code, _msg = _map_failure_to_status(_extract_failure_code(exc))
                        if code == HTTPStatus.INTERNAL_SERVER_ERROR:
                            err_code = "internal_error"
                        else:
                            # try to pass through known failure code safely
                            err_code = _extract_failure_code(exc)
                        body = _make_response_body(
                            ok=False,
                            status=code,
                            request_id=req_id,
                            error_code=err_code,
                        )
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("api_operation_failed", endpoint=path, method="POST", status=code)
                        return

                if path == "/v1/execution-outcomes":
                    payload, err = self._read_json_object(req_id)
                    if err is not None:
                        code, body = err
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("request_rejected", endpoint=path, method="POST", status=code)
                        return
                    try:
                        runtime = self._runtime()
                        if runtime is None:
                            raise RuntimeError("runtime_not_running")
                        runtime.process_execution_outcome(payload)  # type: ignore[attr-defined]
                        body = _make_response_body(
                            ok=True,
                            status=int(HTTPStatus.OK),
                            request_id=req_id,
                            data={"processed": True},
                        )
                        self._set_common_headers(int(HTTPStatus.OK))
                        self._write_body(body)
                        self._emit("request_completed", endpoint=path, method="POST", status=int(HTTPStatus.OK))
                        return
                    except Exception as exc:
                        code, _msg = _map_failure_to_status(_extract_failure_code(exc))
                        if code == HTTPStatus.INTERNAL_SERVER_ERROR:
                            err_code = "internal_error"
                        else:
                            err_code = _extract_failure_code(exc)
                        body = _make_response_body(
                            ok=False,
                            status=code,
                            request_id=req_id,
                            error_code=err_code,
                        )
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("api_operation_failed", endpoint=path, method="POST", status=code)
                        return

                # Lifecycle endpoints (guarded by flag)
                lifecycle_allowed = bool(cfg.enable_lifecycle_endpoints)
                if path in (
                    "/v1/runtime/start",
                    "/v1/runtime/stop",
                    "/v1/components/background-worker/start",
                    "/v1/components/background-worker/stop",
                    "/v1/components/autonomous-controller/start",
                    "/v1/components/autonomous-controller/stop",
                ):
                    if not lifecycle_allowed:
                        code, msg = _map_failure_to_status("lifecycle_disabled")
                        body = _make_response_body(
                            ok=False, status=code, request_id=req_id, error_code="lifecycle_disabled"
                        )
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("request_rejected", endpoint=path, method="POST", status=code)
                        return
                    try:
                        runtime = self._runtime()
                        if runtime is None:
                            raise RuntimeError("runtime_not_running")
                        if path == "/v1/runtime/start":
                            getattr(runtime, "start")()  # type: ignore[attr-defined]
                        elif path == "/v1/runtime/stop":
                            getattr(runtime, "stop")()  # type: ignore[attr-defined]
                        elif path == "/v1/components/background-worker/start":
                            getattr(runtime, "start_background_worker")()  # type: ignore[attr-defined]
                        elif path == "/v1/components/background-worker/stop":
                            getattr(runtime, "stop_background_worker")()  # type: ignore[attr-defined]
                        elif path == "/v1/components/autonomous-controller/start":
                            getattr(runtime, "start_autonomous_controller")()  # type: ignore[attr-defined]
                        elif path == "/v1/components/autonomous-controller/stop":
                            getattr(runtime, "stop_autonomous_controller")()  # type: ignore[attr-defined]
                        else:
                            raise RuntimeError("not_found")
                        body = _make_response_body(
                            ok=True, status=int(HTTPStatus.OK), request_id=req_id, data={"accepted": True}
                        )
                        self._set_common_headers(int(HTTPStatus.OK))
                        self._write_body(body)
                        self._emit("request_completed", endpoint=path, method="POST", status=int(HTTPStatus.OK))
                        return
                    except Exception as exc:
                        code, _ = _map_failure_to_status(_extract_failure_code(exc))
                        if code == HTTPStatus.INTERNAL_SERVER_ERROR:
                            err_code = "internal_error"
                        else:
                            err_code = _extract_failure_code(exc)
                        body = _make_response_body(
                            ok=False, status=code, request_id=req_id, error_code=err_code
                        )
                        self._set_common_headers(code)
                        self._write_body(body)
                        self._emit("api_operation_failed", endpoint=path, method="POST", status=code)
                        return

                # Default: not found or method not allowed
                body = _make_response_body(
                    ok=False,
                    status=int(HTTPStatus.NOT_FOUND),
                    request_id=req_id,
                    error_code="not_found",
                )
                self._set_common_headers(int(HTTPStatus.NOT_FOUND))
                self._write_body(body)
                self._emit("request_rejected", endpoint=path, method="POST", status=int(HTTPStatus.NOT_FOUND))

            def do_PUT(self) -> None:  # noqa: N802
                self._method_not_allowed()

            def do_DELETE(self) -> None:  # noqa: N802
                self._method_not_allowed()

            def _method_not_allowed(self) -> None:
                req_id = self._request_id()
                path = self.path.split("?", 1)[0]
                body = _make_response_body(
                    ok=False, status=int(HTTPStatus.METHOD_NOT_ALLOWED), request_id=req_id, error_code="method_not_allowed"
                )
                self._set_common_headers(int(HTTPStatus.METHOD_NOT_ALLOWED))
                self._write_body(body)
                self._emit("request_rejected", endpoint=path, method=self.command, status=int(HTTPStatus.METHOD_NOT_ALLOWED))

        return Handler


def _make_response_body(
    *,
    ok: bool,
    status: int,
    request_id: Optional[str] = None,
    request_id_out: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "ok": bool(ok),
        "status": int(status),
        "timestamp": _utc_timestamp_iso(),
    }
    if request_id:
        body["request_id"] = request_id
    if request_id_out:
        body["request_id"] = request_id_out  # expose when safely available (override for outward id)
    if data is not None:
        # Copy to avoid accidental mutation
        body["data"] = dict(data)
    else:
        body["data"] = None
    if not ok:
        code = error_code or "internal_error"
        body["error"] = {
            "code": code,
            "message": _SAFE_ERROR_MESSAGES.get(code, _SAFE_ERROR_MESSAGES["internal_error"]),
        }
    else:
        body["error"] = None
    return body


def build_runtime_private_api(
    config: Union[RuntimeAPIConfig, Mapping[str, Any]],
    runtime: Optional[Any] = None,
    token_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> RuntimePrivateAPI:
    # Do not eagerly resolve authentication. Accept empty auth_token_reference.
    cfg = config if isinstance(config, RuntimeAPIConfig) else RuntimeAPIConfig.from_mapping(config)
    return RuntimePrivateAPI(cfg, runtime=runtime, token_resolver=token_resolver)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime Private API")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", default="8765", help="Bind port (0 for ephemeral)")
    parser.add_argument("--data-root", dest="data_root", default=None, help="Data root directory")
    parser.add_argument("--repository-root", dest="repository_root", default=None, help="Repository root directory")
    parser.add_argument("--default-project-id", dest="default_project_id", default=None, help="Default project ID")
    parser.add_argument("--environment-name", dest="environment_name", default=None, help="Environment name")
    parser.add_argument(
        "--auth-token-env",
        dest="auth_token_env",
        default=None,
        help="Environment variable name that holds the bearer auth token",
    )
    parser.add_argument(
        "--enable-lifecycle-endpoints",
        dest="enable_lifecycle_endpoints",
        action="store_true",
        help="Enable lifecycle endpoints",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # Validate host/port early
    try:
        port = int(args.port)
    except (TypeError, ValueError):
        print("Invalid --port; must be an integer", file=sys.stderr)
        return 2

    try:
        api_cfg = RuntimeAPIConfig.from_mapping(
            {
                "host": str(args.host),
                "port": port,
                "enable_lifecycle_endpoints": bool(args.enable_lifecycle_endpoints),
                "auth_token_reference": str(args.auth_token_env or ""),
            }
        )
    except Exception as exc:
        print(f"Invalid API configuration: {exc}", file=sys.stderr)
        return 2

    # Lazy token resolver: do not access environment until request time. However, define resolver function.
    def _env_token_resolver(ref: str) -> Optional[str]:
        try:
            # Never raise here; return None if missing
            val = os.environ.get(ref)
            return val if val else None
        except Exception:
            return None

    # Build runtime using existing public interfaces. Import lazily to avoid import errors in environments
    # where runtime components are unavailable unless main() is invoked.
    try:
        # Import within main to prevent import-time failures in test contexts that do not require runtime.
        from agent.runtime import build_runtime as _build_runtime  # type: ignore
        from agent.runtime import ApplicationConfig as _ApplicationConfig  # type: ignore
        from agent.runtime import RuntimeConfig as _RuntimeConfig  # type: ignore
    except Exception as exc:
        print(f"Failed to import runtime components: {exc}", file=sys.stderr)
        return 1

    try:
        app_cfg_kwargs: Dict[str, Any] = {}
        if args.data_root is not None:
            app_cfg_kwargs["data_root"] = args.data_root
        if args.repository_root is not None:
            app_cfg_kwargs["repository_root"] = args.repository_root
        if args.default_project_id is not None:
            app_cfg_kwargs["default_project_id"] = args.default_project_id
        if args.environment_name is not None:
            app_cfg_kwargs["environment_name"] = args.environment_name

        application_config = _ApplicationConfig(**app_cfg_kwargs)  # type: ignore[arg-type]
        runtime_config = _RuntimeConfig()  # type: ignore[call-arg]
        runtime = _build_runtime(application_config, runtime_config)  # type: ignore[misc]
        # Start runtime service using its public lifecycle method if available
        try:
            runtime.start()
        except Exception:
            # If start is not required/available, continue
            pass
    except Exception as exc:
        print(f"Failed to build or start runtime: {exc}", file=sys.stderr)
        return 1

    api = build_runtime_private_api(api_cfg, runtime=runtime, token_resolver=_env_token_resolver)

    # Signal handling to stop serving gracefully
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception:
        # Not all environments allow setting signals; continue without
        pass

    try:
        api.start()
    except Exception as exc:
        print(f"Failed to start API: {exc}", file=sys.stderr)
        try:
            # Ensure runtime is stopped if API fails to start
            try:
                runtime.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
        finally:
            return 1

    # Block until signal
    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            api.stop()
            api.close()
        except Exception:
            pass
        try:
            runtime.stop()  # type: ignore[attr-defined]
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
