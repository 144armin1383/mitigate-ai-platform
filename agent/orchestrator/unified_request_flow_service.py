from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from copy import deepcopy


# Public interface: UnifiedRequestFlowService with submit(request), status(), latest_events(limit, project_id=None)

SafeResult = Dict[str, Any]
RawRequest = Dict[str, Any]
ApprovedRequest = Dict[str, Any]
EventRecord = Dict[str, Any]


_ALLOWED_GATE_BLOCKED_REASONS: Tuple[str, ...] = (
    "invalid_request",
    "unknown_project",
    "cross_project_reference",
    "no_model_available",
    "budget_blocked",
    "rate_limit_blocked",
    "dependency_failed",
)

_ALLOWED_PLANNER_QUEUE_FAILURES: Tuple[str, ...] = (
    "invalid_approved_request",
    "planner_failed",
    "invalid_plan",
    "queue_resolution_failed",
    "unsupported_queue_interface",
    "queue_failed",
    "partial_enqueue",
    "dependency_failed",
)

# Success result shape keys (and also used for blocked result shape)
_ALLOWED_RESULT_KEYS: Tuple[str, ...] = (
    "accepted",
    "request_id",
    "project_id",
    "conversation_id",
    "provider_id",
    "model_id",
    "task_type",
    "plan_id",
    "plan_summary",
    "mission_ids",
    "warning",
    "blocked_reason",
    "created_at",
)

# Safe event payload keys (must not include user_message or sensitive contents)
_ALLOWED_EVENT_KEYS: Tuple[str, ...] = (
    "status",
    "accepted",
    "request_id",
    "project_id",
    "conversation_id",
    "provider_id",
    "model_id",
    "task_type",
    "warning",
    "blocked_reason",
)


class UnifiedRequestFlowService:
    """
    A small reusable service that accepts one user request, processes it through the injected
    RequestGateSelector, and if accepted forwards an approved request to the injected
    PlannerQueueFlowCoordinator. Returns a sanitized safe result and emits structured safe events.

    Security and privacy constraints:
    - Never include user_message in returned status or events.
    - Never expose uploaded file contents; only upload_ids may be propagated (not returned).
    - Never mutate the original request.
    - Never continue to planner after a blocked gate result.
    - Convert unexpected exceptions into dependency_failed without exposing raw exceptions.
    """

    def __init__(
        self,
        *,
        request_gate_selector: Any,
        planner_queue_flow_coordinator: Any,
        clock: Any,
        event_sink: Any,
    ) -> None:
        self._gate = request_gate_selector
        self._planner = planner_queue_flow_coordinator
        self._clock = clock
        self._event_sink = event_sink

        self._latest_status: Optional[SafeResult] = None
        # Internal deterministic event buffer to support latest_events API
        self._event_buffer: List[Dict[str, Any]] = []

    # ---------------------- Public API ----------------------

    def submit(self, request: RawRequest) -> SafeResult:
        """
        Process one raw user request through the gate, then (if accepted) through the planner/queue.
        Returns a sanitized safe result.
        """
        raw_request: RawRequest = deepcopy(request)
        self._emit("unified_request_started", self._build_event_payload_from_request(raw_request, status="started"))

        try:
            gate_result: Dict[str, Any] = self._gate.process_request(raw_request)
        except Exception:
            # Convert unexpected raw exceptions into dependency_failed, avoiding leaking details
            blocked = self._build_dependency_failed_result_from_request(raw_request)
            self._emit("request_gate_blocked", self._build_event_payload_from_result(blocked, status="blocked"))
            self._set_status(blocked)
            self._emit("unified_request_failed", self._build_event_payload_from_result(blocked, status="failed"))
            return blocked

        # Sanity: do not silently repair malformed dependency results — we propagate fields as given,
        # only sanitize/redact output shape.
        accepted = bool(gate_result.get("accepted"))

        if not accepted:
            # blocked or rejected at gate level
            blocked_result = self._sanitize_result(gate_result)
            # Ensure a documented blocked_reason is preserved unchanged if provided
            # Do not map to planner errors.
            self._emit("request_gate_blocked", self._build_event_payload_from_result(blocked_result, status="blocked"))
            self._set_status(blocked_result)
            self._emit("unified_request_failed", self._build_event_payload_from_result(blocked_result, status="failed"))
            return blocked_result

        # Gate accepted the request; construct approved request for planner/queue
        approved_request = self._build_approved_request(
            gate_result=gate_result,
            original_request=raw_request,
        )

        self._emit("request_gate_accepted", self._build_event_payload_from_result(self._sanitize_result(gate_result), status="accepted"))
        self._emit("planner_queue_started", self._build_event_payload_from_result(self._sanitize_result(gate_result), status="started"))

        try:
            pq_result: Dict[str, Any] = self._planner.process(approved_request)
        except Exception:
            failure = self._build_dependency_failed_result_from_gate_accept(gate_result)
            self._emit("planner_queue_failed", self._build_event_payload_from_result(failure, status="failed"))
            self._set_status(failure)
            self._emit("unified_request_failed", self._build_event_payload_from_result(failure, status="failed"))
            return failure

        # Planner/Queue returned a result; sanitize and enforce boundaries
        final_result = self._merge_and_sanitize_final_result(gate_result, pq_result)

        if not bool(final_result.get("accepted")):
            # Propagate planner/queue failure unchanged
            self._emit("planner_queue_failed", self._build_event_payload_from_result(final_result, status="failed"))
            self._set_status(final_result)
            self._emit("unified_request_failed", self._build_event_payload_from_result(final_result, status="failed"))
            return final_result

        # Success
        self._set_status(final_result)
        self._emit("unified_request_completed", self._build_event_payload_from_result(final_result, status="completed"))
        return final_result

    def status(self) -> Optional[SafeResult]:
        """Return the latest sanitized status for the most recent submit call, or None if none."""
        if self._latest_status is None:
            return None
        # Return a deep copy to avoid external mutation
        return deepcopy(self._latest_status)

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return the most recent emitted events (sanitized), optionally filtered by project_id."""
        if limit <= 0:
            return []
        events = self._event_buffer
        if project_id is not None:
            events = [e for e in events if e.get("payload", {}).get("project_id") == project_id]
        # Return the last N events deterministically
        subset = events[-limit:]
        return deepcopy(subset)

    # ---------------------- Internal helpers ----------------------

    def _set_status(self, result: SafeResult) -> None:
        self._latest_status = deepcopy(result)

    def _build_dependency_failed_result_from_request(self, request: RawRequest) -> SafeResult:
        # Build a blocked result derived only from the original request (no cross-request substitution)
        result: SafeResult = {
            "accepted": False,
            "blocked_reason": "dependency_failed",
        }
        # Preserve safe identifiers if provided by the request itself
        for key in ("request_id", "project_id", "conversation_id", "provider_id", "model_id", "task_type"):
            if key in request:
                result[key] = request[key]
        # created_at: do not synthesize from environment; omit to avoid silent repair
        return self._sanitize_result(result)

    def _build_dependency_failed_result_from_gate_accept(self, gate_result: Dict[str, Any]) -> SafeResult:
        # Build a planner/queue failure preserving validated identifiers from the gate result
        result: SafeResult = {
            "accepted": False,
            "blocked_reason": "dependency_failed",
        }
        for key in ("request_id", "project_id", "conversation_id", "provider_id", "model_id", "task_type", "created_at"):
            if key in gate_result:
                result[key] = gate_result[key]
        # Preserve any gate warning
        if "warning" in gate_result:
            result["warning"] = gate_result["warning"]
        return self._sanitize_result(result)

    def _build_approved_request(self, *, gate_result: Dict[str, Any], original_request: RawRequest) -> ApprovedRequest:
        # Map fields strictly from gate_result and original_request
        approved: ApprovedRequest = {
            "accepted": True,
            "request_id": gate_result.get("request_id"),
            "project_id": gate_result.get("project_id"),
            "conversation_id": gate_result.get("conversation_id"),
            "provider_id": gate_result.get("provider_id"),
            "model_id": gate_result.get("model_id"),
            "task_type": gate_result.get("task_type"),
            # Only pass user_message downstream; never include it in status/events/logs
            "user_message": original_request.get("user_message"),
            # Preserve upload_ids for downstream only (not returned)
            "upload_ids": deepcopy(original_request.get("upload_ids") or []),
            # created_at and warning from the gate (do not synthesize)
            "created_at": gate_result.get("created_at"),
            "warning": gate_result.get("warning"),
            # Optional project_context from the gate
            "project_context": gate_result.get("project_context"),
        }
        return approved

    def _merge_and_sanitize_final_result(self, gate_result: Dict[str, Any], pq_result: Dict[str, Any]) -> SafeResult:
        # Start with identifiers from gate_result (validated), then overlay planner/queue status fields.
        merged: Dict[str, Any] = {
            "request_id": gate_result.get("request_id"),
            "project_id": gate_result.get("project_id"),
            "conversation_id": gate_result.get("conversation_id"),
            "provider_id": gate_result.get("provider_id"),
            "model_id": gate_result.get("model_id"),
            "task_type": gate_result.get("task_type"),
            "created_at": gate_result.get("created_at"),
        }
        # Preserve gate warning on success/failure
        if "warning" in gate_result:
            merged["warning"] = gate_result["warning"]

        # Overlay accepted and planner/queue fields
        if "accepted" in pq_result:
            merged["accepted"] = bool(pq_result["accepted"])  # enforce boolean
        if "plan_id" in pq_result:
            merged["plan_id"] = pq_result["plan_id"]
        if "plan_summary" in pq_result:
            merged["plan_summary"] = pq_result["plan_summary"]
        if "mission_ids" in pq_result:
            merged["mission_ids"] = pq_result["mission_ids"]
        if "blocked_reason" in pq_result:
            merged["blocked_reason"] = pq_result["blocked_reason"]

        return self._sanitize_result(merged)

    def _sanitize_result(self, result: Dict[str, Any]) -> SafeResult:
        # Only include whitelisted keys and ensure redaction of user_message and uploaded contents
        sanitized: SafeResult = {}
        for key in _ALLOWED_RESULT_KEYS:
            if key in result:
                if key == "mission_ids":
                    value = result[key]
                    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                        # Keep as-is for simple sequences (IDs)
                        sanitized[key] = list(value)
                    # else: drop malformed mission_ids silently for safety, avoiding repair
                else:
                    sanitized[key] = result[key]
        # Never include user_message in the result
        if "user_message" in sanitized:
            del sanitized["user_message"]
        # Ensure no nested unexpected keys are leaked
        return sanitized

    def _build_event_payload_from_request(self, request: RawRequest, *, status: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": status,
        }
        for key in ("request_id", "project_id", "conversation_id", "provider_id", "model_id", "task_type", "warning"):
            if key in request:
                payload[key] = request[key]
        # Never include user_message
        return self._sanitize_event_payload(payload)

    def _build_event_payload_from_result(self, result: Dict[str, Any], *, status: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"status": status}
        for key in ("accepted", "request_id", "project_id", "conversation_id", "provider_id", "model_id", "task_type", "warning", "blocked_reason"):
            if key in result:
                payload[key] = result[key]
        return self._sanitize_event_payload(payload)

    def _sanitize_event_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key in _ALLOWED_EVENT_KEYS:
            if key in payload:
                safe[key] = payload[key]
        # Ensure no user_message
        if "user_message" in safe:
            del safe["user_message"]
        return safe

    def _emit(self, name: str, payload: Dict[str, Any]) -> None:
        record = {"name": name, "payload": deepcopy(payload)}
        # Internal buffer first (deterministic retention)
        self._event_buffer.append(record)
        # External sink emission (best-effort; do not raise if sink fails)
        try:
            self._event_sink.emit(name, payload)
        except Exception:
            # Swallow event sink errors to keep service deterministic and non-intrusive
            pass


__all__ = ["UnifiedRequestFlowService"]
