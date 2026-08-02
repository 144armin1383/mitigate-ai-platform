from __future__ import annotations

import argparse
import datetime as _dt
import hmac
import http.server
import json
import signal
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, MutableMapping, Optional, Tuple
from collections import deque
import sys
import traceback

# Note: We intentionally avoid dynamic imports. The following imports are attempted statically.
# Some repositories may provide these in different modules; main() will handle failures safely.
try:
    from agent.runtime import ApplicationConfig as _ApplicationConfig  # type: ignore
except Exception:  # pragma: no cover - import path may vary in different repos
    _ApplicationConfig = None  # type: ignore

try:
    from agent.runtime import RuntimeConfig as _RuntimeConfig  # type: ignore
except Exception:  # pragma: no cover
    _RuntimeConfig = None  # type: ignore

try:
    from agent.runtime import build_runtime as _build_runtime  # type: ignore
except Exception:  # pragma: no cover
    _build_runtime = None  # type: ignore

try:
    from agent.runtime import runtime_status as _runtime_status  # type: ignore
except Exception:  # pragma: no cover
    _runtime_status = None  # type: ignore


# Types
TokenResolver = Callable[[str], Optional[str]]


def _utcnow_iso() -> str:
    # Produce deterministic ISO-8601 UTC timestamp with Z suffix
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass(slots=True)
class RuntimeAPIConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    request_body_limit_bytes: int = 1048576
    response_body_limit_bytes: int = 1048576
    request_timeout_seconds: float = 30.0
    graceful_shutdown_timeout_seconds: float = 15.0
    enable_lifecycle_endpoints: bool = False
    auth_token_reference: str = field(default_factory=str)
    token_resolver: TokenResolver | None = None

    def validate(self) -> None:
        # Host validation
        if not isinstance(self.host, str) or not self.host:
            raise ValueError("invalid_config: host must be a non-empty string")
        # Reject wildcard public hosts
        if self.host in ("0.0.0.0", "::"):
            raise ValueError("invalid_config: public wildcard hosts are not allowed")
        # Port validation (0 allowed for ephemeral)
        if not isinstance(self.port, int) or self.port < 0 or self.port > 65535:
            raise ValueError("invalid_config: port must be in range 0..65535")
        # Body limits
        if not isinstance(self.request_body_limit_bytes, int) or self.request_body_limit_bytes <= 0:
            raise ValueError("invalid_config: request_body_limit_bytes must be > 0")
        if not isinstance(self.response_body_limit_bytes, int) or self.response_body_limit_bytes <= 0:
            raise ValueError("invalid_config: response_body_limit_bytes must be > 0")
        # Timeouts
        if not (isinstance(self.request_timeout_seconds, (int, float)) and self.request_timeout_seconds > 0):
            raise ValueError("invalid_config: request_timeout_seconds must be > 0")
        if not (isinstance(self.graceful_shutdown_timeout_seconds, (int, float)) and self.graceful_shutdown_timeout_seconds > 0):
            raise ValueError("invalid_config: graceful_shutdown_timeout_seconds must be > 0")
        # Auth ref
        if not isinstance(self.auth_token_reference, str) or not self.auth_token_reference.strip():
            raise ValueError("invalid_config: auth_token_reference must be non-empty")
        # Token resolver presence checked during build


# Event structure limited to safe keys only
SafeEvent = Dict[str, Any]


class _EventRecorder:
    def __init__(self, capacity: int = 1024) -> None:
        self._events: Deque[SafeEvent] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, event: SafeEvent) -> None:
        safe: SafeEvent = {}
        # Only allow safe keys
        for k in ("endpoint", "method", "status", "runtime_state", "timestamp", "failure_code"):
            if k in event and event[k] is not None:
                safe[k] = event[k]
        with self._lock:
            self._events.append(safe)

    def latest(self, limit: int) -> List[SafeEvent]:
        if limit <= 0:
            return []
        with self._lock:
            return list(self._events)[-limit:]


# Failure mapping per specification
_FAILURE_TO_STATUS: Dict[str, int] = {
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


def _failure_code_from_exception(exc: BaseException) -> str:
    # Attempt to extract a domain-specific code without exposing raw internals
    # 1) code attribute
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    # 2) error_code attribute
    code = getattr(exc, "error_code", None)
    if isinstance(code, str) and code:
        return code
    # 3) known builtin mappings
    if isinstance(exc, (json.JSONDecodeError, ValueError, KeyError, TypeError)):
        return "invalid_request"
    if isinstance(exc, PermissionError):
        return "cross_project_reference"
    # Unknown
    return "internal_error"


def _status_from_failure_code(code: str) -> int:
    return _FAILURE_TO_STATUS.get(code, 500)


def _safe_message_for_code(code: str) -> str:
    safe_messages: Dict[str, str] = {
        "invalid_request": "Invalid request.",
        "invalid_execution_outcome": "Invalid execution outcome.",
        "runtime_not_running": "Runtime is not running.",
        "invalid_runtime_transition": "Invalid runtime transition.",
        "duplicate_execution": "Duplicate execution.",
        "invalid_status_transition": "Invalid status transition.",
        "mission_not_found": "Mission not found.",
        "budget_blocked": "Budget blocked.",
        "rate_limit_blocked": "Rate limit exceeded.",
        "unknown_project": "Unknown project.",
        "cross_project_reference": "Forbidden cross-project reference.",
        "no_model_available": "Service unavailable.",
        "planner_failed": "Service unavailable.",
        "queue_resolution_failed": "Service unavailable.",
        "queue_failed": "Service unavailable.",
        "usage_recording_failed": "Service unavailable.",
        "report_persistence_failed": "Service unavailable.",
        "dependency_failed": "Service unavailable.",
        "internal_error": "Internal error.",
        "request_timeout": "Request timeout.",
        "unauthorized": "Authentication required.",
        "forbidden": "Forbidden.",
        "not_found": "Not found.",
        "method_not_allowed": "Method not allowed.",
        "unsupported_media_type": "Unsupported media type.",
        "payload_too_large": "Payload too large.",
        "bad_gateway": "Bad gateway.",
        "service_unavailable": "Service unavailable.",
    }
    return safe_messages.get(code, "Internal error.")


class _JSONResponseBuilder:
    def __init__(self, response_size_limit: int) -> None:
        self._limit = response_size_limit

    def build(self, *, ok: bool, status: int, data: Optional[Dict[str, Any]] = None,
              error: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None) -> Tuple[bytes, int, str]:
        body: Dict[str, Any] = {
            "ok": bool(ok),
            "status": int(status),
            "timestamp": _utcnow_iso(),
        }
        if request_id:
            body["request_id"] = str(request_id)
        if data is not None:
            body["data"] = data
        if error is not None:
            # Only allow code and message in error
            safe_err: Dict[str, Any] = {}
            if "code" in error:
                safe_err["code"] = error["code"]
            if "message" in error:
                safe_err["message"] = error["message"]
            body["error"] = safe_err
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) <= self._limit:
            return payload, len(payload), "application/json; charset=utf-8"
        # If response too large, fallback to minimal safe error
        minimal: Dict[str, Any] = {
            "ok": False,
            "status": 500,
            "timestamp": _utcnow_iso(),
            "error": {"code": "internal_error", "message": _safe_message_for_code("internal_error")},
        }
        payload2 = json.dumps(minimal, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return payload2, len(payload2), "application/json; charset=utf-8"


class RuntimePrivateAPI:
    def __init__(self, *, config: RuntimeAPIConfig, runtime: Any, resolved_token: str) -> None:
        self._config = config
        self._runtime = runtime
        self._resolved_token = resolved_token
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._serve_ready = threading.Event()
        self._stopping = threading.Event()
        self._closed = threading.Event()
        self._address: Optional[Tuple[str, int]] = None
        self._events = _EventRecorder()
        self._json_builder = _JSONResponseBuilder(config.response_body_limit_bytes)
        self._lock = threading.RLock()
        # Emit api_created event
        self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "-", "method": "-", "status": None, "runtime_state": None})

    # Context manager support
    def __enter__(self) -> "RuntimePrivateAPI":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        try:
            self.stop()
        finally:
            self.close()

    # Public lifecycle
    def start(self) -> None:
        with self._lock:
            if self._server is not None:
                return  # idempotent
            self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "-", "method": "-", "status": None, "runtime_state": None})
            self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_starting", "method": "-"})
            try:
                # Initialize server bound to configured host/port
                handler_cls = self._build_handler_class()
                # Create server socket bound before returning
                server = http.server.ThreadingHTTPServer((self._config.host, self._config.port), handler_cls, bind_and_activate=True)
                # Set socket options
                server.daemon_threads = True  # do not prevent process exit
                server.timeout = self._config.request_timeout_seconds
                self._server = server
                # Store actual bound address
                sa = server.server_address
                host = sa[0]
                port = sa[1]
                if not isinstance(port, int) or port <= 0:
                    raise OSError("failed_to_bind")
                self._address = (host, port)
                # Start serving thread
                self._thread = threading.Thread(target=self._serve, name="RuntimePrivateAPIServer", daemon=True)
                self._thread.start()
                # Wait until serving loop ready (bounded)
                if not self._serve_ready.wait(timeout=5.0):  # bounded deterministic sync
                    # Readiness failed; shutdown and report
                    try:
                        self._safe_shutdown_server()
                    finally:
                        self._server = None
                        self._thread = None
                    self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_start_failed", "method": "-", "failure_code": "api_start_failed"})
                    raise RuntimeError("api_start_failed")
                self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_started", "method": "-"})
            except Exception:
                self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_start_failed", "method": "-", "failure_code": "api_start_failed"})
                raise

    def serve_forever(self) -> None:
        # Block until the serving thread terminates
        t = self._thread
        if t is None:
            return
        if t.is_alive():
            try:
                t.join()
            except KeyboardInterrupt:
                # Propagate up for main to handle if needed
                raise

    def stop(self) -> None:
        with self._lock:
            if self._server is None:
                return
            if self._stopping.is_set():
                return
            self._stopping.set()
        # Do not hold locks while calling shutdown()
        self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_stopping", "method": "-"})
        self._safe_shutdown_server()
        self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_stopped", "method": "-"})

    def close(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
            thread = self._thread
            self._thread = None
            self._address = None
            self._closed.set()
        if server is not None:
            try:
                server.server_close()
            except Exception:
                # Swallow errors during close; do not expose
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass

    def status(self) -> str:
        # Return a simple lifecycle string
        if self._server is not None and self._thread is not None and self._thread.is_alive():
            return "running"
        if self._closed.is_set():
            return "closed"
        return "stopped"

    def address(self) -> Optional[Tuple[str, int]]:
        return self._address

    def latest_events(self, limit: int = 50) -> List[SafeEvent]:
        return self._events.latest(limit)

    # Internal methods
    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        # Once the server loop starts, set ready flag
        self._serve_ready.set()
        try:
            server.serve_forever(poll_interval=0.5)
        except Exception:
            # Record failure but do not propagate raw exceptions
            self._events.emit({"timestamp": _utcnow_iso(), "endpoint": "api_operation_failed", "method": "-", "failure_code": "internal_error"})
        finally:
            # Ensure server closed if needed
            try:
                server.server_close()
            except Exception:
                pass

    def _safe_shutdown_server(self) -> None:
        server = self._server
        thread = self._thread
        if server is None:
            return
        try:
            server.shutdown()
        except Exception:
            pass
        # Join thread bounded
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout=float(self._config.graceful_shutdown_timeout_seconds))
            except Exception:
                pass

    def _build_handler_class(self):
        api = self

        class Handler(http.server.BaseHTTPRequestHandler):  # type: ignore[misc]
            server_version = "RuntimePrivateAPI/1.0"
            sys_version = ""

            # Disable default request logging to avoid leaking
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            # Common utils
            def _set_common_headers(self, status: int, content_length: int, content_type: str = "application/json; charset=utf-8") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(content_length))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()

            def _emit_event(self, name: str, status: Optional[int] = None, failure_code: Optional[str] = None) -> None:
                try:
                    api._events.emit({
                        "endpoint": self.path,
                        "method": self.command,
                        "status": status,
                        "timestamp": _utcnow_iso(),
                        "failure_code": failure_code,
                    })
                except Exception:
                    pass

            def _authenticate(self) -> Tuple[bool, Optional[int], Optional[bytes]]:
                # Health live endpoint may be unauthenticated
                if self.command == "GET" and self.path == "/health/live":
                    return True, None, None
                hdr = self.headers.get("Authorization")
                if not hdr:
                    # 401 missing auth
                    payload, length, ctype = api._json_builder.build(ok=False, status=401, error={
                        "code": "unauthorized",
                        "message": _safe_message_for_code("unauthorized"),
                    })
                    # Note: do not include WWW-Authenticate details beyond scheme
                    self.send_response(401)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Content-Length", str(length))
                    self.send_header("WWW-Authenticate", "Bearer")
                    self.end_headers()
                    api._events.emit({"endpoint": self.path, "method": self.command, "timestamp": _utcnow_iso(), "failure_code": "unauthorized", "status": 401})
                    return False, 401, payload
                scheme = "Bearer "
                if not hdr.startswith(scheme):
                    payload, length, ctype = api._json_builder.build(ok=False, status=403, error={
                        "code": "forbidden",
                        "message": _safe_message_for_code("forbidden"),
                    })
                    self._set_common_headers(403, length, ctype)
                    self.wfile.write(payload)
                    api._events.emit({"endpoint": self.path, "method": self.command, "timestamp": _utcnow_iso(), "failure_code": "forbidden", "status": 403})
                    return False, 403, payload
                token = hdr[len(scheme):].strip()
                # Compare using constant-time
                try:
                    expected = api._resolved_token
                    ok = bool(token) and hmac.compare_digest(token, expected)
                except Exception:
                    ok = False
                if not ok:
                    payload, length, ctype = api._json_builder.build(ok=False, status=403, error={
                        "code": "forbidden",
                        "message": _safe_message_for_code("forbidden"),
                    })
                    self._set_common_headers(403, length, ctype)
                    self.wfile.write(payload)
                    api._events.emit({"endpoint": self.path, "method": self.command, "timestamp": _utcnow_iso(), "failure_code": "forbidden", "status": 403})
                    return False, 403, payload
                return True, None, None

            def _read_json_object(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, bytes]]]:
                # Enforce content-type
                ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    payload, length, ct = api._json_builder.build(ok=False, status=415, error={
                        "code": "unsupported_media_type",
                        "message": _safe_message_for_code("unsupported_media_type"),
                    })
                    return None, (415, payload)
                # Enforce body limit using Content-Length
                cl_raw = self.headers.get("Content-Length")
                if cl_raw is None:
                    payload, length, ct = api._json_builder.build(ok=False, status=400, error={
                        "code": "invalid_request",
                        "message": _safe_message_for_code("invalid_request"),
                    })
                    return None, (400, payload)
                try:
                    content_length = int(cl_raw)
                except Exception:
                    payload, length, ct = api._json_builder.build(ok=False, status=400, error={
                        "code": "invalid_request",
                        "message": _safe_message_for_code("invalid_request"),
                    })
                    return None, (400, payload)
                if content_length > api._config.request_body_limit_bytes:
                    payload, length, ct = api._json_builder.build(ok=False, status=413, error={
                        "code": "payload_too_large",
                        "message": _safe_message_for_code("payload_too_large"),
                    })
                    return None, (413, payload)
                # Set socket timeout for request body operations
                try:
                    self.connection.settimeout(float(api._config.request_timeout_seconds))
                except Exception:
                    pass
                try:
                    raw = self.rfile.read(content_length)
                except socket.timeout:
                    payload, length, ct = api._json_builder.build(ok=False, status=408, error={
                        "code": "request_timeout",
                        "message": _safe_message_for_code("request_timeout"),
                    })
                    return None, (408, payload)
                except Exception:
                    payload, length, ct = api._json_builder.build(ok=False, status=400, error={
                        "code": "invalid_request",
                        "message": _safe_message_for_code("invalid_request"),
                    })
                    return None, (400, payload)
                try:
                    data = json.loads(raw.decode("utf-8"))
                except Exception:
                    payload, length, ct = api._json_builder.build(ok=False, status=400, error={
                        "code": "invalid_request",
                        "message": _safe_message_for_code("invalid_request"),
                    })
                    return None, (400, payload)
                if not isinstance(data, MutableMapping):
                    payload, length, ct = api._json_builder.build(ok=False, status=400, error={
                        "code": "invalid_request",
                        "message": _safe_message_for_code("invalid_request"),
                    })
                    return None, (400, payload)
                return dict(data), None

            def _get_runtime_safe_status(self) -> Dict[str, Any]:
                rt = api._runtime
                # Prefer provided runtime_status function if available
                try:
                    if _runtime_status is not None:
                        status = _runtime_status(rt)  # type: ignore[misc]
                        if isinstance(status, MutableMapping):
                            return dict(status)
                except Exception:
                    pass
                # Fallbacks: try calling .status()
                try:
                    s = getattr(rt, "status", None)
                    if callable(s):
                        res = s()
                        if isinstance(res, MutableMapping):
                            return dict(res)
                        # Try to coerce object to dict using __dict__ safely
                        if hasattr(res, "__dict__"):
                            return {k: v for k, v in vars(res).items() if not k.startswith("_")}
                except Exception:
                    pass
                return {}

            def _runtime_is_ready(self) -> bool:
                st = self._get_runtime_safe_status()
                state = st.get("state")
                app_ready = st.get("application_ready")
                return (state == "running") and (app_ready is True)

            # Endpoint handlers
            def do_GET(self) -> None:  # noqa: N802
                api._events.emit({"endpoint": self.path, "method": "GET", "timestamp": _utcnow_iso()})
                if self.path == "/health/live":
                    payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"alive": True})
                    self._set_common_headers(200, length, ctype)
                    self.wfile.write(payload)
                    self._emit_event("request_completed", 200)
                    return
                ok, _, unauthorized_payload = self._authenticate()
                if not ok:
                    # Payload already sent in _authenticate
                    if unauthorized_payload is not None:
                        self.wfile.write(unauthorized_payload)
                    self._emit_event("authentication_failed", 401)
                    return
                if self.path == "/health/ready":
                    if self._runtime_is_ready():
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"ready": True})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    else:
                        payload, length, ctype = api._json_builder.build(ok=False, status=503, error={
                            "code": "service_unavailable",
                            "message": _safe_message_for_code("service_unavailable"),
                        })
                        self._set_common_headers(503, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 503)
                        return
                if self.path == "/v1/runtime/status":
                    st = self._get_runtime_safe_status()
                    # Ensure only safe keys included
                    payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"runtime": st})
                    self._set_common_headers(200, length, ctype)
                    self.wfile.write(payload)
                    self._emit_event("request_completed", 200)
                    return
                # Unknown endpoint
                payload, length, ctype = api._json_builder.build(ok=False, status=404, error={
                    "code": "not_found",
                    "message": _safe_message_for_code("not_found"),
                })
                self._set_common_headers(404, length, ctype)
                self.wfile.write(payload)
                self._emit_event("request_rejected", 404, failure_code="not_found")

            def do_POST(self) -> None:  # noqa: N802
                api._events.emit({"endpoint": self.path, "method": "POST", "timestamp": _utcnow_iso()})
                ok, _, unauthorized_payload = self._authenticate()
                if not ok:
                    if unauthorized_payload is not None:
                        self._set_common_headers(401, len(unauthorized_payload))
                        self.wfile.write(unauthorized_payload)
                    self._emit_event("authentication_failed", 401)
                    return
                # Lifecycle endpoints guarded by config
                lifecycle_only_paths = {
                    "/v1/runtime/start",
                    "/v1/runtime/stop",
                    "/v1/components/background-worker/start",
                    "/v1/components/background-worker/stop",
                    "/v1/components/autonomous-controller/start",
                    "/v1/components/autonomous-controller/stop",
                }
                if self.path in lifecycle_only_paths and (not api._config.enable_lifecycle_endpoints):
                    payload, length, ctype = api._json_builder.build(ok=False, status=404, error={
                        "code": "not_found",
                        "message": _safe_message_for_code("not_found"),
                    })
                    self._set_common_headers(404, length, ctype)
                    self.wfile.write(payload)
                    self._emit_event("request_rejected", 404, failure_code="not_found")
                    return

                if self.path == "/v1/requests":
                    data, err = self._read_json_object()
                    if err is not None:
                        status, payload = err[0], err[1]
                        self._set_common_headers(status, len(payload))
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", status, failure_code="invalid_request")
                        return
                    try:
                        res = getattr(api._runtime, "submit_request")(data)
                        # Try to extract request_id from result if present
                        req_id: Optional[str] = None
                        if isinstance(res, MutableMapping):
                            rid = res.get("request_id")
                            if isinstance(rid, str):
                                req_id = rid
                        payload, length, ctype = api._json_builder.build(ok=True, status=202, data={"accepted": True}, request_id=req_id)
                        self._set_common_headers(202, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 202)
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={
                            "code": code,
                            "message": _safe_message_for_code(code),
                        })
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                if self.path == "/v1/execution-outcomes":
                    data, err = self._read_json_object()
                    if err is not None:
                        status, payload = err[0], err[1]
                        self._set_common_headers(status, len(payload))
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", status, failure_code="invalid_request")
                        return
                    try:
                        getattr(api._runtime, "process_execution_outcome")(data)
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"processed": True})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={
                            "code": code,
                            "message": _safe_message_for_code(code),
                        })
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                # Lifecycle endpoints
                if self.path == "/v1/runtime/start":
                    try:
                        start_fn = getattr(api._runtime, "start", None)
                        if not callable(start_fn):
                            raise NotImplementedError
                        start_fn()
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"started": True})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except NotImplementedError:
                        payload, length, ctype = api._json_builder.build(ok=False, status=501, error={
                            "code": "not_found",
                            "message": _safe_message_for_code("not_found"),
                        })
                        self._set_common_headers(501, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", 501, failure_code="not_found")
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={"code": code, "message": _safe_message_for_code(code)})
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                if self.path == "/v1/runtime/stop":
                    try:
                        stop_fn = getattr(api._runtime, "stop", None)
                        if not callable(stop_fn):
                            raise NotImplementedError
                        stop_fn()
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"stopped": True})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except NotImplementedError:
                        payload, length, ctype = api._json_builder.build(ok=False, status=501, error={
                            "code": "not_found",
                            "message": _safe_message_for_code("not_found"),
                        })
                        self._set_common_headers(501, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", 501, failure_code="not_found")
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={"code": code, "message": _safe_message_for_code(code)})
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                if self.path == "/v1/components/background-worker/start":
                    try:
                        fn = getattr(api._runtime, "start_background_worker", None)
                        if not callable(fn):
                            raise NotImplementedError
                        fn()
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"background_worker": "started"})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except NotImplementedError:
                        payload, length, ctype = api._json_builder.build(ok=False, status=501, error={
                            "code": "not_found",
                            "message": _safe_message_for_code("not_found"),
                        })
                        self._set_common_headers(501, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", 501, failure_code="not_found")
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={"code": code, "message": _safe_message_for_code(code)})
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                if self.path == "/v1/components/background-worker/stop":
                    try:
                        fn = getattr(api._runtime, "stop_background_worker", None)
                        if not callable(fn):
                            raise NotImplementedError
                        fn()
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"background_worker": "stopped"})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except NotImplementedError:
                        payload, length, ctype = api._json_builder.build(ok=False, status=501, error={
                            "code": "not_found",
                            "message": _safe_message_for_code("not_found"),
                        })
                        self._set_common_headers(501, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", 501, failure_code="not_found")
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={"code": code, "message": _safe_message_for_code(code)})
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                if self.path == "/v1/components/autonomous-controller/start":
                    try:
                        fn = getattr(api._runtime, "start_autonomous_controller", None)
                        if not callable(fn):
                            raise NotImplementedError
                        fn()
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"autonomous_controller": "started"})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except NotImplementedError:
                        payload, length, ctype = api._json_builder.build(ok=False, status=501, error={
                            "code": "not_found",
                            "message": _safe_message_for_code("not_found"),
                        })
                        self._set_common_headers(501, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", 501, failure_code="not_found")
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={"code": code, "message": _safe_message_for_code(code)})
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                if self.path == "/v1/components/autonomous-controller/stop":
                    try:
                        fn = getattr(api._runtime, "stop_autonomous_controller", None)
                        if not callable(fn):
                            raise NotImplementedError
                        fn()
                        payload, length, ctype = api._json_builder.build(ok=True, status=200, data={"autonomous_controller": "stopped"})
                        self._set_common_headers(200, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", 200)
                        return
                    except NotImplementedError:
                        payload, length, ctype = api._json_builder.build(ok=False, status=501, error={
                            "code": "not_found",
                            "message": _safe_message_for_code("not_found"),
                        })
                        self._set_common_headers(501, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_rejected", 501, failure_code="not_found")
                        return
                    except Exception as exc:
                        code = _failure_code_from_exception(exc)
                        status = _status_from_failure_code(code)
                        payload, length, ctype = api._json_builder.build(ok=False, status=status, error={"code": code, "message": _safe_message_for_code(code)})
                        self._set_common_headers(status, length, ctype)
                        self.wfile.write(payload)
                        self._emit_event("request_completed", status, failure_code=code)
                        return

                # Unknown endpoint
                payload, length, ctype = api._json_builder.build(ok=False, status=404, error={
                    "code": "not_found",
                    "message": _safe_message_for_code("not_found"),
                })
                self._set_common_headers(404, length, ctype)
                self.wfile.write(payload)
                self._emit_event("request_rejected", 404, failure_code="not_found")

        return Handler


def build_runtime_private_api(config: RuntimeAPIConfig, runtime: Any | None = None) -> RuntimePrivateAPI:
    # Validate config
    if not isinstance(config, RuntimeAPIConfig):
        raise TypeError("config must be RuntimeAPIConfig")
    config.validate()
    # Resolve token using provided resolver or defaulting to env
    resolver: Optional[TokenResolver] = config.token_resolver
    if resolver is None:
        # Default resolver reads from environment variables
        def _env_resolver(ref: str) -> Optional[str]:
            import os
            return os.environ.get(ref)
        resolver = _env_resolver
    token = resolver(config.auth_token_reference) or ""
    if not token:
        raise ValueError("invalid_config: failed to resolve authentication token from reference")
    if runtime is None:
        raise ValueError("runtime instance must be provided to build_runtime_private_api")
    return RuntimePrivateAPI(config=config, runtime=runtime, resolved_token=token)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="runtime-private-api", add_help=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", dest="data_root", default=None)
    parser.add_argument("--repository-root", dest="repository_root", default=None)
    parser.add_argument("--default-project-id", dest="default_project_id", default=None)
    parser.add_argument("--environment-name", dest="environment_name", default=None)
    parser.add_argument("--auth-token-env", dest="auth_token_env", required=True)
    parser.add_argument("--enable-lifecycle-endpoints", dest="enable_lifecycle_endpoints", action="store_true", default=False)

    args = parser.parse_args(argv)

    # Validate host
    if args.host in ("0.0.0.0", "::"):
        print("Error: public wildcard hosts are not allowed", file=sys.stderr)
        return 2

    # Resolve token from environment
    try:
        import os
        token = os.environ.get(args.auth_token_env, "")
    except Exception:
        token = ""
    if not token:
        print("Error: authentication token not found in environment", file=sys.stderr)
        return 2

    # Build runtime via existing interfaces (if available)
    if _ApplicationConfig is None or _RuntimeConfig is None or _build_runtime is None:
        print("Error: runtime interfaces not available in this environment", file=sys.stderr)
        return 2

    try:
        # Construct application and runtime configs using available constructors
        # We avoid exposing full configs outside; only use for runtime construction
        app_kwargs: Dict[str, Any] = {}
        if args.data_root is not None:
            app_kwargs["data_root"] = args.data_root
        if args.repository_root is not None:
            app_kwargs["repository_root"] = args.repository_root
        if args.default_project_id is not None:
            app_kwargs["default_project_id"] = args.default_project_id
        if args.environment_name is not None:
            app_kwargs["environment_name"] = args.environment_name
        application_config = _ApplicationConfig(**app_kwargs)  # type: ignore

        runtime_config = _RuntimeConfig(application=application_config)  # type: ignore[arg-type]
        runtime = _build_runtime(runtime_config)  # type: ignore[misc]
    except Exception as exc:
        # Do not expose raw exception details
        print("Error: failed to build runtime", file=sys.stderr)
        return 2

    # Start runtime service
    try:
        start_fn = getattr(runtime, "start", None)
        if callable(start_fn):
            start_fn()
    except Exception:
        print("Error: failed to start runtime", file=sys.stderr)
        return 2

    # Build API config and server
    def _env_resolver(ref: str) -> Optional[str]:
        import os as _os
        return _os.environ.get(ref)

    api_config = RuntimeAPIConfig(
        host=args.host,
        port=int(args.port),
        enable_lifecycle_endpoints=bool(args.enable_lifecycle_endpoints),
        auth_token_reference=str(args.auth_token_env),
        token_resolver=_env_resolver,
    )

    try:
        api = build_runtime_private_api(api_config, runtime=runtime)
    except Exception:
        print("Error: failed to build API", file=sys.stderr)
        try:
            stop_fn = getattr(runtime, "stop", None)
            if callable(stop_fn):
                stop_fn()
        except Exception:
            pass
        return 2

    # Signal handling
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
        if not stop_event.is_set():
            stop_event.set()
            # Stop API in a separate thread to avoid blocking in signal handler
            threading.Thread(target=api.stop, name="api-stop-signal", daemon=True).start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    # Start API
    try:
        api.start()
    except Exception:
        print("Error: failed to start API", file=sys.stderr)
        try:
            stop_fn = getattr(runtime, "stop", None)
            if callable(stop_fn):
                stop_fn()
        except Exception:
            pass
        return 2

    # Serve until signal
    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        try:
            api.stop()
        except Exception:
            pass
        try:
            api.close()
        except Exception:
            pass
        try:
            stop_fn = getattr(runtime, "stop", None)
            if callable(stop_fn):
                stop_fn()
        except Exception:
            pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
