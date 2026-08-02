from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, TypedDict


# Typed structures and protocols


class EventSink(Protocol):
    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:  # pragma: no cover - interface
        ...

    def latest(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        ...


class Clock(Protocol):
    def now(self) -> float:  # pragma: no cover - interface
        ...


class ProjectRegistry(Protocol):
    def resolve_project(self, project_id: str) -> Optional[Dict[str, Any]]:  # pragma: no cover - interface
        ...

    def conversation_belongs_to_project(self, conversation_id: str, project_id: str) -> bool:  # pragma: no cover - interface
        ...

    def upload_belongs_to_project(self, upload_id: str, project_id: str) -> bool:  # pragma: no cover - interface
        ...


@dataclass(frozen=True)
class ModelInfo:
    project_id: str
    provider_id: str
    model_id: str
    supports_vision: bool
    supports_tools: bool
    enabled: bool
    available: bool
    deprecated: bool


class ProviderModelRegistry(Protocol):
    def is_task_supported(self, project_id: str, task_type: str) -> bool:  # pragma: no cover - interface
        ...

    def requires_tools(self, task_type: str) -> bool:  # pragma: no cover - interface
        ...

    def explicit_model_allowed(
        self, project_id: str, task_type: str, provider_id: str, model_id: str
    ) -> Optional[ModelInfo]:  # pragma: no cover - interface
        ...

    def select_default_model(
        self,
        project_id: str,
        task_type: str,
        requires_vision: bool,
        requires_tools: bool,
        requested_provider_id: Optional[str] = None,
    ) -> Optional[ModelInfo]:  # pragma: no cover - interface
        ...


class ProviderBudgetEvaluator(Protocol):
    def preflight(
        self,
        *,
        project_id: str,
        provider_id: str,
        model_id: str,
        task_type: str,
        created_at: Any,
        request_id: str,
    ) -> Dict[str, Any]:  # returns {status: 'allow'|'warn'|'block', message?: str}
        ...


class ProviderRateLimiter(Protocol):
    def check_and_register(
        self,
        *,
        project_id: str,
        provider_id: str,
        model_id: str,
        task_type: str,
        request_id: str,
        created_at: Any,
    ) -> Dict[str, Any]:  # returns {allowed: bool, reason?: str}
        ...


class ValidationResult(TypedDict, total=False):
    valid: bool
    error_code: str
    error_message: str


class ProcessResult(TypedDict, total=False):
    accepted: bool
    request_id: str
    project_id: Optional[str]
    conversation_id: Optional[str]
    provider_id: Optional[str]
    model_id: Optional[str]
    task_type: Optional[str]
    warning: Optional[str]
    blocked_reason: Optional[str]
    created_at: Any
    project_context: Dict[str, Any]


_ALLOWED_FIELDS = {
    "request_id",
    "project_id",
    "conversation_id",
    "user_message",
    "upload_ids",
    "requested_task_type",
    "requested_provider_id",
    "requested_model_id",
    "created_at",
    "metadata",
}

_REQUIRED_FIELDS = {
    "request_id",
    "project_id",
    "conversation_id",
    "user_message",
    "requested_task_type",
    "created_at",
}

_IDENTIFIER_FIELDS = [
    "request_id",
    "project_id",
    "conversation_id",
    "requested_task_type",
    "requested_provider_id",
    "requested_model_id",
]


def _has_control_chars(value: str) -> bool:
    for ch in value:
        code = ord(ch)
        if code < 32 or code == 127:
            return True
    return False


def _redact_message_info(message: str) -> Dict[str, Any]:
    # Never include full user message in logs/events
    return {"message_length": len(message)}


class RequestGateSelector:
    def __init__(
        self,
        *,
        project_registry: ProjectRegistry,
        provider_registry: ProviderModelRegistry,
        budget_evaluator: ProviderBudgetEvaluator,
        rate_limiter: ProviderRateLimiter,
        clock: Clock,
        event_sink: EventSink,
    ) -> None:
        self._project_registry = project_registry
        self._provider_registry = provider_registry
        self._budget_evaluator = budget_evaluator
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._event_sink = event_sink
        self._seen_request_ids: set[str] = set()
        self._accepted_count = 0
        self._blocked_count = 0
        self._last_error_code: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        return {
            "accepted_count": self._accepted_count,
            "blocked_count": self._blocked_count,
            "last_error_code": self._last_error_code,
            "last_updated": self._clock.now(),
        }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._event_sink.latest(limit, project_id)

    def validate_request(self, request: Dict[str, Any]) -> ValidationResult:
        try:
            if not isinstance(request, dict):
                return {"valid": False, "error_code": "invalid_request", "error_message": "Request must be a dict"}

            unknown = set(request.keys()) - _ALLOWED_FIELDS
            if unknown:
                return {
                    "valid": False,
                    "error_code": "invalid_request",
                    "error_message": f"Unknown fields: {sorted(list(unknown))}",
                }

            missing = [f for f in _REQUIRED_FIELDS if f not in request]
            if missing:
                return {
                    "valid": False,
                    "error_code": "invalid_request",
                    "error_message": f"Missing required fields: {sorted(missing)}",
                }

            # Basic type checks
            if not isinstance(request.get("user_message"), str) or not request["user_message"].strip():
                return {"valid": False, "error_code": "invalid_request", "error_message": "user_message must be a non-empty string"}

            if not isinstance(request.get("request_id"), str):
                return {"valid": False, "error_code": "invalid_request", "error_message": "request_id must be a string"}

            if not isinstance(request.get("project_id"), str):
                return {"valid": False, "error_code": "invalid_request", "error_message": "project_id must be a string"}

            if not isinstance(request.get("conversation_id"), str):
                return {"valid": False, "error_code": "invalid_request", "error_message": "conversation_id must be a string"}

            if not isinstance(request.get("requested_task_type"), str):
                return {"valid": False, "error_code": "invalid_request", "error_message": "requested_task_type must be a string"}

            if "upload_ids" in request:
                if not isinstance(request["upload_ids"], list) or not all(isinstance(x, str) for x in request["upload_ids"]):
                    return {"valid": False, "error_code": "invalid_request", "error_message": "upload_ids must be a list of strings"}
            if "requested_provider_id" in request and request["requested_provider_id"] is not None and not isinstance(request["requested_provider_id"], str):
                return {"valid": False, "error_code": "invalid_request", "error_message": "requested_provider_id must be a string when provided"}
            if "requested_model_id" in request and request["requested_model_id"] is not None and not isinstance(request["requested_model_id"], str):
                return {"valid": False, "error_code": "invalid_request", "error_message": "requested_model_id must be a string when provided"}
            if "metadata" in request and request["metadata"] is not None and not isinstance(request["metadata"], dict):
                return {"valid": False, "error_code": "invalid_request", "error_message": "metadata must be a dict when provided"}

            # Reject control characters in identifiers
            for field in _IDENTIFIER_FIELDS:
                if field in request and request[field] is not None:
                    value = request[field]
                    if not isinstance(value, str):
                        return {"valid": False, "error_code": "invalid_request", "error_message": f"{field} must be a string"}
                    if _has_control_chars(value):
                        return {"valid": False, "error_code": "invalid_request", "error_message": f"{field} contains control characters"}

            # upload_ids values should not contain control chars
            for uid in request.get("upload_ids", []) or []:
                if _has_control_chars(uid):
                    return {"valid": False, "error_code": "invalid_request", "error_message": "upload_ids contain control characters"}

            # request_id uniqueness within this gate instance
            req_id = request["request_id"]
            if req_id in self._seen_request_ids:
                return {"valid": False, "error_code": "invalid_request", "error_message": "duplicate request_id"}

            # Reserve the ID to ensure uniqueness going forward
            self._seen_request_ids.add(req_id)

            return {"valid": True}
        except Exception:
            # Never leak internal details
            return {"valid": False, "error_code": "dependency_failed", "error_message": "Unexpected error during validation"}

    def process_request(self, request: Dict[str, Any]) -> ProcessResult:
        # Emit request_received as early as possible with redacted info
        try:
            self._event_sink.emit(
                "request_received",
                {
                    "request_id": str(request.get("request_id", "")),
                    "project_id": str(request.get("project_id", "")),
                    "conversation_id": str(request.get("conversation_id", "")),
                    "has_uploads": bool(request.get("upload_ids")),
                    "requested_task_type": str(request.get("requested_task_type", "")),
                    "requested_provider_id": request.get("requested_provider_id"),
                    "requested_model_id": request.get("requested_model_id"),
                    "created_at": request.get("created_at"),
                    **_redact_message_info(str(request.get("user_message", ""))),
                },
            )
        except Exception:
            # Event sink failures are isolated and should not crash processing
            pass

        v = self.validate_request(request)
        if not v.get("valid", False):
            self._blocked_count += 1
            self._last_error_code = str(v.get("error_code", "invalid_request"))
            payload = {
                "accepted": False,
                "request_id": str(request.get("request_id", "")),
                "project_id": None,
                "conversation_id": None,
                "provider_id": None,
                "model_id": None,
                "task_type": None,
                "warning": None,
                "blocked_reason": self._last_error_code,
                "created_at": request.get("created_at"),
                "project_context": {},
            }
            try:
                self._event_sink.emit(
                    "request_rejected",
                    {
                        "request_id": payload["request_id"],
                        "project_id": None,
                        "reason": self._last_error_code,
                    },
                )
            except Exception:
                pass
            return payload

        # At this point, schema validation passed
        project_id = request["project_id"]
        req_id = request["request_id"]
        conv_id = request["conversation_id"]
        user_message = request["user_message"]
        task_type = request["requested_task_type"]
        upload_ids: List[str] = request.get("upload_ids", []) or []
        requested_provider_id: Optional[str] = request.get("requested_provider_id")
        requested_model_id: Optional[str] = request.get("requested_model_id")
        created_at = request.get("created_at")

        # Resolve project context
        try:
            project_ctx = self._project_registry.resolve_project(project_id)
        except Exception:
            project_ctx = None
        if not project_ctx:
            self._blocked_count += 1
            self._last_error_code = "unknown_project"
            try:
                self._event_sink.emit(
                    "request_rejected",
                    {"request_id": req_id, "project_id": project_id, "reason": "unknown_project"},
                )
            except Exception:
                pass
            return self._blocked_payload(req_id, created_at, blocked_reason="unknown_project")

        # Validate conversation ownership
        try:
            if not self._project_registry.conversation_belongs_to_project(conv_id, project_id):
                self._blocked_count += 1
                self._last_error_code = "cross_project_reference"
                try:
                    self._event_sink.emit(
                        "request_rejected",
                        {
                            "request_id": req_id,
                            "project_id": project_id,
                            "reason": "cross_project_reference",
                            "entity": "conversation",
                        },
                    )
                except Exception:
                    pass
                return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="cross_project_reference")
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="dependency_failed")

        # Validate upload ownership
        try:
            for uid in upload_ids:
                if not self._project_registry.upload_belongs_to_project(uid, project_id):
                    self._blocked_count += 1
                    self._last_error_code = "cross_project_reference"
                    try:
                        self._event_sink.emit(
                            "request_rejected",
                            {
                                "request_id": req_id,
                                "project_id": project_id,
                                "reason": "cross_project_reference",
                                "entity": "upload",
                            },
                        )
                    except Exception:
                        pass
                    return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="cross_project_reference")
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="dependency_failed")

        # Resolve and validate task type support
        try:
            if not self._provider_registry.is_task_supported(project_id, task_type):
                self._blocked_count += 1
                self._last_error_code = "invalid_request"
                try:
                    self._event_sink.emit(
                        "request_rejected",
                        {
                            "request_id": req_id,
                            "project_id": project_id,
                            "reason": "invalid_request",
                            "detail": "unsupported_task_type",
                        },
                    )
                except Exception:
                    pass
                return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="invalid_request")
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="dependency_failed")

        # Model selection
        try:
            requires_tools = self._provider_registry.requires_tools(task_type)
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="dependency_failed")

        requires_vision = bool(upload_ids)  # Per contract for this mission/tests

        model_info: Optional[ModelInfo] = None
        try:
            if requested_provider_id and requested_model_id:
                model_info = self._provider_registry.explicit_model_allowed(
                    project_id, task_type, requested_provider_id, requested_model_id
                )
            else:
                model_info = self._provider_registry.select_default_model(
                    project_id,
                    task_type,
                    requires_vision=requires_vision,
                    requires_tools=requires_tools,
                    requested_provider_id=requested_provider_id,
                )
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="dependency_failed")

        # Validate model selection result
        if not model_info:
            self._blocked_count += 1
            self._last_error_code = "no_model_available"
            try:
                self._event_sink.emit(
                    "request_rejected",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "reason": "no_model_available",
                    },
                )
            except Exception:
                pass
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="no_model_available")

        # Enforce model enablement/availability/deprecation
        if (
            model_info.project_id != project_id
            or not model_info.enabled
            or not model_info.available
            or model_info.deprecated
        ):
            self._blocked_count += 1
            self._last_error_code = "no_model_available"
            try:
                self._event_sink.emit(
                    "request_rejected",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "reason": "no_model_available",
                    },
                )
            except Exception:
                pass
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="no_model_available")

        # Enforce capability constraints
        if requires_vision and not model_info.supports_vision:
            # Immediate block before budget/rate-limit per contract
            self._blocked_count += 1
            self._last_error_code = "no_model_available"
            try:
                self._event_sink.emit(
                    "request_rejected",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "reason": "no_model_available",
                        "detail": "vision_not_supported",
                    },
                )
            except Exception:
                pass
            return self._blocked_payload(
                req_id,
                created_at,
                project_id=project_id,
                conversation_id=conv_id,
                blocked_reason="no_model_available",
            )

        if requires_tools and not model_info.supports_tools:
            self._blocked_count += 1
            self._last_error_code = "no_model_available"
            try:
                self._event_sink.emit(
                    "request_rejected",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "reason": "no_model_available",
                        "detail": "tools_not_supported",
                    },
                )
            except Exception:
                pass
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="no_model_available")

        # Emit model_selected event safely
        try:
            self._event_sink.emit(
                "model_selected",
                {
                    "request_id": req_id,
                    "project_id": project_id,
                    "provider_id": model_info.provider_id,
                    "model_id": model_info.model_id,
                    "supports_vision": model_info.supports_vision,
                    "supports_tools": model_info.supports_tools,
                },
            )
        except Exception:
            pass

        # Budget preflight must occur before rate-limit
        try:
            budget = self._budget_evaluator.preflight(
                project_id=project_id,
                provider_id=model_info.provider_id,
                model_id=model_info.model_id,
                task_type=task_type,
                created_at=created_at,
                request_id=req_id,
            )
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(req_id, created_at, project_id=project_id, conversation_id=conv_id, blocked_reason="dependency_failed")

        status = str(budget.get("status", "allow"))
        warning: Optional[str] = None
        if status == "block":
            self._blocked_count += 1
            self._last_error_code = "budget_blocked"
            try:
                self._event_sink.emit(
                    "budget_blocked",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "provider_id": model_info.provider_id,
                        "model_id": model_info.model_id,
                        "task_type": task_type,
                    },
                )
            except Exception:
                pass
            return self._blocked_payload(
                req_id,
                created_at,
                project_id=project_id,
                conversation_id=conv_id,
                provider_id=model_info.provider_id,
                model_id=model_info.model_id,
                blocked_reason="budget_blocked",
            )
        elif status == "warn":
            warning = str(budget.get("message") or "budget_soft_limit")
            try:
                self._event_sink.emit(
                    "budget_warning",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "provider_id": model_info.provider_id,
                        "model_id": model_info.model_id,
                        "task_type": task_type,
                        "warning": warning,
                    },
                )
            except Exception:
                pass

        # Atomic rate limit check and registration
        try:
            rl = self._rate_limiter.check_and_register(
                project_id=project_id,
                provider_id=model_info.provider_id,
                model_id=model_info.model_id,
                task_type=task_type,
                request_id=req_id,
                created_at=created_at,
            )
        except Exception:
            self._blocked_count += 1
            self._last_error_code = "dependency_failed"
            return self._blocked_payload(
                req_id,
                created_at,
                project_id=project_id,
                conversation_id=conv_id,
                provider_id=model_info.provider_id,
                model_id=model_info.model_id,
                blocked_reason="dependency_failed",
            )

        if not bool(rl.get("allowed", False)):
            self._blocked_count += 1
            self._last_error_code = "rate_limit_blocked"
            try:
                self._event_sink.emit(
                    "rate_limit_blocked",
                    {
                        "request_id": req_id,
                        "project_id": project_id,
                        "provider_id": model_info.provider_id,
                        "model_id": model_info.model_id,
                        "task_type": task_type,
                    },
                )
            except Exception:
                pass
            return self._blocked_payload(
                req_id,
                created_at,
                project_id=project_id,
                conversation_id=conv_id,
                provider_id=model_info.provider_id,
                model_id=model_info.model_id,
                blocked_reason="rate_limit_blocked",
            )

        # Accepted result
        result: ProcessResult = {
            "accepted": True,
            "request_id": req_id,
            "project_id": project_id,
            "conversation_id": conv_id,
            "provider_id": model_info.provider_id,
            "model_id": model_info.model_id,
            "task_type": task_type,
            "warning": warning,
            "blocked_reason": None,
            "created_at": created_at,
            "project_context": self._sanitize_project_context(project_ctx),
        }
        self._accepted_count += 1
        try:
            self._event_sink.emit(
                "request_gate_accepted",
                {
                    "request_id": req_id,
                    "project_id": project_id,
                    "provider_id": model_info.provider_id,
                    "model_id": model_info.model_id,
                    "task_type": task_type,
                },
            )
        except Exception:
            pass
        # Do not expose or echo user_message or metadata in result
        _ = user_message  # explicitly unused, ensure not leaked
        return result

    def _sanitize_project_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Only include safe minimal fields necessary downstream
        safe: Dict[str, Any] = {}
        pid = ctx.get("project_id") if isinstance(ctx, dict) else None
        if isinstance(pid, str):
            safe["project_id"] = pid
        return safe

    def _blocked_payload(
        self,
        request_id: str,
        created_at: Any,
        *,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        blocked_reason: str,
    ) -> ProcessResult:
        return {
            "accepted": False,
            "request_id": request_id,
            "project_id": project_id,
            "conversation_id": conversation_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "task_type": None,
            "warning": None,
            "blocked_reason": blocked_reason,
            "created_at": created_at,
            "project_context": {},
        }
