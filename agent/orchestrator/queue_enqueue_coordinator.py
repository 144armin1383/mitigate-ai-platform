from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from datetime import datetime, timezone


class QueueEnqueueCoordinator:
    """
    Queue Enqueue Coordinator

    - Pure Python 3.12 compatible, standard library only
    - Provider-neutral and project-neutral
    - Uses dependency-injected public interfaces only (queue resolver, clock, event sink)
    - Deterministic, secure, and does not mutate inputs
    """

    # Explicitly supported method names for adapter compatibility
    _BATCH_METHODS: Tuple[str, ...] = (
        "enqueue_batch",
        "enqueue_many",
        "enqueue_missions",
    )
    _SINGLE_METHODS: Tuple[str, ...] = (
        "enqueue",
        "enqueue_one",
        "enqueue_mission",
    )

    # Required mission fields exactly (reject unknown)
    _REQUIRED_MISSION_FIELDS: Tuple[str, ...] = (
        "mission_id",
        "project_id",
        "request_id",
        "conversation_id",
        "plan_id",
        "step_id",
        "task_type",
        "provider_id",
        "model_id",
        "dependencies",
        "priority",
        "payload",
        "status",
        "created_at",
    )

    # Allowed event fields to ensure redaction/safety
    _ALLOWED_EVENT_KEYS: Tuple[str, ...] = (
        "type",
        "project_id",
        "mission_id",
        "mission_ids",
        "count",
        "enqueued_count",
        "atomic",
        "timestamp",
    )

    def __init__(self, queue_resolver: Any, clock: Any, event_sink: Any) -> None:
        self._queue_resolver = queue_resolver
        self._clock = clock
        self._event_sink = event_sink

    # -------------------------- Public Interface --------------------------

    def enqueue(
        self,
        project_id: str,
        queue_reference: str,
        missions: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """
        Enqueue a deterministically ordered list of validated missions into the project's queue.

        Returns a structured deterministic result dict with:
        - accepted (bool)
        - project_id (str)
        - mission_ids (List[str]) (successfully enqueued IDs only)
        - enqueued_count (int)
        - atomic (bool)
        - blocked_reason (Optional[str])
        - created_at (str ISO-8601)
        """
        created_at = self._now_iso()

        # Input validation (not planner content validation; only coordinator rules)
        valid_info = self.validate_enqueue_request(project_id, queue_reference, missions)
        if not valid_info["valid"]:
            return self._result(
                accepted=False,
                project_id=project_id,
                mission_ids=[],
                atomic=False,
                blocked_reason=valid_info["blocked_reason"] or "invalid_enqueue_request",
                created_at=created_at,
            )

        # Resolve queue
        self._emit({
            "type": "queue_resolution_started",
            "project_id": project_id,
            "timestamp": created_at,
        })
        try:
            queue = self._queue_resolver.resolve(project_id, queue_reference)
        except Exception:
            # Do not expose raw exceptions
            self._emit({
                "type": "queue_resolution_failed",
                "project_id": project_id,
                "timestamp": self._now_iso(),
            })
            return self._result(
                accepted=False,
                project_id=project_id,
                mission_ids=[],
                atomic=False,
                blocked_reason="queue_resolution_failed",
                created_at=created_at,
            )

        # Verify queue belongs to the selected project (cross-project protection)
        if not hasattr(queue, "project_id") or str(getattr(queue, "project_id")) != str(project_id):
            self._emit({
                "type": "queue_resolution_failed",
                "project_id": project_id,
                "timestamp": self._now_iso(),
            })
            return self._result(
                accepted=False,
                project_id=project_id,
                mission_ids=[],
                atomic=False,
                blocked_reason="cross_project_reference",
                created_at=created_at,
            )

        # Detect interfaces
        batch_callable = self._first_callable(queue, self._BATCH_METHODS)
        single_callable = self._first_callable(queue, self._SINGLE_METHODS)

        # Prefer atomic batch if available
        if batch_callable is not None:
            expected_ids = [str(m.get("mission_id")) for m in missions]
            self._emit({
                "type": "queue_batch_started",
                "project_id": project_id,
                "count": len(expected_ids),
                "atomic": True,
                "timestamp": self._now_iso(),
            })
            try:
                returned = batch_callable(missions)
            except Exception:
                self._emit({
                    "type": "queue_failed",
                    "project_id": project_id,
                    "enqueued_count": 0,
                    "atomic": True,
                    "timestamp": self._now_iso(),
                })
                # Do not attempt individual after failed atomic batch call
                result = self._result(
                    accepted=False,
                    project_id=project_id,
                    mission_ids=[],
                    atomic=True,
                    blocked_reason="queue_failed",
                    created_at=created_at,
                )
                self._emit({
                    "type": "enqueue_completed",
                    "project_id": project_id,
                    "enqueued_count": 0,
                    "atomic": True,
                    "timestamp": self._now_iso(),
                })
                return result

            # Validate returned IDs
            ok = isinstance(returned, list) and [str(x) for x in returned] == expected_ids
            if not ok:
                self._emit({
                    "type": "queue_failed",
                    "project_id": project_id,
                    "enqueued_count": 0,
                    "atomic": True,
                    "timestamp": self._now_iso(),
                })
                result = self._result(
                    accepted=False,
                    project_id=project_id,
                    mission_ids=[],
                    atomic=True,
                    blocked_reason="queue_failed",
                    created_at=created_at,
                )
                self._emit({
                    "type": "enqueue_completed",
                    "project_id": project_id,
                    "enqueued_count": 0,
                    "atomic": True,
                    "timestamp": self._now_iso(),
                })
                return result

            # Success
            self._emit({
                "type": "queue_batch_completed",
                "project_id": project_id,
                "count": len(expected_ids),
                "atomic": True,
                "timestamp": self._now_iso(),
            })
            result = self._result(
                accepted=True,
                project_id=project_id,
                mission_ids=expected_ids,
                atomic=True,
                blocked_reason=None,
                created_at=created_at,
            )
            self._emit({
                "type": "enqueue_completed",
                "project_id": project_id,
                "enqueued_count": len(expected_ids),
                "atomic": True,
                "timestamp": self._now_iso(),
            })
            return result

        # Non-atomic path requires a single-mission method
        if single_callable is None:
            return self._result(
                accepted=False,
                project_id=project_id,
                mission_ids=[],
                atomic=False,
                blocked_reason="unsupported_queue_interface",
                created_at=created_at,
            )

        # Validate complete mission set already done before first enqueue
        total = len(missions)
        self._emit({
            "type": "queue_individual_started",
            "project_id": project_id,
            "count": total,
            "atomic": False,
            "timestamp": self._now_iso(),
        })

        enqueued_ids: List[str] = []
        for m in missions:
            mid = str(m.get("mission_id"))
            try:
                rv = single_callable(m)
            except Exception:
                # Failure occurred
                self._emit({
                    "type": "queue_failed",
                    "project_id": project_id,
                    "enqueued_count": len(enqueued_ids),
                    "atomic": False,
                    "timestamp": self._now_iso(),
                })
                blocked_reason = "partial_enqueue" if enqueued_ids else "queue_failed"
                result = self._result(
                    accepted=False,
                    project_id=project_id,
                    mission_ids=enqueued_ids,
                    atomic=False,
                    blocked_reason=blocked_reason,
                    created_at=created_at,
                )
                if enqueued_ids:
                    self._emit({
                        "type": "partial_enqueue",
                        "project_id": project_id,
                        "count": total,
                        "enqueued_count": len(enqueued_ids),
                        "atomic": False,
                        "timestamp": self._now_iso(),
                    })
                self._emit({
                    "type": "enqueue_completed",
                    "project_id": project_id,
                    "enqueued_count": len(enqueued_ids),
                    "atomic": False,
                    "timestamp": self._now_iso(),
                })
                return result

            # Interpret return value: success unless explicit False
            if rv is False:
                self._emit({
                    "type": "queue_failed",
                    "project_id": project_id,
                    "enqueued_count": len(enqueued_ids),
                    "atomic": False,
                    "timestamp": self._now_iso(),
                })
                blocked_reason = "partial_enqueue" if enqueued_ids else "queue_failed"
                result = self._result(
                    accepted=False,
                    project_id=project_id,
                    mission_ids=enqueued_ids,
                    atomic=False,
                    blocked_reason=blocked_reason,
                    created_at=created_at,
                )
                if enqueued_ids:
                    self._emit({
                        "type": "partial_enqueue",
                        "project_id": project_id,
                        "count": total,
                        "enqueued_count": len(enqueued_ids),
                        "atomic": False,
                        "timestamp": self._now_iso(),
                    })
                self._emit({
                    "type": "enqueue_completed",
                    "project_id": project_id,
                    "enqueued_count": len(enqueued_ids),
                    "atomic": False,
                    "timestamp": self._now_iso(),
                })
                return result

            enqueued_ids.append(mid)
            self._emit({
                "type": "mission_enqueued",
                "project_id": project_id,
                "mission_id": mid,
                "atomic": False,
                "timestamp": self._now_iso(),
            })

        # All enqueued successfully
        result = self._result(
            accepted=True,
            project_id=project_id,
            mission_ids=enqueued_ids,
            atomic=False,
            blocked_reason=None,
            created_at=created_at,
        )
        self._emit({
            "type": "enqueue_completed",
            "project_id": project_id,
            "enqueued_count": len(enqueued_ids),
            "atomic": False,
            "timestamp": self._now_iso(),
        })
        return result

    def validate_enqueue_request(
        self,
        project_id: str,
        queue_reference: str,
        missions: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Optional[str] | bool]:
        """
        Validate the enqueue request for coordinator-level invariants.

        Returns dict: {"valid": bool, "blocked_reason": Optional[str], "error": Optional[str]}
        """
        # project_id must be non-empty identifier
        if not isinstance(project_id, str) or not project_id.strip():
            return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "invalid_project_id"}

        # missions must be a non-empty list/sequence
        if not isinstance(missions, Sequence) or isinstance(missions, (str, bytes)) or len(missions) == 0:
            return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "empty_or_invalid_missions"}

        # Validate each mission structure and cross-relationships
        required = set(self._REQUIRED_MISSION_FIELDS)
        seen_ids: List[str] = []

        # Pre-collect IDs and check duplicates and project match
        ids_set = set()
        for m in missions:
            if not isinstance(m, Mapping):
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "mission_not_mapping"}
            keys = set(m.keys())
            if keys != required:
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "unknown_or_missing_fields"}
            mid = str(m.get("mission_id"))
            if not mid:
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "missing_mission_id"}
            if mid in ids_set:
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "duplicate_mission_id"}
            ids_set.add(mid)
            # Every mission must belong to project_id
            if str(m.get("project_id")) != str(project_id):
                return {"valid": False, "blocked_reason": "cross_project_reference", "error": "mission_project_mismatch"}
            # Status must be pending
            if m.get("status") != "pending":
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "status_not_pending"}

        # Dependency validation: all deps reference other missions in same list, no self, appear earlier
        seen: set[str] = set()
        for m in missions:
            mid = str(m.get("mission_id"))
            deps = m.get("dependencies")
            if not isinstance(deps, Sequence) or isinstance(deps, (str, bytes)):
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "dependencies_not_list"}
            # Each dependency must be string mission_id
            dep_ids = [str(d) for d in deps]
            # No self-dependencies
            if mid in dep_ids:
                return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "self_dependency"}
            # Every dependency must reference another mission_id in same list
            for d in dep_ids:
                if d not in ids_set:
                    return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "unknown_dependency"}
                if d not in seen:
                    # Must appear earlier than dependant
                    return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "dependency_order_violation"}
            seen.add(mid)
            seen_ids.append(mid)

        # queue_reference basic check (string, non-empty)
        if not isinstance(queue_reference, str) or not queue_reference.strip():
            return {"valid": False, "blocked_reason": "invalid_enqueue_request", "error": "invalid_queue_reference"}

        return {"valid": True, "blocked_reason": None, "error": None}

    def status(self) -> Dict[str, Any]:
        """Return a simple health/status report without secrets."""
        return {
            "service": "QueueEnqueueCoordinator",
            "healthy": True,
            "timestamp": self._now_iso(),
        }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return latest events from the event sink with redaction to safe fields only."""
        try:
            events = self._event_sink.latest(limit, project_id=project_id)
        except Exception:
            return []
        sanitized: List[Dict[str, Any]] = []
        for e in events:
            if not isinstance(e, Mapping):
                continue
            allowed = {k: e[k] for k in self._ALLOWED_EVENT_KEYS if k in e}
            sanitized.append(allowed)
        return sanitized

    # -------------------------- Internal Helpers --------------------------

    def _result(
        self,
        *,
        accepted: bool,
        project_id: str,
        mission_ids: Sequence[str],
        atomic: bool,
        blocked_reason: Optional[str],
        created_at: str,
    ) -> Dict[str, Any]:
        """Create a deterministic structured result in consistent key order."""
        # Ensure deterministic list conversion
        mids = [str(m) for m in mission_ids]
        return {
            "accepted": bool(accepted),
            "project_id": str(project_id),
            "mission_ids": mids,
            "enqueued_count": len(mids),
            "atomic": bool(atomic),
            "blocked_reason": blocked_reason,
            "created_at": created_at,
        }

    def _first_callable(self, obj: Any, names: Iterable[str]) -> Optional[Any]:
        for name in names:
            attr = getattr(obj, name, None)
            if callable(attr):
                return attr
        return None

    def _emit(self, event: Mapping[str, Any]) -> None:
        # Redact to allowed keys only before emitting
        safe: Dict[str, Any] = {k: event[k] for k in self._ALLOWED_EVENT_KEYS if k in event}
        # Ensure timestamp present
        if "timestamp" not in safe:
            safe["timestamp"] = self._now_iso()
        try:
            self._event_sink.emit(safe)
        except Exception:
            # Never raise from event emission; silently drop to preserve enqueue behavior
            pass

    def _now_iso(self) -> str:
        try:
            now: datetime = self._clock.now()  # type: ignore[no-any-return]
            if not isinstance(now, datetime):
                raise TypeError
        except Exception:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        # Use microseconds for deterministic precision
        return now.isoformat()
