from __future__ import annotations

import argparse
import hmac
import json
import os
import signal
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Deque, Dict, List, Mapping, MutableMapping, Optional, Tuple, Union
from urllib.parse import urlparse


# Types
AuthTokenResolver = Callable[[str], Optional[str]]


@dataclass(frozen=True)
class RuntimeAPIConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    request_body_limit_bytes: int = 1_048_576
    response_body_limit_bytes: int = 1_048_576
    request_timeout_seconds: int = 30
    graceful_shutdown_timeout_seconds: int = 15
    enable_lifecycle_endpoints: bool = False
    auth_token_reference: str = ""
    auth_token_resolver: Optional[AuthTokenResolver] = None

    @staticmethod
    def from_dict(cfg: Mapping[str, Any]) -> "RuntimeAPIConfig":
        allowed = {
            "host",
            "port",
            "request_body_limit_bytes",
            "response_body_limit_bytes",
            "request_timeout_seconds",
            "graceful_shutdown_timeout_seconds",
            "enable_lifecycle_endpoints",
            "auth_token_reference",
            "auth_token_resolver",
        }
        unknown = set(cfg.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown configuration fields: {sorted(unknown)}")
        # Build instance with defaults overridden by provided values
        return RuntimeAPIConfig(
            host=str(cfg.get("host", RuntimeAPIConfig.host)),
            port=int(cfg.get("port", RuntimeAPIConfig.port)),
            request_body_limit_bytes=int(cfg.get("request_body_limit_bytes", RuntimeAPIConfig.request_body_limit_bytes)),
            response_body_limit_bytes=int(cfg.get("response_body_limit_bytes", RuntimeAPIConfig.response_body_limit_bytes)),
            request_timeout_seconds=int(cfg.get("request_timeout_seconds", RuntimeAPIConfig.request_timeout_seconds)),
            graceful_shutdown_timeout_seconds=int(cfg.get("graceful_shutdown_timeout_seconds", RuntimeAPIConfig.graceful_shutdown_timeout_seconds)),
            enable_lifecycle_endpoints=bool(cfg.get("enable_lifecycle_endpoints", RuntimeAPIConfig.enable_lifecycle_endpoints)),
            auth_token_reference=str(cfg.get("auth_token_reference", RuntimeAPIConfig.auth_token_reference)),
            auth_token_resolver=cfg.get("auth_token_resolver", RuntimeAPIConfig.auth_token_resolver),
        )


class _RuntimePrivateHTTPServer(ThreadingHTTPServer):
    # Ensure handler threads do not prevent process exit
    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass: type[BaseHTTPRequestHandler], api: "RuntimePrivateAPI") -> None:
        self.api = api
        super().__init__(server_address, RequestHandlerClass, bind_and_activate=True)
        # Socket timeout for I/O operations
        try:
            self.socket.settimeout(float(api.config.request_timeout_seconds))
        except Exception:
            pass


class _RequestHandler(BaseHTTPRequestHandler):
    # Disable default logging to stderr
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - override
        return

    # Core routing
    def do_GET(self) -> None:  # noqa: N802 - http method naming
        self.server: _RuntimePrivateHTTPServer  # type: ignore[no-redef]
        api = self.server.api
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        method = "GET"
        api._emit_event("request_received", endpoint=path, method=method)
        try:
            # Unauthenticated endpoint
            if path == "/health/live":
                self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="alive", data={"alive": True}))
                api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                return

            # All other GET endpoints require authentication
            auth_ok, http_status, failure_code = api._check_auth(self.headers)
            if not auth_ok:
                api._emit_event("authentication_failed", endpoint=path, method=method, http_status=http_status, failure_code=failure_code)
                self._auth_error(http_status, failure_code)
                return

            if path == "/health/ready":
                status_obj = api._safe_runtime_status()
                ready = bool(status_obj.get("application_ready")) and str(status_obj.get("state")) == "running"
                if ready:
                    self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="ready", data={"ready": True}))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                else:
                    self._respond_json(HTTPStatus.SERVICE_UNAVAILABLE, api._response_envelope(ok=False, status="not_ready", error={"code": "runtime_not_ready", "message": "Runtime is not ready"}))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.SERVICE_UNAVAILABLE)
                return

            if path == "/v1/runtime/status":
                status_obj = api._safe_runtime_status()
                self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data=status_obj))
                api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                return

            # Unknown route
            api._emit_event("request_rejected", endpoint=path, method=method, http_status=HTTPStatus.NOT_FOUND, failure_code="not_found")
            self._respond_json(HTTPStatus.NOT_FOUND, api._response_envelope(ok=False, status="error", error={"code": "not_found", "message": "Unknown route"}))
        except Exception:
            # Never expose raw exception
            api._emit_event("api_operation_failed", endpoint=path, method=method, http_status=HTTPStatus.INTERNAL_SERVER_ERROR, failure_code="internal_error")
            self._respond_json(HTTPStatus.INTERNAL_SERVER_ERROR, api._response_envelope(ok=False, status="error", error={"code": "internal_error", "message": "An internal error occurred"}))

    def do_POST(self) -> None:  # noqa: N802 - http method naming
        self.server: _RuntimePrivateHTTPServer  # type: ignore[no-redef]
        api = self.server.api
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        method = "POST"
        api._emit_event("request_received", endpoint=path, method=method)
        try:
            # Authentication required for all POST endpoints
            auth_ok, http_status, failure_code = api._check_auth(self.headers)
            if not auth_ok:
                api._emit_event("authentication_failed", endpoint=path, method=method, http_status=http_status, failure_code=failure_code)
                self._auth_error(http_status, failure_code)
                return

            # Validate Content-Type
            content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                api._emit_event("request_rejected", endpoint=path, method=method, http_status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE, failure_code="unsupported_media_type")
                self._respond_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, api._response_envelope(ok=False, status="error", error={"code": "unsupported_media_type", "message": "Content-Type must be application/json"}))
                return

            # Read and parse JSON body safely
            try:
                body_obj, body_len = self._read_json_object(api)
            except _ImmediateError as e:
                api._emit_event("request_rejected", endpoint=path, method=method, http_status=e.http_status, failure_code=e.code)
                self._respond_json(e.http_status, api._response_envelope(ok=False, status="error", error={"code": e.code, "message": e.message}))
                return

            # Routing
            if path == "/v1/requests":
                # Submit new request to runtime
                try:
                    runtime = api.runtime
                    if runtime is None:
                        raise RuntimeError("runtime_unavailable")
                    result = runtime.submit_request(body_obj)  # type: ignore[attr-defined]
                    # Accepted
                    safe_request_id = None
                    if isinstance(body_obj, dict) and isinstance(body_obj.get("request_id"), str):
                        safe_request_id = body_obj.get("request_id")
                    data: Dict[str, Any] = {"accepted": True}
                    # If runtime returns a dict with request_id, include it
                    if isinstance(result, dict):
                        rid = result.get("request_id")
                        if isinstance(rid, str):
                            data["request_id"] = rid
                    if safe_request_id and "request_id" not in data:
                        data["request_id"] = safe_request_id
                    self._respond_json(HTTPStatus.ACCEPTED, api._response_envelope(ok=True, status="accepted", request_id=data.get("request_id"), data=data))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.ACCEPTED, request_id=data.get("request_id"))
                    return
                except Exception as exc:  # Map known failures
                    code, status = api._map_failure(exc)
                    self._respond_json(status, api._response_envelope(ok=False, status="error", request_id=body_obj.get("request_id") if isinstance(body_obj, dict) else None, error={"code": code, "message": _safe_message_for_code(code)}))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=status, failure_code=code, request_id=(body_obj.get("request_id") if isinstance(body_obj, dict) else None))
                    return

            if path == "/v1/execution-outcomes":
                try:
                    runtime = api.runtime
                    if runtime is None:
                        raise RuntimeError("runtime_unavailable")
                    runtime.process_execution_outcome(body_obj)  # type: ignore[attr-defined]
                    rid = body_obj.get("request_id") if isinstance(body_obj, dict) else None
                    self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", request_id=rid, data={"processed": True}))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK, request_id=rid)
                    return
                except Exception as exc:
                    code, status = api._map_failure(exc)
                    self._respond_json(status, api._response_envelope(ok=False, status="error", request_id=(body_obj.get("request_id") if isinstance(body_obj, dict) else None), error={"code": code, "message": _safe_message_for_code(code)}))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=status, failure_code=code, request_id=(body_obj.get("request_id") if isinstance(body_obj, dict) else None))
                    return

            # Lifecycle endpoints - gated
            if api.config.enable_lifecycle_endpoints:
                try:
                    runtime = api.runtime
                    if runtime is None:
                        raise RuntimeError("runtime_unavailable")
                    if path == "/v1/runtime/start":
                        runtime.start()  # type: ignore[attr-defined]
                        self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data={"started": True}))
                        api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                        return
                    if path == "/v1/runtime/stop":
                        runtime.stop()  # type: ignore[attr-defined]
                        self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data={"stopped": True}))
                        api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                        return
                    if path == "/v1/components/background-worker/start":
                        if hasattr(runtime, "start_background_worker"):
                            getattr(runtime, "start_background_worker")()  # type: ignore[misc]
                            self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data={"background_worker_started": True}))
                            api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                            return
                        raise AttributeError("start_background_worker")
                    if path == "/v1/components/background-worker/stop":
                        if hasattr(runtime, "stop_background_worker"):
                            getattr(runtime, "stop_background_worker")()  # type: ignore[misc]
                            self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data={"background_worker_stopped": True}))
                            api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                            return
                        raise AttributeError("stop_background_worker")
                    if path == "/v1/components/autonomous-controller/start":
                        if hasattr(runtime, "start_autonomous_controller"):
                            getattr(runtime, "start_autonomous_controller")()  # type: ignore[misc]
                            self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data={"autonomous_controller_started": True}))
                            api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                            return
                        raise AttributeError("start_autonomous_controller")
                    if path == "/v1/components/autonomous-controller/stop":
                        if hasattr(runtime, "stop_autonomous_controller"):
                            getattr(runtime, "stop_autonomous_controller")()  # type: ignore[misc]
                            self._respond_json(HTTPStatus.OK, api._response_envelope(ok=True, status="success", data={"autonomous_controller_stopped": True}))
                            api._emit_event("request_completed", endpoint=path, method=method, http_status=HTTPStatus.OK)
                            return
                        raise AttributeError("stop_autonomous_controller")
                except Exception as exc:
                    code, status = api._map_failure(exc)
                    self._respond_json(status, api._response_envelope(ok=False, status="error", error={"code": code, "message": _safe_message_for_code(code)}))
                    api._emit_event("request_completed", endpoint=path, method=method, http_status=status, failure_code=code)
                    return

            # Unknown route
            api._emit_event("request_rejected", endpoint=path, method=method, http_status=HTTPStatus.NOT_FOUND, failure_code="not_found")
            self._respond_json(HTTPStatus.NOT_FOUND, api._response_envelope(ok=False, status="error", error={"code": "not_found", "message": "Unknown route"}))
        except Exception:
            api._emit_event("api_operation_failed", endpoint=path, method=method, http_status=HTTPStatus.INTERNAL_SERVER_ERROR, failure_code="internal_error")
            self._respond_json(HTTPStatus.INTERNAL_SERVER_ERROR, api._response_envelope(ok=False, status="error", error={"code": "internal_error", "message": "An internal error occurred"}))

    # Helpers
    def _auth_error(self, http_status: int, failure_code: str) -> None:
        api = self.server.api  # type: ignore[attr-defined]
        if http_status == HTTPStatus.UNAUTHORIZED:
            msg = "Missing authentication"
        else:
            msg = "Invalid authentication"
        self._respond_json(http_status, api._response_envelope(ok=False, status="error", error={"code": failure_code, "message": msg}))

    def _read_json_object(self, api: "RuntimePrivateAPI") -> Tuple[Dict[str, Any], int]:
        # Validate Content-Length
        cl_header = self.headers.get("Content-Length")
        if cl_header is None:
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "Missing Content-Length header")
        try:
            content_length = int(cl_header)
        except ValueError:
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "Invalid Content-Length header")

        if content_length < 0:
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "Invalid Content-Length header")
        if content_length > api.config.request_body_limit_bytes:
            raise _ImmediateError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large", "Request body too large")

        # Enforce socket timeout per-request
        try:
            self.connection.settimeout(float(api.config.request_timeout_seconds))
        except Exception:
            pass

        # Read exactly content_length bytes (bounded)
        remaining = content_length
        chunks: List[bytes] = []
        rcvd = 0
        while remaining > 0:
            to_read = min(remaining, 65536)
            data = self.rfile.read(to_read)
            if not data:
                break
            chunks.append(data)
            rcvd += len(data)
            remaining -= len(data)
            if rcvd > api.config.request_body_limit_bytes:
                raise _ImmediateError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large", "Request body too large")
        if rcvd != content_length:
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "Incomplete request body")

        raw = b"".join(chunks)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request body must be valid UTF-8 JSON")

        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "Malformed JSON body")

        if not isinstance(obj, dict):
            raise _ImmediateError(HTTPStatus.BAD_REQUEST, "invalid_request", "JSON body must be an object")
        return obj, rcvd

    def _respond_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        # Deterministic JSON serialization
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        # Content-Length must be exact
        content_length = len(data)
        # Write headers and body
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if content_length:
            self.wfile.write(data)
        try:
            self.wfile.flush()
        except Exception:
            pass
        # Ensure connection is closed after response
        self.close_connection = True


class _ImmediateError(Exception):
    __slots__ = ("http_status", "code", "message")

    def __init__(self, http_status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message


_FAILURE_CODE_TO_HTTP: Dict[str, int] = {
    "invalid_request": HTTPStatus.BAD_REQUEST,
    "invalid_execution_outcome": HTTPStatus.BAD_REQUEST,
    "runtime_not_running": HTTPStatus.CONFLICT,
    "invalid_runtime_transition": HTTPStatus.CONFLICT,
    "duplicate_execution": HTTPStatus.CONFLICT,
    "invalid_status_transition": HTTPStatus.CONFLICT,
    "mission_not_found": HTTPStatus.NOT_FOUND,
    "unknown_project": HTTPStatus.NOT_FOUND,
    "cross_project_reference": HTTPStatus.FORBIDDEN,
    "budget_blocked": HTTPStatus.TOO_MANY_REQUESTS,
    "rate_limit_blocked": HTTPStatus.TOO_MANY_REQUESTS,
    "no_model_available": HTTPStatus.SERVICE_UNAVAILABLE,
    "planner_failed": HTTPStatus.SERVICE_UNAVAILABLE,
    "queue_resolution_failed": HTTPStatus.SERVICE_UNAVAILABLE,
    "queue_failed": HTTPStatus.SERVICE_UNAVAILABLE,
    "usage_recording_failed": HTTPStatus.SERVICE_UNAVAILABLE,
    "report_persistence_failed": HTTPStatus.SERVICE_UNAVAILABLE,
    "dependency_failed": HTTPStatus.SERVICE_UNAVAILABLE,
}


def _safe_message_for_code(code: str) -> str:
    # Generic human-safe messages without leaking details
    generic = {
        "invalid_request": "The request is invalid",
        "invalid_execution_outcome": "The execution outcome is invalid",
        "runtime_not_running": "The runtime is not running",
        "invalid_runtime_transition": "Invalid runtime transition",
        "duplicate_execution": "Duplicate execution",
        "invalid_status_transition": "Invalid status transition",
        "mission_not_found": "Mission not found",
        "unknown_project": "Unknown project",
        "cross_project_reference": "Operation not permitted across projects",
        "budget_blocked": "Budget limits prevent this operation",
        "rate_limit_blocked": "Rate limit exceeded",
        "no_model_available": "No model available",
        "planner_failed": "Planner is unavailable",
        "queue_resolution_failed": "A queue dependency failed",
        "queue_failed": "Queue processing failed",
        "usage_recording_failed": "Usage recording is unavailable",
        "report_persistence_failed": "Report persistence is unavailable",
        "dependency_failed": "A dependency is unavailable",
    }
    return generic.get(code, "An internal error occurred")


class RuntimePrivateAPI:
    def __init__(self, config: RuntimeAPIConfig, runtime: Optional[Any] = None) -> None:
        self.config = self._validate_config(config)
        self.runtime = runtime
        self._server: Optional[_RuntimePrivateHTTPServer] = None
        self._state_lock = threading.Lock()
        self._state: str = "created"
        self._bound_host: Optional[str] = None
        self._bound_port: Optional[int] = None
        self._events: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self._auth_token_cached: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._emit_event("api_created")

    # Lifecycle
    def start(self) -> None:
        with self._state_lock:
            if self._server is not None:
                # Idempotent
                return
            self._state = "starting"
            self._emit_event("api_starting")
            try:
                handler_cls = _RequestHandler
                # Bind immediately; constructor binds socket
                server = _RuntimePrivateHTTPServer((self.config.host, self.config.port), handler_cls, api=self)
                self._server = server
                # Store bound address
                addr = server.server_address
                # server_address may be (host, port) or (host, port, *rest)
                host = addr[0]
                port = addr[1]
                self._bound_host = str(host)
                self._bound_port = int(port)
                self._state = "started"
                self._emit_event("api_started")
            except Exception:
                # Ensure resources are cleaned up on failure
                try:
                    if self._server is not None:
                        self._server.server_close()
                except Exception:
                    pass
                self._server = None
                self._bound_host = None
                self._bound_port = None
                self._state = "failed"
                self._emit_event("api_start_failed")
                raise

    def serve_forever(self) -> None:
        # This should be called after start(); it blocks serving requests until shutdown
        srv = self._server
        if srv is None:
            raise RuntimeError("API server is not started")
        # Ensure the poll interval is short but bounded
        try:
            srv.serve_forever(poll_interval=0.5)
        finally:
            pass

    def stop(self) -> None:
        # Request server shutdown; do not hold lock while blocking
        srv = None
        with self._state_lock:
            srv = self._server
            if srv is None:
                return
            self._state = "stopping"
            self._emit_event("api_stopping")
        # Call shutdown from a different thread to avoid deadlocks
        def _shutdown_server(s: _RuntimePrivateHTTPServer) -> None:
            try:
                s.shutdown()
            except Exception:
                pass
        t = threading.Thread(target=_shutdown_server, args=(srv,), name="RuntimePrivateAPI-Shutdown", daemon=True)
        t.start()
        t.join(timeout=float(self.config.graceful_shutdown_timeout_seconds))
        with self._state_lock:
            self._state = "stopped"
            self._emit_event("api_stopped")

    def close(self) -> None:
        with self._state_lock:
            srv = self._server
            if srv is None:
                # Idempotent
                return
            try:
                srv.server_close()
            except Exception:
                pass
            finally:
                self._server = None
                self._bound_host = None
                self._bound_port = None
                self._thread = None

    # Status helpers
    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "state": self._state,
                "address": (self._bound_host, self._bound_port) if self._bound_host and self._bound_port else None,
            }

    def address(self) -> Optional[Tuple[str, int]]:
        with self._state_lock:
            if self._bound_host is None or self._bound_port is None:
                return None
            return (self._bound_host, self._bound_port)

    def latest_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            limit = 1
        if limit > 1000:
            limit = 1000
        return list(list(self._events)[-limit:])

    # Context manager support
    def __enter__(self) -> "RuntimePrivateAPI":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        try:
            self.stop()
        finally:
            self.close()

    # Internal utilities
    def _emit_event(self, event_type: str, **fields: Any) -> None:
        safe_event = {
            "event": event_type,
            "timestamp": _now_iso(),
        }
        for k in ("endpoint", "method", "http_status", "failure_code", "request_id"):
            if k in fields and fields[k] is not None:
                safe_event[k] = fields[k]
        # runtime state snapshot (safe)
        safe_event["runtime_state"] = None
        try:
            status_obj = self._safe_runtime_status()
            safe_event["runtime_state"] = status_obj.get("state")
        except Exception:
            pass
        self._events.append(safe_event)

    def _response_envelope(self, *, ok: bool, status: str, data: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None) -> Dict[str, Any]:
        envelope: Dict[str, Any] = {
            "ok": bool(ok),
            "status": status,
            "timestamp": _now_iso(),
        }
        if request_id:
            envelope["request_id"] = request_id
        if data is not None:
            envelope["data"] = data
        if error is not None:
            # Never include sensitive information
            clean_error = {}
            if "code" in error and isinstance(error["code"], str):
                clean_error["code"] = error["code"]
            if "message" in error and isinstance(error["message"], str):
                clean_error["message"] = error["message"]
            envelope["error"] = clean_error
        return envelope

    def _validate_config(self, config: RuntimeAPIConfig) -> RuntimeAPIConfig:
        # Host validation
        host = config.host.strip()
        if not host:
            raise ValueError("host must be non-empty")
        if host in ("0.0.0.0", "::"):
            raise ValueError("Wildcard public hosts are not allowed")
        # Port validation
        port = int(config.port)
        if port < 0 or port > 65535:
            raise ValueError("port must be between 0 and 65535")
        # Limits
        if config.request_body_limit_bytes <= 0 or config.response_body_limit_bytes <= 0:
            raise ValueError("body limits must be positive integers")
        # Timeouts
        if config.request_timeout_seconds <= 0 or config.graceful_shutdown_timeout_seconds <= 0:
            raise ValueError("timeouts must be positive integers")
        # Authentication config is allowed to be empty at construction per contract
        return config

    def _get_auth_token(self) -> Optional[str]:
        # Lazy token resolution
        if self._auth_token_cached is not None:
            return self._auth_token_cached
        ref = self.config.auth_token_reference
        resolver = self.config.auth_token_resolver
        token: Optional[str] = None
        if resolver is not None and isinstance(ref, str) and ref != "":
            try:
                token = resolver(ref)
            except Exception:
                token = None
        # Cache even empty to avoid repeated resolver calls; empty will be treated as unresolved
        self._auth_token_cached = token if token else None
        return self._auth_token_cached

    def _check_auth(self, headers: MutableMapping[str, str]) -> Tuple[bool, int, str]:
        # Returns (authorized, http_status, failure_code)
        auth_header = headers.get("Authorization")
        if not auth_header:
            return (False, HTTPStatus.UNAUTHORIZED, "missing_authentication")
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return (False, HTTPStatus.FORBIDDEN, "invalid_authentication")
        provided_token = parts[1]
        expected = self._get_auth_token()
        if not expected:
            # Unresolved configuration treated as invalid authentication when a header is provided
            return (False, HTTPStatus.FORBIDDEN, "invalid_authentication")
        try:
            match = hmac.compare_digest(provided_token, expected)
        except Exception:
            match = False
        if not match:
            return (False, HTTPStatus.FORBIDDEN, "invalid_authentication")
        return (True, HTTPStatus.OK, "")

    def _safe_runtime_status(self) -> Dict[str, Any]:
        # Use provided runtime_status function if available in repository; do not import at module import time
        runtime = self.runtime
        if runtime is None:
            return {"state": "unavailable", "application_ready": False}
        try:
            # Delayed import to avoid hard dependency at import time
            from importlib import import_module
            try:
                # Attempt common location; repository should provide a runtime_status function
                mod = import_module("agent.runtime")
            except Exception:
                # Fallback to alternative names if needed
                try:
                    mod = import_module("runtime")
                except Exception:
                    mod = None  # type: ignore[assignment]
            if mod is not None and hasattr(mod, "runtime_status"):
                return dict(getattr(mod, "runtime_status")(runtime))  # type: ignore[misc]
        except Exception:
            pass
        # Last-resort safe status without exposing internals
        try:
            # If runtime has a status() method, call it safely
            if hasattr(runtime, "status"):
                st = getattr(runtime, "status")()
                if isinstance(st, dict):
                    # Sanitize keys
                    safe = {k: v for k, v in st.items() if k in ("state", "application_ready")}
                    if safe:
                        return safe
        except Exception:
            pass
        return {"state": "unknown", "application_ready": False}

    def _map_failure(self, exc: Exception) -> Tuple[str, int]:
        # Try to extract a structured error code from known attributes
        code: Optional[str] = None
        for attr in ("code", "error_code", "reason"):
            if hasattr(exc, attr):
                v = getattr(exc, attr)
                if isinstance(v, str) and v:
                    code = v
                    break
        # Heuristics for common Python exceptions
        if code is None:
            if isinstance(exc, ValueError):
                code = "invalid_request"
            elif isinstance(exc, KeyError):
                code = "invalid_request"
            elif isinstance(exc, PermissionError):
                code = "cross_project_reference"
            elif isinstance(exc, TimeoutError):
                code = "dependency_failed"
            elif isinstance(exc, RuntimeError) and str(exc) == "runtime_unavailable":
                code = "dependency_failed"
        if code is None or not isinstance(code, str):
            # Unknown failure
            return ("internal_error", HTTPStatus.INTERNAL_SERVER_ERROR)
        http = _FAILURE_CODE_TO_HTTP.get(code, HTTPStatus.INTERNAL_SERVER_ERROR)
        return (code, http)


def build_runtime_private_api(config: Union[RuntimeAPIConfig, Mapping[str, Any]], runtime: Optional[Any] = None) -> RuntimePrivateAPI:
    # Accept dict-like config to simplify external construction
    if isinstance(config, Mapping):
        cfg = RuntimeAPIConfig.from_dict(config)
    elif isinstance(config, RuntimeAPIConfig):
        cfg = config
    else:
        raise TypeError("config must be a RuntimeAPIConfig or a mapping")
    # Do not eagerly resolve authentication token here; comply with contract
    return RuntimePrivateAPI(cfg, runtime=runtime)


# Utilities

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _env_token_resolver(env_var_name: str) -> Optional[str]:
    # Read environment variable safely; return None if not set or empty
    val = os.environ.get(env_var_name)
    if val is None or val == "":
        return None
    return val


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="runtime_private_api", add_help=True)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", type=str, default="")
    parser.add_argument("--repository-root", type=str, default="")
    parser.add_argument("--default-project-id", type=str, default="")
    parser.add_argument("--environment-name", type=str, default="")
    parser.add_argument("--auth-token-env", type=str, default="")
    parser.add_argument("--enable-lifecycle-endpoints", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    # Validate host
    host = (args.host or "").strip()
    if not host or host in ("0.0.0.0", "::"):
        _safe_stderr("Invalid host; refusing to bind to wildcard public interfaces\n")
        return 2
    # Validate port
    try:
        port = int(args.port)
    except Exception:
        _safe_stderr("Invalid port\n")
        return 2
    if port < 0 or port > 65535:
        _safe_stderr("Port must be between 0 and 65535\n")
        return 2

    # Build RuntimeService using repository-provided builders; imports are delayed and optional
    runtime = None
    try:
        # Attempt common module path for builders
        from importlib import import_module
        runtime_mod = None
        appcfg_cls = None
        rtcfg_cls = None
        build_runtime_fn = None
        try:
            runtime_mod = import_module("agent.runtime")
        except Exception:
            try:
                runtime_mod = import_module("runtime")
            except Exception:
                runtime_mod = None
        if runtime_mod is None:
            _safe_stderr("Runtime modules not found; cannot start runtime service\n")
            return 2
        # Fetch expected interfaces; if missing, fail fast and safe
        appcfg_cls = getattr(runtime_mod, "ApplicationConfig", None)
        rtcfg_cls = getattr(runtime_mod, "RuntimeConfig", None)
        build_runtime_fn = getattr(runtime_mod, "build_runtime", None)
        if appcfg_cls is None or rtcfg_cls is None or build_runtime_fn is None:
            _safe_stderr("Required runtime interfaces are unavailable\n")
            return 2

        # Construct configs with only safe/known fields
        app_cfg = appcfg_cls(  # type: ignore[call-arg]
            data_root=(args.data_root or None),
            repository_root=(args.repository_root or None),
            default_project_id=(args.default_project_id or None),
            environment_name=(args.environment_name or None),
        )
        rt_cfg = rtcfg_cls()  # type: ignore[call-arg]
        runtime = build_runtime_fn(app_cfg, rt_cfg)  # type: ignore[misc]
    except SystemExit:
        raise
    except Exception:
        _safe_stderr("Failed to construct runtime service\n")
        return 2

    # Start runtime service
    try:
        if hasattr(runtime, "start"):
            runtime.start()  # type: ignore[attr-defined]
    except Exception:
        _safe_stderr("Failed to start runtime service\n")
        return 3

    # Build API config with lazy token resolver
    auth_ref = str(args.auth_token_env or "")
    api_cfg = RuntimeAPIConfig(
        host=host,
        port=port,
        enable_lifecycle_endpoints=bool(args.enable_lifecycle_endpoints),
        auth_token_reference=auth_ref,
        auth_token_resolver=(_env_token_resolver if auth_ref else None),
    )

    # Build and start API
    try:
        api = build_runtime_private_api(api_cfg, runtime=runtime)
        api.start()
    except Exception:
        _safe_stderr("Failed to start private API\n")
        try:
            if hasattr(runtime, "stop"):
                runtime.stop()  # type: ignore[attr-defined]
        except Exception:
            pass
        return 4

    # Signal handling
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
        # Trigger API shutdown without deadlocking
        stop_event.set()
        try:
            api.stop()
        except Exception:
            pass

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception:
        # Some environments may not allow signal handling (e.g., Windows threads)
        pass

    # Serve until stopped by signal
    try:
        api.serve_forever()
    except KeyboardInterrupt:
        pass

    # Ensure API is stopped and closed
    try:
        api.stop()
    except Exception:
        pass
    try:
        api.close()
    except Exception:
        pass

    # Stop runtime
    try:
        if hasattr(runtime, "stop"):
            runtime.stop()  # type: ignore[attr-defined]
    except Exception:
        _safe_stderr("Failed to stop runtime service cleanly\n")
        return 5

    return 0


def _safe_stderr(msg: str) -> None:
    try:
        import sys
        sys.stderr.write(msg)
        sys.stderr.flush()
    except Exception:
        pass


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
