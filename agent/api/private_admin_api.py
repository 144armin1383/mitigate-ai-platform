from __future__ import annotations

import argparse
import datetime as _dt
import hmac
import http.client
import json
import os
import re
import signal
import socket
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Tuple
from urllib.parse import parse_qs, unquote, urlparse
from collections import deque

try:
    from repair.audit_store import SelfHealingAuditStore
except ModuleNotFoundError as exc:
    if exc.name != "repair":
        raise
    from agent.repair.audit_store import SelfHealingAuditStore

# =============================
# Exceptions and Interfaces
# =============================

class NotFoundError(Exception):
    """Raised when an item is not found."""


class InvalidStateError(Exception):
    """Raised when an invalid state transition is attempted."""


class DuplicateRequestError(Exception):
    """Raised when a duplicate request identifier is used."""


class PlannerValidationError(Exception):
    """Raised when planner validation fails for the input request."""


class PlannerFailureError(Exception):
    """Raised when the planner fails unexpectedly."""


class PlannerInterface(Protocol):
    def plan(self, request: Mapping[str, Any]) -> List[Mapping[str, Any]]:  # missions/specs
        ...


class MissionQueueInterface(Protocol):
    def enqueue_plan(self, request_id: str, missions: List[Mapping[str, Any]]) -> List[str]:
        """Atomically enqueue a list of mission specs; returns created mission IDs."""
        ...

    def list_missions(self) -> List[Mapping[str, Any]]:
        ...

    def get_mission(self, mission_id: str) -> Mapping[str, Any]:
        ...

    def cancel(self, mission_id: str) -> None:
        ...

    def resume(self, mission_id: str) -> None:
        ...

    def retry(self, mission_id: str) -> None:
        ...

    def counts_by_state(self) -> Mapping[str, int]:
        ...


# =============================
# Configuration and Utilities
# =============================

@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    queue_path: Optional[str] = None
    events_path: Optional[str] = None  # Path to worker events file (.jsonl)
    reports_path: Optional[str] = None  # Directory containing structured JSON reports
    heartbeat_path: Optional[str] = None  # Worker heartbeat file
    max_request_bytes: int = 1024 * 1024  # 1 MiB default
    rate_limit_per_minute: int = 60
    worker_heartbeat_ttl_secs: int = 120
    api_events_path: Optional[str] = None  # Optional path to append structured API events (jsonl)
    audit_path: Optional[str] = None  # Optional Self-Healing audit JSONL path


class AdminAuth:
    def __init__(self, expected_token: str) -> None:
        self._expected = expected_token

    @classmethod
    def from_env(cls) -> "AdminAuth":
        token = os.environ.get("MITIGATE_AI_ADMIN_TOKEN", "")
        if not token:
            raise SystemExit("MITIGATE_AI_ADMIN_TOKEN is required for startup")
        return cls(token)

    def check(self, auth_header: Optional[str]) -> bool:
        # Constant-time comparison attempt regardless of header presence
        provided: str = ""
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                provided = parts[1]
            else:
                provided = ""
        # Use hmac.compare_digest for constant-time comparison
        try:
            return hmac.compare_digest(provided, self._expected)
        except Exception:
            # In unexpected cases, deny access
            return False


class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self._limit = max(1, int(limit_per_minute))
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str, now: Optional[float] = None) -> bool:
        ts = time.time() if now is None else now
        window_start = ts - 60.0
        with self._lock:
            dq = self._buckets.get(client_id)
            if dq is None:
                dq = deque()
                self._buckets[client_id] = dq
            # Purge old timestamps
            while dq and dq[0] < window_start:
                dq.popleft()
            if len(dq) >= self._limit:
                return False
            dq.append(ts)
            return True


class RequestIdGen:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = 0

    def next(self) -> str:
        with self._lock:
            self._counter += 1
            return f"req-{self._counter:06d}"


_SECRET_KEYS = {"token", "secret", "password", "passwd", "key", "api_key", "access_key"}


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > 0:
            return "[REDACTED]"
    return "[REDACTED]"


def _redact_dict(obj: Mapping[str, Any]) -> Dict[str, Any]:
    redacted: Dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(k, str) and any(s in k.lower() for s in _SECRET_KEYS):
            redacted[k] = _redact_value(v)
        else:
            redacted[k] = safe_json(v)
    return redacted


def safe_json(obj: Any) -> Any:
    # Ensure JSON serializable and safe basic types only
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Mapping):
        return _redact_dict(obj)
    if isinstance(obj, (list, tuple)):
        return [safe_json(x) for x in obj]
    # Fallback to string representation without sensitive paths
    s = str(obj)
    if "\n" in s:
        s = s.replace("\n", " ")
    return s


_MISSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_mission_id(mission_id: str) -> bool:
    return bool(_MISSION_ID_RE.fullmatch(mission_id))


# =============================
# HTTP Handler
# =============================

class PrivateAdminAPIHandler(BaseHTTPRequestHandler):
    server_version = "PrivateAdminAPI/1.0"

    # Class-level injected dependencies
    config: ServerConfig
    auth: AdminAuth
    rate_limiter: RateLimiter
    planner: PlannerInterface
    queue: MissionQueueInterface
    req_ids: RequestIdGen
    server_started_at: float

    # Paths
    events_path: Optional[str]
    reports_path: Optional[str]
    heartbeat_path: Optional[str]
    audit_path: Optional[str]

    # Disable default logging to stderr
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 (shadowing built-in)
        return

    # -------- Utilities ---------

    def _request_id(self) -> str:
        return self.req_ids.next()

    def _client_id(self) -> str:
        # Use remote IP as client ID
        try:
            return self.client_address[0]
        except Exception:
            return "unknown"

    def _parse_json(self, *, max_bytes: int, require_content_type: bool = True) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        # Returns (json_obj_or_none, error_code)
        ctype = self.headers.get("Content-Type", "")
        if require_content_type:
            if not ctype:
                return None, "missing_content_type"
            main_type = ctype.split(";")[0].strip().lower()
            if main_type != "application/json":
                return None, "unsupported_content_type"
        # Enforce size
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return None, "length_required"
        try:
            content_len = int(raw_len)
        except ValueError:
            return None, "invalid_content_length"
        if content_len < 0:
            return None, "invalid_content_length"
        if content_len > max_bytes:
            return None, "body_too_large"
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return None, "malformed_json"
        if not isinstance(data, dict):
            return None, "malformed_json"
        return data, None

    def _write_json(self, status: int, obj: Mapping[str, Any]) -> None:
        payload = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _write_error(self, status: int, request_id: str, code: str, message: str, extra: Optional[Mapping[str, Any]] = None) -> None:
        base = {"request_id": request_id, "error": {"code": code, "message": message}}
        if extra:
            base["error"].update({k: safe_json(v) for k, v in extra.items()})
        self._write_json(status, base)

    def _require_auth_and_rate_limit(self, request_id: str) -> bool:
        # Rate limit first to avoid engaging token checks too early
        client_id = self._client_id()
        if not self.rate_limiter.allow(client_id):
            self._write_error(HTTPStatus.TOO_MANY_REQUESTS, request_id, "rate_limited", "Too many requests")
            return False
        # Health endpoint bypasses auth (handled by caller)
        auth_header = self.headers.get("Authorization")
        if not self.auth.check(auth_header):
            # Avoid disclosing whether token missing or wrong
            self._write_error(HTTPStatus.UNAUTHORIZED, request_id, "unauthorized", "Authentication required")
            return False
        return True

    # -------- Handlers ---------

    def do_GET(self) -> None:  # noqa: N802
        request_id = self._request_id()
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/health":
            self._write_json(HTTPStatus.OK, {"request_id": request_id, "status": "ok"})
            return
        if not self._require_auth_and_rate_limit(request_id):
            return
        try:
            if route == "/v1/status":
                self._handle_status(request_id)
                return
            if route == "/v1/missions":
                self._handle_list_missions(request_id)
                return
            if route.startswith("/v1/missions/"):
                parts = route.split("/")
                if len(parts) == 4 and parts[3]:
                    # Action endpoints are POST; GET mission detail path should have 3 segments after split: ['', 'v1', 'missions', '{id}']
                    pass
                if len(parts) == 4 and parts[3]:
                    mission_id = parts[3]
                    self._handle_get_mission(request_id, mission_id)
                    return
            if route == "/v1/self-healing/status":
                self._handle_self_healing_status(request_id)
                return
            if route == "/v1/self-healing/audits":
                self._handle_self_healing_audits(
                    request_id,
                    parsed.query,
                )
                return
            if route.startswith("/v1/self-healing/audits/"):
                repair_id = route[
                    len("/v1/self-healing/audits/"):
                ]
                self._handle_self_healing_audit_detail(
                    request_id,
                    repair_id,
                )
                return
            if route == "/v1/events":
                self._handle_events(request_id, parsed.query)
                return
            if route == "/v1/reports/latest":
                self._handle_reports_latest(request_id)
                return
            self._write_error(HTTPStatus.NOT_FOUND, request_id, "not_found", "Unknown endpoint")
        except Exception:
            # Safe generic error
            self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, request_id, "internal_error", "An unexpected error occurred")

    def do_POST(self) -> None:  # noqa: N802
        request_id = self._request_id()
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/v1/requests":
            if not self._require_auth_and_rate_limit(request_id):
                return
            self._handle_post_request(request_id)
            return
        if not self._require_auth_and_rate_limit(request_id):
            return
        try:
            if route.startswith("/v1/missions/"):
                parts = route.split("/")
                # ['', 'v1', 'missions', '{id}', 'action']
                if len(parts) == 5:
                    mission_id = parts[3]
                    action = parts[4]
                    if not _validate_mission_id(mission_id):
                        self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_mission_id", "Invalid mission identifier")
                        return
                    if action == "cancel":
                        self._handle_mission_action(request_id, mission_id, "cancel")
                        return
                    if action == "resume":
                        self._handle_mission_action(request_id, mission_id, "resume")
                        return
                    if action == "retry":
                        self._handle_mission_action(request_id, mission_id, "retry")
                        return
            self._write_error(HTTPStatus.NOT_FOUND, request_id, "not_found", "Unknown endpoint")
        except Exception:
            self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, request_id, "internal_error", "An unexpected error occurred")

    # -------- Route handlers ---------

    def _handle_status(self, request_id: str) -> None:
        counts = self.queue.counts_by_state()
        now = time.time()
        worker_active = False
        last_heartbeat: Optional[str] = None
        if self.heartbeat_path and os.path.exists(self.heartbeat_path):
            try:
                mtime = os.path.getmtime(self.heartbeat_path)
                worker_active = (now - mtime) <= float(self.config.worker_heartbeat_ttl_secs)
                last_heartbeat = _dt.datetime.fromtimestamp(
                    mtime,
                    tz=_dt.timezone.utc,
                ).isoformat()
            except Exception:
                worker_active = False
                last_heartbeat = None
        out = {
            "request_id": request_id,
            "queue_counts": {str(k): int(v) for k, v in sorted(counts.items(), key=lambda x: str(x[0]))},
            "worker": {
                "active": bool(worker_active),
                "last_heartbeat": last_heartbeat,
            },
            "uptime_seconds": int(now - self.server_started_at),
        }
        self._write_json(HTTPStatus.OK, out)

    def _handle_list_missions(self, request_id: str) -> None:
        missions = self.queue.list_missions()
        safe_missions = [safe_json(m) for m in missions]
        self._write_json(HTTPStatus.OK, {"request_id": request_id, "missions": safe_missions})

    def _handle_get_mission(self, request_id: str, mission_id: str) -> None:
        if not _validate_mission_id(mission_id):
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_mission_id", "Invalid mission identifier")
            return
        try:
            m = self.queue.get_mission(mission_id)
        except NotFoundError:
            self._write_error(HTTPStatus.NOT_FOUND, request_id, "not_found", "Mission not found")
            return
        self._write_json(HTTPStatus.OK, {"request_id": request_id, "mission": safe_json(m)})

    def _handle_mission_action(self, request_id: str, mission_id: str, action: str) -> None:
        try:
            if action == "cancel":
                self.queue.cancel(mission_id)
            elif action == "resume":
                self.queue.resume(mission_id)
            elif action == "retry":
                self.queue.retry(mission_id)
            else:
                self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_action", "Unsupported action")
                return
        except NotFoundError:
            self._write_error(HTTPStatus.NOT_FOUND, request_id, "not_found", "Mission not found")
            return
        except InvalidStateError:
            self._write_error(HTTPStatus.CONFLICT, request_id, "invalid_state", "Invalid state transition")
            return
        self._write_json(HTTPStatus.OK, {"request_id": request_id, "status": "ok"})

    def _handle_events(self, request_id: str, query: str) -> None:
        params = parse_qs(query or "")
        limit = 100
        if "limit" in params:
            try:
                limit_val = int(params["limit"][0])
                if limit_val <= 0 or limit_val > 1000:
                    raise ValueError
                limit = limit_val
            except Exception:
                self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_limit", "Invalid limit parameter")
                return
        events_out: List[Any] = []
        if self.events_path and os.path.exists(self.events_path):
            try:
                dq: Deque[str] = deque(maxlen=limit)
                with open(self.events_path, "r", encoding="utf-8") as f:
                    for line in f:
                        dq.append(line)
                for line in dq:
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            events_out.append(safe_json(obj))
                    except Exception:
                        # skip malformed
                        continue
            except Exception:
                # If reading fails, return empty list without exposing internals
                events_out = []
        self._write_json(HTTPStatus.OK, {"request_id": request_id, "events": events_out})

    def _handle_reports_latest(self, request_id: str) -> None:
        content: Optional[Any] = None
        if self.reports_path and os.path.isdir(self.reports_path):
            try:
                candidates = [
                    os.path.join(self.reports_path, p)
                    for p in os.listdir(self.reports_path)
                    if p.endswith(".json")
                ]
                if candidates:
                    latest = max(candidates, key=lambda p: os.path.getmtime(p))
                    with open(latest, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, Mapping):
                            content = safe_json(data)
                        else:
                            content = safe_json(data)
            except Exception:
                content = None
        if content is None:
            self._write_error(HTTPStatus.NOT_FOUND, request_id, "not_found", "No report available")
            return
        self._write_json(HTTPStatus.OK, {"request_id": request_id, "report": content})

    def _self_healing_audit_store(self) -> SelfHealingAuditStore:
        if self.audit_path:
            return SelfHealingAuditStore(self.audit_path)
        return SelfHealingAuditStore()

    def _handle_self_healing_audits(
        self,
        request_id: str,
        query: str,
    ) -> None:
        params = parse_qs(
            query or "",
            keep_blank_values=True,
        )

        allowed = {
            "mission_name",
            "repair_id",
            "final_state",
            "started_at_from",
            "started_at_to",
            "min_attempts",
            "max_attempts",
            "limit",
            "order",
        }

        unknown = sorted(
            key for key in params
            if key not in allowed
        )

        if unknown:
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                request_id,
                "invalid_query",
                "Unknown query parameter",
                {"fields": unknown},
            )
            return

        def one(name: str) -> Optional[str]:
            values = params.get(name)
            if not values:
                return None
            return values[0]

        try:
            limit_raw = one("limit")
            limit = (
                100
                if limit_raw is None
                else int(limit_raw)
            )

            if limit <= 0 or limit > 1000:
                raise ValueError

            min_raw = one("min_attempts")
            max_raw = one("max_attempts")

            min_attempts = (
                None
                if min_raw is None
                else int(min_raw)
            )
            max_attempts = (
                None
                if max_raw is None
                else int(max_raw)
            )

            if (
                min_attempts is not None
                and min_attempts < 0
            ):
                raise ValueError

            if (
                max_attempts is not None
                and max_attempts < 0
            ):
                raise ValueError

            if (
                min_attempts is not None
                and max_attempts is not None
                and min_attempts > max_attempts
            ):
                raise ValueError

            order = one("order") or "newest"

            if order not in {"newest", "oldest"}:
                raise ValueError

            records = self._self_healing_audit_store().query(
                mission_name=one("mission_name"),
                repair_id=one("repair_id"),
                final_state=one("final_state"),
                started_at_from=one("started_at_from"),
                started_at_to=one("started_at_to"),
                min_attempts=min_attempts,
                max_attempts=max_attempts,
                limit=limit,
                newest_first=(order == "newest"),
            )

        except (TypeError, ValueError):
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                request_id,
                "invalid_query",
                "Invalid audit query",
            )
            return

        audits = [
            safe_json(record.to_dict())
            for record in records
        ]

        self._write_json(
            HTTPStatus.OK,
            {
                "request_id": request_id,
                "count": len(audits),
                "audits": audits,
            },
        )

    def _handle_self_healing_audit_detail(
        self,
        request_id: str,
        raw_repair_id: str,
    ) -> None:
        repair_id = unquote(raw_repair_id).strip()

        if (
            not repair_id
            or len(repair_id) > 256
            or "/" in repair_id
            or any(ord(ch) < 32 for ch in repair_id)
        ):
            self._write_error(
                HTTPStatus.BAD_REQUEST,
                request_id,
                "invalid_repair_id",
                "Invalid repair identifier",
            )
            return

        records = self._self_healing_audit_store().query(
            repair_id=repair_id,
            limit=1,
            newest_first=True,
        )

        if not records:
            self._write_error(
                HTTPStatus.NOT_FOUND,
                request_id,
                "not_found",
                "Self-Healing audit not found",
            )
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "request_id": request_id,
                "audit": safe_json(
                    records[0].to_dict()
                ),
            },
        )

    def _handle_self_healing_status(
        self,
        request_id: str,
    ) -> None:
        records = self._self_healing_audit_store().query(
            newest_first=True,
        )

        counts: Dict[str, int] = {}

        for record in records:
            state = str(record.final_state)
            counts[state] = counts.get(state, 0) + 1

        latest = (
            safe_json(records[0].to_dict())
            if records
            else None
        )

        self._write_json(
            HTTPStatus.OK,
            {
                "request_id": request_id,
                "self_healing": {
                    "total_audits": len(records),
                    "by_final_state": {
                        key: counts[key]
                        for key in sorted(counts)
                    },
                    "latest_audit": latest,
                },
            },
        )

    def _handle_post_request(self, request_id: str) -> None:
        body, err = self._parse_json(max_bytes=self.config.max_request_bytes, require_content_type=True)
        if err is not None:
            if err == "unsupported_content_type":
                self._write_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, request_id, "unsupported_media_type", "Only application/json is supported")
                return
            if err == "body_too_large":
                self._write_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, request_id, "payload_too_large", "Request body too large")
                return
            if err == "length_required":
                self._write_error(HTTPStatus.LENGTH_REQUIRED, request_id, "length_required", "Content-Length required")
                return
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, err, "Invalid JSON request")
            return
        assert body is not None
        allowed_fields = {"request_id", "title", "description", "priority", "metadata"}
        unknown = [k for k in body.keys() if k not in allowed_fields]
        if unknown:
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "unknown_fields", "Unknown fields in request", {"fields": sorted(unknown)})
            return
        req_id = body.get("request_id")
        title = body.get("title")
        description = body.get("description")
        priority = body.get("priority", "normal")
        metadata = body.get("metadata", {})
        if not isinstance(req_id, str) or not req_id or len(req_id) > 128:
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_request_id", "Invalid request identifier")
            return
        if not isinstance(title, str) or not title.strip():
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_title", "Title is required")
            return
        if not isinstance(description, str) or not description.strip():
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_description", "Description is required")
            return
        if not isinstance(priority, str) or priority not in {"low", "normal", "high"}:
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_priority", "Priority must be one of: low, normal, high")
            return
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, Mapping):
            self._write_error(HTTPStatus.BAD_REQUEST, request_id, "invalid_metadata", "Metadata must be an object")
            return
        # Call planner
        try:
            plan = self.planner.plan({
                "request_id": req_id,
                "title": title,
                "description": description,
                "priority": priority,
                "metadata": dict(metadata),
            })
        except PlannerValidationError as e:
            self._write_error(HTTPStatus.UNPROCESSABLE_ENTITY, request_id, "planner_validation_failed", "Planner could not validate the request")
            return
        except PlannerFailureError:
            self._write_error(HTTPStatus.BAD_GATEWAY, request_id, "planner_failed", "Planner failed to generate a plan")
            return
        except Exception:
            self._write_error(HTTPStatus.BAD_GATEWAY, request_id, "planner_failed", "Planner failed to generate a plan")
            return
        # Enqueue atomically
        try:
            mission_ids = self.queue.enqueue_plan(req_id, [dict(m) for m in plan])
        except DuplicateRequestError:
            self._write_error(HTTPStatus.CONFLICT, request_id, "duplicate_request", "Duplicate request identifier")
            return
        except Exception:
            self._write_error(HTTPStatus.SERVICE_UNAVAILABLE, request_id, "enqueue_failed", "Failed to enqueue plan")
            return
        self._write_json(HTTPStatus.ACCEPTED, {"request_id": request_id, "submitted_request_id": req_id, "mission_ids": list(mission_ids)})


# =============================
# Server factory and CLI
# =============================

def build_handler(config: ServerConfig, auth: AdminAuth, planner: PlannerInterface, queue: MissionQueueInterface, rate_limiter: RateLimiter, req_ids: RequestIdGen) -> type[PrivateAdminAPIHandler]:
    # Create a new handler subclass bound to provided dependencies
    class _H(PrivateAdminAPIHandler):  # type: ignore[misc]
        pass
    _H.config = config
    _H.auth = auth
    _H.rate_limiter = rate_limiter
    _H.planner = planner
    _H.queue = queue
    _H.req_ids = req_ids
    _H.server_started_at = time.time()
    _H.events_path = config.events_path
    _H.reports_path = config.reports_path
    _H.heartbeat_path = config.heartbeat_path
    _H.audit_path = config.audit_path
    return _H


def create_server(config: ServerConfig, *, planner: Optional[PlannerInterface] = None, queue: Optional[MissionQueueInterface] = None, auth: Optional[AdminAuth] = None) -> ThreadingHTTPServer:
    # Ensure admin token at startup
    if auth is None:
        auth = AdminAuth.from_env()
    # Lazy default imports if not injected (kept optional and not required for tests)
    if planner is None:
        # Placeholder to avoid import-time hard dependency; raise clear error at runtime if used without DI
        class _NoPlanner(PlannerInterface):  # type: ignore[misc]
            def plan(self, request: Mapping[str, Any]) -> List[Mapping[str, Any]]:
                raise PlannerFailureError("Planner not provided")
        planner = _NoPlanner()
    if queue is None:
        class _NoQueue(MissionQueueInterface):  # type: ignore[misc]
            def enqueue_plan(self, request_id: str, missions: List[Mapping[str, Any]]) -> List[str]:
                raise RuntimeError("Queue not provided")
            def list_missions(self) -> List[Mapping[str, Any]]:
                return []
            def get_mission(self, mission_id: str) -> Mapping[str, Any]:
                raise NotFoundError("not found")
            def cancel(self, mission_id: str) -> None:
                raise NotFoundError("not found")
            def resume(self, mission_id: str) -> None:
                raise NotFoundError("not found")
            def retry(self, mission_id: str) -> None:
                raise NotFoundError("not found")
            def counts_by_state(self) -> Mapping[str, int]:
                return {}
        queue = _NoQueue()
    rl = RateLimiter(config.rate_limit_per_minute)
    rid = RequestIdGen()
    handler_cls = build_handler(config, auth, planner, queue, rl, rid)
    # Bind to specific host
    server_address = (config.host, int(config.port))
    httpd = ThreadingHTTPServer(server_address, handler_cls)
    # Set reasonable timeout on socket to aid shutdown
    httpd.timeout = 1.0
    return httpd


def _install_signal_handlers(httpd: ThreadingHTTPServer) -> None:
    def _graceful(signum: int, frame: Any) -> None:  # noqa: ARG001
        # Initiate shutdown without raising exception
        try:
            httpd.shutdown()
        except Exception:
            pass
    try:
        signal.signal(signal.SIGINT, _graceful)
        signal.signal(signal.SIGTERM, _graceful)
    except ValueError:
        # Signals can only be set in main thread; ignore if not main thread
        pass


def run_server(config: ServerConfig, *, planner: Optional[PlannerInterface] = None, queue: Optional[MissionQueueInterface] = None, auth: Optional[AdminAuth] = None) -> None:
    httpd = create_server(config, planner=planner, queue=queue, auth=auth)
    _install_signal_handlers(httpd)
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Private Admin API")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8765, help="Port to bind (default 8765)")
    p.add_argument("--queue-path", default=None, help="Path to queue persistence (optional)")
    p.add_argument("--events-path", default=None, help="Path to worker events file (jsonl)")
    p.add_argument("--reports-path", default=None, help="Path to reports directory")
    p.add_argument("--heartbeat-path", default=None, help="Path to worker heartbeat file")
    p.add_argument("--audit-path", default=None, help="Path to Self-Healing audit JSONL file")
    p.add_argument("--request-size", type=int, default=1024 * 1024, help="Maximum request body size in bytes (default 1048576)")
    p.add_argument("--rate-limit", type=int, default=60, help="Requests per minute per client (default 60)")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cfg = ServerConfig(
        host=args.host,
        port=int(args.port),
        queue_path=args.queue_path,
        events_path=args.events_path,
        reports_path=args.reports_path,
        heartbeat_path=args.heartbeat_path,
        audit_path=args.audit_path,
        max_request_bytes=int(args.request_size),
        rate_limit_per_minute=int(args.rate_limit),
    )
    run_server(cfg)


if __name__ == "__main__":
    main()
