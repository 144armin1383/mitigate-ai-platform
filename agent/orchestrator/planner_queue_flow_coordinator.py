from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple


class PlannerQueueFlowCoordinator:
    """
    Coordinates the flow from an approved request through Planner, PlanValidatorMissionBuilder,
    and QueueEnqueueCoordinator. All dependencies must be injected via the constructor and
    must expose public interfaces used here.

    This module uses only Python standard library and is fully typed for Python 3.12.
    """

    # Failure codes
    INVALID_APPROVED_REQUEST = "invalid_approved_request"
    PLANNER_FAILED = "planner_failed"
    INVALID_PLAN = "invalid_plan"
    QUEUE_RESOLUTION_FAILED = "queue_resolution_failed"
    UNSUPPORTED_QUEUE_INTERFACE = "unsupported_queue_interface"
    QUEUE_FAILED = "queue_failed"
    PARTIAL_ENQUEUE = "partial_enqueue"
    DEPENDENCY_FAILED = "dependency_failed"

    # Events
    EVT_FLOW_STARTED = "planner_flow_started"
    EVT_PLANNER_STARTED = "planner_started"
    EVT_PLANNER_FAILED = "planner_failed"
    EVT_PLAN_VALIDATED = "plan_validated"
    EVT_PLAN_REJECTED = "plan_rejected"
    EVT_MISSIONS_BUILT = "missions_built"
    EVT_QUEUE_SUBMISSION_STARTED = "queue_submission_started"
    EVT_QUEUE_SUBMISSION_FAILED = "queue_submission_failed"
    EVT_FLOW_COMPLETED = "planner_queue_flow_completed"

    _APPROVED_REQUEST_FIELDS = {
        "accepted",
        "request_id",
        "project_id",
        "conversation_id",
        "provider_id",
        "model_id",
        "task_type",
        "user_message",
        "upload_ids",
        "created_at",
        "warning",
        "project_context",
    }
    _PROJECT_CONTEXT_REQUIRED_FIELDS = {
        "repository_root",
        "default_branch",
        "project_type",
        "policy_profile",
        "queue_reference",
    }

    def __init__(
        self,
        *,
        planner: Any,
        builder: Any,
        queue_coordinator: Any,
        clock: Any,
        event_sink: Any,
    ) -> None:
        self._planner = planner
        self._builder = builder
        self._queue = queue_coordinator
        self._clock = clock
        self._event_sink = event_sink

        self._processed_count: int = 0
        self._accepted_count: int = 0
        self._rejected_count: int = 0
        self._events: List[Dict[str, Any]] = []

    # -------------------- Public API --------------------

    def validate_approved_request(
        self, approved_request: Mapping[str, Any]
    ) -> Tuple[bool, Mapping[str, Any] | str]:
        """
        Validate the approved request schema and project-context structure.
        - Ensures only expected top-level fields are present.
        - Ensures accepted is True.
        - Validates identifiers and user_message.
        - Validates upload_ids is a list.
        - Validates project_context structure and project ownership.
        - Does not attempt to resolve queue_reference.

        Returns (True, normalized_request) if valid; otherwise (False, reason_code).
        """
        if not isinstance(approved_request, Mapping):
            return False, self.INVALID_APPROVED_REQUEST

        keys = set(approved_request.keys())
        if keys != self._APPROVED_REQUEST_FIELDS:
            return False, self.INVALID_APPROVED_REQUEST

        # accepted must be True
        if approved_request.get("accepted") is not True:
            return False, self.INVALID_APPROVED_REQUEST

        # Validate identifiers and types
        id_fields = (
            "request_id",
            "project_id",
            "conversation_id",
            "provider_id",
            "model_id",
            "task_type",
        )
        for k in id_fields:
            if not _is_valid_identifier(approved_request.get(k)):
                return False, self.INVALID_APPROVED_REQUEST

        # user_message must be non-empty string
        if not _is_nonempty_str(approved_request.get("user_message")):
            return False, self.INVALID_APPROVED_REQUEST

        # upload_ids must be a list (content not validated here)
        if not isinstance(approved_request.get("upload_ids"), list):
            return False, self.INVALID_APPROVED_REQUEST

        # created_at should be present; accept string or number, normalize to string
        created_at = approved_request.get("created_at")
        if created_at is None:
            return False, self.INVALID_APPROVED_REQUEST

        # warning may be any string or None; normalize to string
        warning_val = approved_request.get("warning")
        if warning_val is not None and not isinstance(warning_val, str):
            return False, self.INVALID_APPROVED_REQUEST

        # Validate project_context
        pc_raw = approved_request.get("project_context")
        if not isinstance(pc_raw, Mapping):
            return False, self.INVALID_APPROVED_REQUEST

        # Must provide required fields
        for req in self._PROJECT_CONTEXT_REQUIRED_FIELDS:
            if req not in pc_raw:
                return False, self.INVALID_APPROVED_REQUEST

        # Types for project_context required fields
        if not _is_nonempty_str(pc_raw.get("repository_root")):
            return False, self.INVALID_APPROVED_REQUEST
        if not _is_nonempty_str(pc_raw.get("default_branch")):
            return False, self.INVALID_APPROVED_REQUEST
        if not _is_nonempty_str(pc_raw.get("project_type")):
            return False, self.INVALID_APPROVED_REQUEST
        if not _is_nonempty_str(pc_raw.get("policy_profile")):
            return False, self.INVALID_APPROVED_REQUEST
        if not _is_nonempty_str(pc_raw.get("queue_reference")):
            return False, self.INVALID_APPROVED_REQUEST

        # Cross-project references must be rejected: ensure project_context belongs to project_id
        # Require project_context to include project_id and it must match
        pc_project_id = pc_raw.get("project_id")
        if pc_project_id is not None and not _is_nonempty_str(pc_project_id):
            return False, self.INVALID_APPROVED_REQUEST
        if pc_project_id is not None and pc_project_id != approved_request["project_id"]:
            return False, self.INVALID_APPROVED_REQUEST

        # Build normalized copy with only allowed keys at top level and keep project_context as-is
        normalized: Dict[str, Any] = {
            "accepted": True,
            "request_id": str(approved_request["request_id"]).strip(),
            "project_id": str(approved_request["project_id"]).strip(),
            "conversation_id": str(approved_request["conversation_id"]).strip(),
            "provider_id": str(approved_request["provider_id"]).strip(),
            "model_id": str(approved_request["model_id"]).strip(),
            "task_type": str(approved_request["task_type"]).strip(),
            "user_message": str(approved_request["user_message"]),
            "upload_ids": list(approved_request["upload_ids"]),
            "created_at": str(approved_request["created_at"]),
            "warning": approved_request.get("warning") if warning_val is None or isinstance(warning_val, str) else None,
            "project_context": dict(pc_raw),
        }
        return True, normalized

    def process(self, approved_request: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Process the approved request through planner -> builder -> queue.
        Returns a safe structured result with required fields.
        """
        self._processed_count += 1

        # Minimal safe identifiers for events
        req_id = _safe_id(approved_request.get("request_id"))
        proj_id = _safe_id(approved_request.get("project_id"))
        provider = _safe_id(approved_request.get("provider_id"))
        model = _safe_id(approved_request.get("model_id"))
        task_type = _safe_id(approved_request.get("task_type"))

        self._emit(
            self.EVT_FLOW_STARTED,
            {
                "request_id": req_id,
                "project_id": proj_id,
                "provider_id": provider,
                "model_id": model,
                "task_type": task_type,
                "status": "started",
            },
        )

        valid, validated_or_reason = self.validate_approved_request(approved_request)
        if not valid:
            self._rejected_count += 1
            # Return invalid_approved_request without planner invocation
            result = self._build_result_template(
                approved_request,
                accepted=False,
                blocked_reason=self.INVALID_APPROVED_REQUEST,
                plan_id="",
                plan_summary="",
                mission_ids=[],
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.INVALID_APPROVED_REQUEST,
                },
            )
            return result

        approved_norm = validated_or_reason  # type: ignore[assignment]
        assert isinstance(approved_norm, Mapping)

        # Build deterministic planner input in strict order
        planner_input: Dict[str, Any] = {
            "request_id": approved_norm["request_id"],
            "project_id": approved_norm["project_id"],
            "conversation_id": approved_norm["conversation_id"],
            "repository_root": approved_norm["project_context"]["repository_root"],
            "default_branch": approved_norm["project_context"]["default_branch"],
            "project_type": approved_norm["project_context"]["project_type"],
            "policy_profile": approved_norm["project_context"]["policy_profile"],
            "provider_id": approved_norm["provider_id"],
            "model_id": approved_norm["model_id"],
            "task_type": approved_norm["task_type"],
            "user_message": approved_norm["user_message"],
            "upload_ids": approved_norm["upload_ids"],
        }

        # Invoke planner
        self._emit(
            self.EVT_PLANNER_STARTED,
            {
                "request_id": req_id,
                "project_id": proj_id,
                "provider_id": provider,
                "model_id": model,
                "task_type": task_type,
                "status": "started",
            },
        )

        try:
            plan = self._planner.plan(planner_input)
        except Exception:
            # Never expose raw planner exceptions
            self._rejected_count += 1
            self._emit(
                self.EVT_PLANNER_FAILED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.PLANNER_FAILED,
                },
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.PLANNER_FAILED,
                },
            )
            return self._build_result_template(
                approved_norm,
                accepted=False,
                blocked_reason=self.PLANNER_FAILED,
                plan_id="",
                plan_summary="",
                mission_ids=[],
            )

        # Do not accept empty plans
        if not plan:
            self._rejected_count += 1
            self._emit(
                self.EVT_PLAN_REJECTED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.INVALID_PLAN,
                },
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.INVALID_PLAN,
                },
            )
            return self._build_result_template(
                approved_norm,
                accepted=False,
                blocked_reason=self.INVALID_PLAN,
                plan_id="",
                plan_summary="",
                mission_ids=[],
            )

        # Validate and build missions using builder
        try:
            build_result = self._builder.validate_and_build(plan, approved_norm)
        except Exception:
            # Unexpected builder error -> dependency_failed
            self._rejected_count += 1
            self._emit(
                self.EVT_PLAN_REJECTED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.DEPENDENCY_FAILED,
                },
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.DEPENDENCY_FAILED,
                },
            )
            return self._build_result_template(
                approved_norm,
                accepted=False,
                blocked_reason=self.DEPENDENCY_FAILED,
                plan_id="",
                plan_summary="",
                mission_ids=[],
            )

        # Expect builder to return a mapping with ok flag
        if not isinstance(build_result, Mapping) or not build_result.get("ok"):
            # Builder validation failure must return invalid_plan, and do not enqueue
            self._rejected_count += 1
            self._emit(
                self.EVT_PLAN_REJECTED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.INVALID_PLAN,
                },
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "provider_id": provider,
                    "model_id": model,
                    "task_type": task_type,
                    "status": self.INVALID_PLAN,
                },
            )
            return self._build_result_template(
                approved_norm,
                accepted=False,
                blocked_reason=self.INVALID_PLAN,
                plan_id="",
                plan_summary="",
                mission_ids=[],
            )

        # Extract missions and metadata
        missions = build_result.get("missions") or []
        plan_id = _safe_string(build_result.get("plan_id", ""))
        plan_summary = _safe_string(build_result.get("plan_summary", ""))

        # Validate missions: ensure identifier presence and preserve order
        mission_ids: List[str] = []
        for m in missions:
            if not isinstance(m, Mapping) or not _is_valid_identifier(m.get("mission_id")):
                # If builder produced invalid missions, treat as invalid_plan without repair
                self._rejected_count += 1
                self._emit(
                    self.EVT_PLAN_REJECTED,
                    {
                        "request_id": req_id,
                        "project_id": proj_id,
                        "provider_id": provider,
                        "model_id": model,
                        "task_type": task_type,
                        "status": self.INVALID_PLAN,
                    },
                )
                self._emit(
                    self.EVT_FLOW_COMPLETED,
                    {
                        "request_id": req_id,
                        "project_id": proj_id,
                        "provider_id": provider,
                        "model_id": model,
                        "task_type": task_type,
                        "status": self.INVALID_PLAN,
                    },
                )
                return self._build_result_template(
                    approved_norm,
                    accepted=False,
                    blocked_reason=self.INVALID_PLAN,
                    plan_id="",
                    plan_summary="",
                    mission_ids=[],
                )
            mission_ids.append(str(m["mission_id"]))

        self._emit(
            self.EVT_PLAN_VALIDATED,
            {
                "request_id": req_id,
                "project_id": proj_id,
                "provider_id": provider,
                "model_id": model,
                "task_type": task_type,
                "status": "ok",
            },
        )
        self._emit(
            self.EVT_MISSIONS_BUILT,
            {
                "request_id": req_id,
                "project_id": proj_id,
                "count": len(missions),
                "status": "ok",
            },
        )

        # Resolve queue_reference only from approved project_context
        queue_reference = approved_norm["project_context"]["queue_reference"]

        # Enqueue missions
        self._emit(
            self.EVT_QUEUE_SUBMISSION_STARTED,
            {
                "request_id": req_id,
                "project_id": proj_id,
                "count": len(missions),
                "status": "started",
            },
        )

        try:
            enqueue_result = self._queue.enqueue(
                project_id=approved_norm["project_id"],
                queue_reference=queue_reference,
                missions=missions,
            )
        except Exception:
            # Do not expose exception details
            self._rejected_count += 1
            self._emit(
                self.EVT_QUEUE_SUBMISSION_FAILED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "count": len(missions),
                    "status": self.DEPENDENCY_FAILED,
                },
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "status": self.DEPENDENCY_FAILED,
                },
            )
            return self._build_result_template(
                approved_norm,
                accepted=False,
                blocked_reason=self.DEPENDENCY_FAILED,
                plan_id=plan_id,
                plan_summary=plan_summary,
                mission_ids=[],
            )

        if not isinstance(enqueue_result, Mapping):
            queue_accepted = False
            queue_failure_code = self.DEPENDENCY_FAILED
        else:
            # Production QueueEnqueueCoordinator contract uses
            # accepted / blocked_reason. Preserve compatibility
            # with the earlier ok / code contract used by tests
            # and alternate adapters.
            if "accepted" in enqueue_result:
                queue_accepted = bool(
                    enqueue_result.get("accepted")
                )
                queue_failure_code = (
                    enqueue_result.get("blocked_reason")
                )
            else:
                queue_accepted = bool(
                    enqueue_result.get("ok")
                )
                queue_failure_code = (
                    enqueue_result.get("code")
                )

        if not queue_accepted:
            # Map known failure codes; propagate queue failures unchanged.
            code = queue_failure_code

            if code == self.QUEUE_RESOLUTION_FAILED:
                blocked = self.QUEUE_RESOLUTION_FAILED
            elif code == self.UNSUPPORTED_QUEUE_INTERFACE:
                blocked = self.UNSUPPORTED_QUEUE_INTERFACE
            elif code == self.QUEUE_FAILED:
                blocked = self.QUEUE_FAILED
            elif code == self.PARTIAL_ENQUEUE:
                blocked = self.PARTIAL_ENQUEUE
            elif code == self.DEPENDENCY_FAILED:
                blocked = self.DEPENDENCY_FAILED
            else:
                blocked = self.DEPENDENCY_FAILED

            self._rejected_count += 1
            self._emit(
                self.EVT_QUEUE_SUBMISSION_FAILED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "count": len(missions),
                    "status": blocked,
                },
            )
            self._emit(
                self.EVT_FLOW_COMPLETED,
                {
                    "request_id": req_id,
                    "project_id": proj_id,
                    "status": blocked,
                },
            )
            return self._build_result_template(
                approved_norm,
                accepted=False,
                blocked_reason=blocked,
                plan_id=plan_id,
                plan_summary=plan_summary,
                mission_ids=[],
            )

        # Success
        self._accepted_count += 1
        self._emit(
            self.EVT_FLOW_COMPLETED,
            {
                "request_id": req_id,
                "project_id": proj_id,
                "provider_id": provider,
                "model_id": model,
                "task_type": task_type,
                "status": "ok",
            },
        )
        return self._build_result_template(
            approved_norm,
            accepted=True,
            blocked_reason="",
            plan_id=plan_id,
            plan_summary=plan_summary,
            mission_ids=mission_ids,
        )

    def status(self) -> Dict[str, Any]:
        return {
            "processed": self._processed_count,
            "accepted": self._accepted_count,
            "rejected": self._rejected_count,
        }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        if project_id is None:
            return list(self._events[-limit:])
        pid = str(project_id)
        filtered = [e for e in self._events if e.get("payload", {}).get("project_id") == pid]
        return filtered[-limit:]

    # -------------------- Internal helpers --------------------

    def _build_result_template(
        self,
        approved_request: Mapping[str, Any],
        *,
        accepted: bool,
        blocked_reason: str,
        plan_id: str,
        plan_summary: str,
        mission_ids: Sequence[str],
    ) -> Dict[str, Any]:
        # Sanitize fields as required by Success Result structure
        return {
            "accepted": bool(accepted),
            "request_id": _safe_id(approved_request.get("request_id")),
            "project_id": _safe_id(approved_request.get("project_id")),
            "conversation_id": _safe_id(approved_request.get("conversation_id")),
            "provider_id": _safe_id(approved_request.get("provider_id")),
            "model_id": _safe_id(approved_request.get("model_id")),
            "task_type": _safe_id(approved_request.get("task_type")),
            "plan_id": _safe_string(plan_id),
            "plan_summary": _safe_string(plan_summary),
            "mission_ids": [str(mid) for mid in mission_ids],
            "warning": _safe_string(approved_request.get("warning", "")),
            "blocked_reason": _safe_string(blocked_reason),
            "created_at": _safe_string(approved_request.get("created_at", "")),
        }

    def _emit(self, name: str, payload: Mapping[str, Any]) -> None:
        # Ensure event payload is safe and does not contain sensitive fields like user_message or upload_ids
        safe_payload: Dict[str, Any] = dict(payload)
        safe_payload.pop("user_message", None)
        safe_payload.pop("upload_ids", None)
        event = {
            "time": _safe_string(getattr(self._clock, "now", lambda: "")()),
            "event": str(name),
            "payload": safe_payload,
        }
        # Store in local buffer
        self._events.append(event)
        # Emit to external sink without sensitive data
        try:
            self._event_sink.emit(name, safe_payload)
        except Exception:
            # Swallow event sink errors silently; never expose sink exceptions
            pass


# -------------------- Utility functions --------------------


def _is_nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _is_valid_identifier(v: Any) -> bool:
    return _is_nonempty_str(v)


def _safe_string(v: Any, max_len: int = 1024) -> str:
    try:
        s = str(v) if v is not None else ""
    except Exception:
        s = ""
    s = s.replace("\r", " ").replace("\n", " ")
    if len(s) > max_len:
        s = s[:max_len]
    return s


def _safe_id(v: Any) -> str:
    return _safe_string(v, max_len=256)
