from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock, Condition, Thread
from typing import Any, Callable, Dict, List, Optional, Protocol, TypedDict, runtime_checkable, Union
import copy


# ===== Protocols and minimal public interfaces =====

@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class RealClock:
    def now(self) -> datetime:
        # Always return timezone-aware UTC timestamps for determinism
        return datetime.now(timezone.utc)


@runtime_checkable
class EventSink(Protocol):
    def emit(self, event: Dict[str, Any]) -> None: ...


# Application-side interfaces (minimal subset for typing only)

@runtime_checkable
class UnifiedRequestFlowService(Protocol):
    def submit(self, request: Any) -> Any: ...


@runtime_checkable
class ExecutionOutcomeCoordinator(Protocol):
    def process(self, outcome: Any) -> Any: ...


@runtime_checkable
class ManagedComponent(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


@runtime_checkable
class ApplicationContainer(Protocol):
    request_flow: UnifiedRequestFlowService
    execution_outcome_coordinator: ExecutionOutcomeCoordinator

    # Optional components; tests/fakes may implement as attributes
    background_worker: ManagedComponent  # type: ignore[assignment]
    autonomous_controller: ManagedComponent  # type: ignore[assignment]
    private_admin_api: ManagedComponent  # type: ignore[assignment]

    def close(self) -> None: ...


# Application status result may be a dict-like or object with .ready
class _AppStatusDict(TypedDict, total=False):
    ready: bool
    warnings: List[str]


ApplicationStatus = Union[_AppStatusDict, Any]


# ===== Runtime constants and state management =====

RuntimeState = str  # one of: created, starting, running, stopping, stopped, failed

_ALLOWED_STATES: List[RuntimeState] = [
    "created",
    "starting",
    "running",
    "stopping",
    "stopped",
    "failed",
]


# Failure codes
_FAILURE_INVALID_CONFIG = "invalid_runtime_config"
_FAILURE_INVALID_TRANSITION = "invalid_runtime_transition"
_FAILURE_NOT_RUNNING = "runtime_not_running"
_FAILURE_START_FAILED = "runtime_start_failed"
_FAILURE_STOP_FAILED = "runtime_stop_failed"
_FAILURE_COMPONENT_START_FAILED = "component_start_failed"
_FAILURE_COMPONENT_STOP_FAILED = "component_stop_failed"
_FAILURE_APP_NOT_READY = "application_not_ready"
_FAILURE_DEPENDENCY_FAILED = "dependency_failed"


# Event types
_EVENT_RUNTIME_CREATED = "runtime_created"
_EVENT_RUNTIME_STARTING = "runtime_starting"
_EVENT_RUNTIME_STARTED = "runtime_started"
_EVENT_RUNTIME_START_FAILED = "runtime_start_failed"
_EVENT_RUNTIME_STOPPING = "runtime_stopping"
_EVENT_RUNTIME_STOPPED = "runtime_stopped"
_EVENT_COMPONENT_STARTING = "component_starting"
_EVENT_COMPONENT_STARTED = "component_started"
_EVENT_COMPONENT_START_FAILED = "component_start_failed"
_EVENT_COMPONENT_STOPPING = "component_stopping"
_EVENT_COMPONENT_STOPPED = "component_stopped"
_EVENT_REQUEST_SUBMITTED = "request_submitted"
_EVENT_REQUEST_REJECTED = "request_rejected"
_EVENT_OUTCOME_PROCESSED = "execution_outcome_processed"
_EVENT_RUNTIME_OPERATION_FAILED = "runtime_operation_failed"


# ===== In-memory event sink =====

class InMemoryEventSink:
    def __init__(self, capacity: int = 1000, clock: Optional[Clock] = None) -> None:
        self._events: List[Dict[str, Any]] = []
        self._capacity = capacity
        self._clock = clock or RealClock()
        self._lock = RLock()

    def emit(self, event: Dict[str, Any]) -> None:  # type: ignore[override]
        # Ensure a timestamp exists and do not expose unsafe details
        safe_event = dict(event)
        if "ts" not in safe_event:
            safe_event["ts"] = self._clock.now().isoformat()
        with self._lock:
            self._events.append(safe_event)
            if len(self._events) > self._capacity:
                # Drop oldest to keep bounded memory
                del self._events[0 : len(self._events) - self._capacity]

    def latest(self, limit: int) -> List[Dict[str, Any]]:
        with self._lock:
            if limit <= 0:
                return []
            return [dict(e) for e in self._events[-limit:]]


# ===== Runtime configuration =====

@dataclass(frozen=True)
class RuntimeConfig:
    application_config: Any
    auto_start_background_worker: bool = False
    auto_start_autonomous_controller: bool = False
    auto_start_private_admin_api: bool = False


# ===== Runtime service =====

class RuntimeService:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        builder: Callable[[Any, Optional[Dict[str, Any]]], ApplicationContainer],
        application_status: Callable[[ApplicationContainer], ApplicationStatus],
        overrides: Optional[Dict[str, Any]] = None,
        clock: Optional[Clock] = None,
        event_sink: Optional[EventSink] = None,
    ) -> None:
        # Config must not be mutated; store references only
        if not isinstance(config, RuntimeConfig):
            raise ValueError(_FAILURE_INVALID_CONFIG)

        self._config: RuntimeConfig = config
        # Deepcopy overrides to ensure we don't mutate caller/state
        self._overrides: Optional[Dict[str, Any]] = copy.deepcopy(overrides) if overrides is not None else None
        self._builder = builder
        self._application_status = application_status
        self._clock: Clock = clock or RealClock()
        self._event_sink: EventSink = event_sink or InMemoryEventSink(clock=self._clock)

        # Runtime state
        self._state: RuntimeState = "created"
        self._container: Optional[ApplicationContainer] = None
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._last_failure_code: Optional[str] = None
        self._warnings: List[str] = []

        # Started components tracking (only those started by this RuntimeService)
        self._started_background_worker: bool = False
        self._started_autonomous_controller: bool = False
        self._started_private_admin_api: bool = False

        # Concurrency control
        self._lock = RLock()
        self._state_cv = Condition(self._lock)

        # Emit created event (safe)
        self._emit_event(
            _EVENT_RUNTIME_CREATED,
            {
                "state": self._state,
                "environment_name": _safe_getattr(config.application_config, "environment_name"),
                "project_id": _safe_getattr(config.application_config, "default_project_id"),
            },
        )

    # ===== Public API =====

    def start(self) -> Dict[str, Any]:
        # Validate and change state to starting atomically
        with self._lock:
            if self._state == "running":
                return self.runtime_status()
            if self._state == "starting":
                # Wait briefly for ongoing start to complete
                self._wait_for_state_change_unlocked(targets=["running", "failed", "stopped"], timeout=2.0)
                return self.runtime_status()
            if self._state not in ("created", "stopped"):
                self._last_failure_code = _FAILURE_INVALID_TRANSITION
                self._emit_event(_EVENT_RUNTIME_OPERATION_FAILED, {"operation": "start", "failure_code": self._last_failure_code, "state": self._state})
                return self.runtime_status()

            self._state = "starting"
            self._warnings.clear()
            self._emit_event(
                _EVENT_RUNTIME_STARTING,
                {
                    "state": self._state,
                    "environment_name": _safe_getattr(self._config.application_config, "environment_name"),
                    "project_id": _safe_getattr(self._config.application_config, "default_project_id"),
                },
            )
            self._state_cv.notify_all()

        built_container: Optional[ApplicationContainer] = None
        try:
            # Build outside of lock to avoid deadlocks
            built_container = self._builder(self._config.application_config, copy.deepcopy(self._overrides))
            # Validate application is ready
            status = self._application_status(built_container)
            ready = False
            warnings: List[str] = []
            if isinstance(status, dict):
                ready = bool(status.get("ready", False))
                if isinstance(status.get("warnings"), list):
                    warnings = [str(w) for w in status.get("warnings", [])]
            else:
                # Try attribute access
                ready = bool(getattr(status, "ready", False))
                _w = getattr(status, "warnings", None)
                if isinstance(_w, list):
                    warnings = [str(w) for w in _w]

            if not ready:
                # Application not ready; cleanup and fail
                try:
                    built_container.close()
                except Exception:
                    # Swallow; do not leak raw exceptions
                    pass
                with self._lock:
                    self._container = None
                    self._state = "failed"
                    self._last_failure_code = _FAILURE_APP_NOT_READY
                    self._warnings = warnings[:]
                    self._state_cv.notify_all()
                self._emit_event(_EVENT_RUNTIME_START_FAILED, {"failure_code": self._last_failure_code, "state": self._state})
                return self.runtime_status()

            # Success path: set running and store container
            with self._lock:
                self._container = built_container
                self._state = "running"
                self._started_at = self._clock.now()
                self._stopped_at = None
                self._last_failure_code = None
                if warnings:
                    self._warnings = warnings[:]
                self._state_cv.notify_all()

            self._emit_event(
                _EVENT_RUNTIME_STARTED,
                {
                    "state": "running",
                    "environment_name": _safe_getattr(self._config.application_config, "environment_name"),
                    "project_id": _safe_getattr(self._config.application_config, "default_project_id"),
                },
            )

            # Auto-start explicitly configured components (do not hold lock during starts)
            if self._config.auto_start_private_admin_api:
                self.start_private_admin_api()
            if self._config.auto_start_autonomous_controller:
                self.start_autonomous_controller()
            if self._config.auto_start_background_worker:
                self.start_background_worker()

            return self.runtime_status()

        except Exception:
            # Safe failure; attempt to cleanup partial container
            if built_container is not None:
                try:
                    built_container.close()
                except Exception:
                    pass
            with self._lock:
                self._container = None
                self._state = "failed"
                self._last_failure_code = _FAILURE_START_FAILED
                self._state_cv.notify_all()
            self._emit_event(_EVENT_RUNTIME_START_FAILED, {"failure_code": self._last_failure_code, "state": self._state})
            return self.runtime_status()

    def stop(self) -> Dict[str, Any]:
        # Transition to stopping if allowed
        with self._lock:
            if self._state in ("created", "stopped"):
                return self.runtime_status()
            if self._state == "stopping":
                self._wait_for_state_change_unlocked(targets=["stopped"], timeout=2.0)
                return self.runtime_status()
            if self._state not in ("running", "failed"):
                self._last_failure_code = _FAILURE_INVALID_TRANSITION
                self._emit_event(_EVENT_RUNTIME_OPERATION_FAILED, {"operation": "stop", "failure_code": self._last_failure_code, "state": self._state})
                return self.runtime_status()

            self._state = "stopping"
            self._emit_event(_EVENT_RUNTIME_STOPPING, {"state": self._state})
            container = self._container
            # Capture which components were started by this runtime
            bw_to_stop = self._started_background_worker
            ac_to_stop = self._started_autonomous_controller
            pa_to_stop = self._started_private_admin_api

            self._state_cv.notify_all()

        # Stop components in reverse order, only those started by this service
        failure_code: Optional[str] = None
        if container is not None:
            # Private Admin API
            if pa_to_stop and _hasattr(container, "private_admin_api"):
                try:
                    self._emit_event(_EVENT_COMPONENT_STOPPING, {"component": "private_admin_api"})
                    container.private_admin_api.stop()  # type: ignore[attr-defined]
                    self._emit_event(_EVENT_COMPONENT_STOPPED, {"component": "private_admin_api"})
                except Exception:
                    failure_code = failure_code or _FAILURE_COMPONENT_STOP_FAILED
                    self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": "private_admin_api", "failure_code": _FAILURE_COMPONENT_STOP_FAILED})

            # Autonomous Controller
            if ac_to_stop and _hasattr(container, "autonomous_controller"):
                try:
                    self._emit_event(_EVENT_COMPONENT_STOPPING, {"component": "autonomous_controller"})
                    container.autonomous_controller.stop()  # type: ignore[attr-defined]
                    self._emit_event(_EVENT_COMPONENT_STOPPED, {"component": "autonomous_controller"})
                except Exception:
                    failure_code = failure_code or _FAILURE_COMPONENT_STOP_FAILED
                    self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": "autonomous_controller", "failure_code": _FAILURE_COMPONENT_STOP_FAILED})

            # Background Worker
            if bw_to_stop and _hasattr(container, "background_worker"):
                try:
                    self._emit_event(_EVENT_COMPONENT_STOPPING, {"component": "background_worker"})
                    container.background_worker.stop()  # type: ignore[attr-defined]
                    self._emit_event(_EVENT_COMPONENT_STOPPED, {"component": "background_worker"})
                except Exception:
                    failure_code = failure_code or _FAILURE_COMPONENT_STOP_FAILED
                    self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": "background_worker", "failure_code": _FAILURE_COMPONENT_STOP_FAILED})

            # Close the container
            try:
                container.close()
            except Exception:
                failure_code = failure_code or _FAILURE_STOP_FAILED

        with self._lock:
            # Clear container and flags
            self._container = None
            self._started_background_worker = False
            self._started_autonomous_controller = False
            self._started_private_admin_api = False
            self._stopped_at = self._clock.now()
            self._state = "stopped"
            self._last_failure_code = failure_code
            self._state_cv.notify_all()

        self._emit_event(_EVENT_RUNTIME_STOPPED, {"state": "stopped"})
        return self.runtime_status()

    def close(self) -> None:
        # Safe, idempotent stop
        try:
            self.stop()
        except Exception:
            # Do not raise raw exceptions from cleanup
            pass

    # Context manager support
    def __enter__(self) -> "RuntimeService":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # Component activation methods
    def start_background_worker(self) -> Dict[str, Any]:
        return self._start_component(
            name="background_worker",
            attr_name="background_worker",
            flag_name="_started_background_worker",
        )

    def stop_background_worker(self) -> Dict[str, Any]:
        return self._stop_component(
            name="background_worker",
            attr_name="background_worker",
            flag_name="_started_background_worker",
        )

    def start_autonomous_controller(self) -> Dict[str, Any]:
        return self._start_component(
            name="autonomous_controller",
            attr_name="autonomous_controller",
            flag_name="_started_autonomous_controller",
        )

    def stop_autonomous_controller(self) -> Dict[str, Any]:
        return self._stop_component(
            name="autonomous_controller",
            attr_name="autonomous_controller",
            flag_name="_started_autonomous_controller",
        )

    def start_private_admin_api(self) -> Dict[str, Any]:
        return self._start_component(
            name="private_admin_api",
            attr_name="private_admin_api",
            flag_name="_started_private_admin_api",
        )

    def stop_private_admin_api(self) -> Dict[str, Any]:
        return self._stop_component(
            name="private_admin_api",
            attr_name="private_admin_api",
            flag_name="_started_private_admin_api",
        )

    # Request processing
    def submit_request(self, request: Any) -> Any:
        with self._lock:
            if self._state != "running" or self._container is None:
                self._emit_event(_EVENT_REQUEST_REJECTED, {"reason": _FAILURE_NOT_RUNNING})
                return {
                    "accepted": False,
                    "failure_code": _FAILURE_NOT_RUNNING,
                    "blocked_reason": _FAILURE_NOT_RUNNING,
                }
            container = self._container

        try:
            result = container.request_flow.submit(request)
            self._emit_event(_EVENT_REQUEST_SUBMITTED, {"state": "running"})
            return result
        except Exception:
            self._emit_event(_EVENT_REQUEST_REJECTED, {"reason": _FAILURE_DEPENDENCY_FAILED})
            return {
                "accepted": False,
                "failure_code": _FAILURE_DEPENDENCY_FAILED,
                "blocked_reason": _FAILURE_DEPENDENCY_FAILED,
            }

    def process_execution_outcome(self, outcome: Any) -> Any:
        with self._lock:
            if self._state != "running" or self._container is None:
                self._emit_event(_EVENT_RUNTIME_OPERATION_FAILED, {"operation": "process_execution_outcome", "failure_code": _FAILURE_NOT_RUNNING})
                return {
                    "processed": False,
                    "failure_code": _FAILURE_NOT_RUNNING,
                    "blocked_reason": _FAILURE_NOT_RUNNING,
                }
            container = self._container

        try:
            result = container.execution_outcome_coordinator.process(outcome)
            self._emit_event(_EVENT_OUTCOME_PROCESSED, {"state": "running"})
            return result
        except Exception:
            self._emit_event(_EVENT_RUNTIME_OPERATION_FAILED, {"operation": "process_execution_outcome", "failure_code": _FAILURE_DEPENDENCY_FAILED})
            return {
                "processed": False,
                "failure_code": _FAILURE_DEPENDENCY_FAILED,
                "blocked_reason": _FAILURE_DEPENDENCY_FAILED,
            }

    # Status and events
    def runtime_status(self) -> Dict[str, Any]:
        with self._lock:
            container_present = self._container is not None
            app_ready = False
            # Only report ready if running and container present
            if container_present and self._state == "running":
                app_ready = True

            status = {
                "state": self._state,
                "environment_name": _safe_getattr(self._config.application_config, "environment_name"),
                "default_project_id": _safe_getattr(self._config.application_config, "default_project_id"),
                "application_ready": app_ready,
                "container_present": container_present,
                "background_worker_running": bool(self._started_background_worker),
                "autonomous_controller_running": bool(self._started_autonomous_controller),
                "private_admin_api_running": bool(self._started_private_admin_api),
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
                "last_failure_code": self._last_failure_code,
                "warnings": list(self._warnings),
            }
            return status

    def latest_events(self, limit: int) -> List[Dict[str, Any]]:
        # If event sink supports latest(), use it; otherwise, no events available
        if isinstance(self._event_sink, InMemoryEventSink):
            return self._event_sink.latest(limit)
        # Fallback: cannot retrieve from external sink; return empty
        return []

    # ===== Internal helpers =====

    def _start_component(self, *, name: str, attr_name: str, flag_name: str) -> Dict[str, Any]:
        with self._lock:
            if self._state != "running" or self._container is None:
                self._last_failure_code = _FAILURE_NOT_RUNNING
                self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": name, "failure_code": _FAILURE_NOT_RUNNING})
                return self.runtime_status()

            already_started: bool = getattr(self, flag_name)
            if already_started:
                return self.runtime_status()

            component = getattr(self._container, attr_name, None)
            if component is None:
                # No such component available in container
                self._last_failure_code = _FAILURE_COMPONENT_START_FAILED
                self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": name, "failure_code": _FAILURE_COMPONENT_START_FAILED})
                return self.runtime_status()

        try:
            self._emit_event(_EVENT_COMPONENT_STARTING, {"component": name})
            component.start()
            self._emit_event(_EVENT_COMPONENT_STARTED, {"component": name})
            with self._lock:
                setattr(self, flag_name, True)
                # Clear last failure when successful component start
                if self._last_failure_code in (_FAILURE_COMPONENT_START_FAILED, _FAILURE_NOT_RUNNING):
                    self._last_failure_code = None
            return self.runtime_status()
        except Exception:
            with self._lock:
                self._last_failure_code = _FAILURE_COMPONENT_START_FAILED
            self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": name, "failure_code": _FAILURE_COMPONENT_START_FAILED})
            return self.runtime_status()

    def _stop_component(self, *, name: str, attr_name: str, flag_name: str) -> Dict[str, Any]:
        with self._lock:
            # Idempotent if not running or not started by this runtime
            if not getattr(self, flag_name, False):
                return self.runtime_status()
            container = self._container
            component = getattr(container, attr_name, None) if container is not None else None

        if component is None:
            # Consider it stopped if container missing
            with self._lock:
                setattr(self, flag_name, False)
            return self.runtime_status()

        try:
            self._emit_event(_EVENT_COMPONENT_STOPPING, {"component": name})
            component.stop()
            self._emit_event(_EVENT_COMPONENT_STOPPED, {"component": name})
            with self._lock:
                setattr(self, flag_name, False)
                if self._last_failure_code == _FAILURE_COMPONENT_STOP_FAILED:
                    self._last_failure_code = None
            return self.runtime_status()
        except Exception:
            with self._lock:
                self._last_failure_code = _FAILURE_COMPONENT_STOP_FAILED
            self._emit_event(_EVENT_COMPONENT_START_FAILED, {"component": name, "failure_code": _FAILURE_COMPONENT_STOP_FAILED})
            return self.runtime_status()

    def _emit_event(self, event_type: str, fields: Dict[str, Any]) -> None:
        # Redact and keep only safe fields; include type and timestamp
        safe_event: Dict[str, Any] = {"type": event_type}
        # Allowed safe additions
        for k in ("state", "component", "operation", "failure_code", "environment_name", "project_id", "reason"):
            if k in fields and fields[k] is not None:
                safe_event[k] = fields[k]
        # Timestamp added by sink if missing
        try:
            self._event_sink.emit(safe_event)
        except Exception:
            # Swallow sink errors; do not fail runtime flow
            pass

    def _wait_for_state_change_unlocked(self, *, targets: List[RuntimeState], timeout: float) -> None:
        # Assumes self._lock is held by caller
        end = self._clock.now().timestamp() + max(0.0, timeout)
        while self._state not in targets and self._clock.now().timestamp() < end:
            remaining = end - self._clock.now().timestamp()
            if remaining <= 0:
                break
            self._state_cv.wait(timeout=remaining)


# ===== Helper functions =====

def _safe_getattr(obj: Any, name: str) -> Optional[str]:
    try:
        val = getattr(obj, name, None)
        if val is None:
            return None
        # Ensure we never return unsafe structured secrets; cast to str safely
        return str(val)
    except Exception:
        return None


def _hasattr(obj: Any, name: str) -> bool:
    try:
        getattr(obj, name)
        return True
    except Exception:
        return False


# ===== Public factory and helpers =====

def build_runtime(
    config: RuntimeConfig,
    overrides: Optional[Dict[str, Any]] = None,
    *,
    builder: Callable[[Any, Optional[Dict[str, Any]]], ApplicationContainer],
    application_status: Callable[[ApplicationContainer], ApplicationStatus],
    clock: Optional[Clock] = None,
    event_sink: Optional[EventSink] = None,
) -> RuntimeService:
    return RuntimeService(
        config,
        builder=builder,
        application_status=application_status,
        overrides=overrides,
        clock=clock,
        event_sink=event_sink,
    )


def runtime_status(runtime: RuntimeService) -> Dict[str, Any]:
    return runtime.runtime_status()
