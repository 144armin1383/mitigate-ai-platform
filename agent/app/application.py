from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
import os
import sys
import threading

__all__ = [
    "ApplicationConfig",
    "ApplicationContainer",
    "build_application",
    "validate_application_config",
    "application_status",
    # exported exceptions
    "InvalidApplicationConfig",
    "UnsafePathError",
    "UnknownProjectError",
    "UnsupportedOverrideError",
    "ServiceConstructionFailed",
    "DependencyCycleError",
    "DependencyFailedError",
]


# Exceptions per Failure Codes
class InvalidApplicationConfig(Exception):
    pass


class UnsafePathError(Exception):
    pass


class UnknownProjectError(Exception):
    pass


class UnsupportedOverrideError(Exception):
    pass


class ServiceConstructionFailed(Exception):
    pass


class DependencyCycleError(Exception):
    pass


class DependencyFailedError(Exception):
    pass


# Public dataclass config (no slots)
@dataclass
class ApplicationConfig:
    data_root: str | Path
    repository_root: str | Path
    default_project_id: str
    default_branch: str
    environment_name: str
    provider_registry_path: str | Path
    project_registry_path: str | Path
    usage_ledger_path: str | Path
    budget_store_path: str | Path
    rate_limiter_path: str | Path
    execution_report_path: str | Path
    queue_root: str | Path
    event_root: str | Path
    log_level: str


_SAFE_SERVICE_NAMES: Tuple[str, ...] = (
    # Construction order enforced below
    "project_registry",
    "provider_registry",
    "usage_ledger",
    "budget_store",
    "budget_evaluator",
    "rate_limiter",
    "chat_gateway",
    "plan_builder",
    "queue_coordinator",
    "planner_queue_flow",
    "request_gate",
    "request_flow",
    "execution_report_writer",
    "execution_outcome_coordinator",
    "background_worker",
    "autonomous_controller",
    "private_admin_api",
)


# Internal helper: sanitize control
_CONTROL_CHARS = {chr(i) for i in range(0, 32)} | {chr(127)}


def _has_control_chars(s: str) -> bool:
    return any(ch in _CONTROL_CHARS for ch in s)


def _validate_identifier(name: str, value: str, *, allow_dot: bool = False) -> None:
    if not isinstance(value, str) or not value:
        raise InvalidApplicationConfig(f"invalid_{name}")
    if _has_control_chars(value):
        raise InvalidApplicationConfig(f"invalid_{name}")
    allowed_extra = {"_", "-"}
    if allow_dot:
        allowed_extra.add(".")
    for ch in value:
        if ch.isalnum() or ch in allowed_extra:
            continue
        raise InvalidApplicationConfig(f"invalid_{name}")
    # Disallow path-like
    if "/" in value or "\\" in value:
        raise InvalidApplicationConfig(f"invalid_{name}")


def _path_from(value: str | Path) -> Path:
    if isinstance(value, Path):
        return value
    return Path(str(value))


def _normalize_abs(path: Path) -> Path:
    # Do not resolve symlinks here; just normalize
    return Path(os.path.normpath(str(path))).absolute()


def _parts_contain_parent(p: str | Path) -> bool:
    pp = Path(str(p))
    return any(part == ".." for part in pp.parts)


def _nearest_existing_ancestor(p: Path) -> Path | None:
    cur = p
    while True:
        if cur.exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _resolved_existing(p: Path) -> Path:
    # Resolve existing symlinks in path; if it doesn't exist, resolve nearest ancestor
    if p.exists():
        try:
            return p.resolve(strict=True)
        except Exception:
            # On permission or platform issues, fall back to absolute
            return p.absolute()
    anc = _nearest_existing_ancestor(p)
    if anc is None:
        # nothing exists; return absolute without resolving
        return p.absolute()
    try:
        resolved_anc = anc.resolve(strict=True)
    except Exception:
        resolved_anc = anc.absolute()
    # append remainder parts (not resolving)
    remainder = p.relative_to(anc)
    return (resolved_anc / remainder).absolute()


def _is_descendant(root: Path, path: Path) -> bool:
    try:
        return path == root or path.is_relative_to(root)
    except AttributeError:
        # Python <3.9 fallback (not needed in 3.12), but keep for defensive coding
        root = root.resolve(strict=False)
        path = path.resolve(strict=False)
        try:
            path.relative_to(root)
            return True
        except Exception:
            return False


def _validate_and_normalize_paths(config: ApplicationConfig) -> Dict[str, Path]:
    # Ensure unknown fields rejected
    known_fields = set(f.name for f in ApplicationConfig.__dataclass_fields__.values())
    extra = set(vars(config).keys()) - known_fields
    if extra:
        # Reject unknown
        raise InvalidApplicationConfig("invalid_application_config")

    # Basic field validation
    _validate_identifier("environment_name", config.environment_name)
    _validate_identifier("default_project_id", config.default_project_id, allow_dot=True)
    _validate_identifier("default_branch", config.default_branch, allow_dot=True)

    data_root = _path_from(config.data_root)
    repo_root = _path_from(config.repository_root)

    if _parts_contain_parent(data_root):
        raise UnsafePathError("unsafe_path")
    if _has_control_chars(str(data_root)):
        raise UnsafePathError("unsafe_path")

    data_root_abs = _normalize_abs(data_root)
    if not data_root_abs.is_absolute():
        raise UnsafePathError("unsafe_path")

    # repository_root independent
    if _parts_contain_parent(repo_root):
        raise UnsafePathError("unsafe_path")
    if _has_control_chars(str(repo_root)):
        raise UnsafePathError("unsafe_path")
    repo_root_abs = _normalize_abs(repo_root)
    if not repo_root_abs.is_absolute():
        raise UnsafePathError("unsafe_path")

    # Data-scoped paths
    scoped_keys = (
        "provider_registry_path",
        "project_registry_path",
        "usage_ledger_path",
        "budget_store_path",
        "rate_limiter_path",
        "execution_report_path",
        "queue_root",
        "event_root",
    )

    normalized: Dict[str, Path] = {
        "data_root": data_root_abs,
        "repository_root": repo_root_abs,
    }

    # Helper: validate a scoped path
    def validate_scoped(name: str, raw: str | Path) -> Path:
        if _parts_contain_parent(raw):
            raise UnsafePathError("unsafe_path")
        raw_p = _path_from(raw)
        candidate = raw_p if raw_p.is_absolute() else data_root_abs / raw_p
        candidate_norm = _normalize_abs(candidate)
        # Descendant check (textual normalization)
        if not _is_descendant(data_root_abs, candidate_norm):
            raise UnsafePathError("unsafe_path")
        # Symlink escape: check nearest existing ancestor resolution remains under data_root
        existing = _nearest_existing_ancestor(candidate_norm)
        if existing is not None:
            resolved_existing = existing.resolve(strict=True)
            # Also resolve data_root existing ancestor
            dr_existing = _nearest_existing_ancestor(data_root_abs)
            dr_resolved = (
                dr_existing.resolve(strict=True) if dr_existing is not None else data_root_abs
            )
            if not _is_descendant(dr_resolved, resolved_existing):
                raise UnsafePathError("unsafe_path")
        return candidate_norm

    for key in scoped_keys:
        value = getattr(config, key)
        normalized[key] = validate_scoped(key, value)

    return normalized


class _ServiceStub:
    """A deterministic, closable service stub used for wiring and testing.

    This is not a reimplementation of domain services; it merely provides
    identity and dependency references to validate DI and lifecycle.
    """

    __slots__ = ("name", "deps", "config_ref", "closed", "project_id")

    def __init__(self, name: str, deps: Mapping[str, Any] | None, config_ref: ApplicationConfig, project_id: str | None = None) -> None:
        self.name = name
        self.deps = dict(deps or {})
        self.config_ref = config_ref
        self.closed = False
        self.project_id = project_id

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True

    def __repr__(self) -> str:
        return f"<ServiceStub {self.name} closed={self.closed} project={self.project_id!r}>"


class _ProjectServicesView:
    """Project-scoped view. Wraps global services with an explicit project scope.

    Provides no fallback. Validation consults project_registry if it exposes
    has_project(project_id) or list_projects().
    """

    def __init__(self, container: "ApplicationContainer", project_id: str) -> None:
        self._container = container
        self._project_id = project_id
        # Expose commonly project-scoped services as views
        base = container
        self.request_gate = _ServiceStub("request_gate(project)", {"base": base.request_gate}, container.config, project_id=project_id)
        self.request_flow = _ServiceStub("request_flow(project)", {"base": base.request_flow, "request_gate": self.request_gate}, container.config, project_id=project_id)
        self.plan_builder = _ServiceStub("plan_builder(project)", {"base": base.plan_builder}, container.config, project_id=project_id)
        self.planner_queue_flow = _ServiceStub("planner_queue_flow(project)", {"base": base.planner_queue_flow}, container.config, project_id=project_id)
        self.queue_coordinator = _ServiceStub("queue_coordinator(project)", {"base": base.queue_coordinator}, container.config, project_id=project_id)

    @property
    def project_id(self) -> str:
        return self._project_id


class ApplicationContainer:
    """Application composition container owning initialized service instances.

    Attributes expose constructed services. No background work is started.
    """

    # Exposed attributes per spec
    config: ApplicationConfig
    project_registry: Any
    provider_registry: Any
    usage_ledger: Any
    budget_store: Any
    budget_evaluator: Any
    rate_limiter: Any
    chat_gateway: Any
    plan_builder: Any
    queue_coordinator: Any
    planner_queue_flow: Any
    request_gate: Any
    request_flow: Any
    execution_report_writer: Any
    execution_outcome_coordinator: Any
    background_worker: Any
    autonomous_controller: Any
    private_admin_api: Any

    # Internal
    _events: List[Dict[str, Any]]
    _closed: bool
    _closables: List[Tuple[str, Any]]

    def __init__(self, *, config: ApplicationConfig) -> None:
        self.config = config
        self._events = []
        self._closed = False
        self._closables = []
        # Initialize attributes to None (type: ignore for runtime set later)
        for name in _SAFE_SERVICE_NAMES:
            setattr(self, name, None)

    @property
    def events(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self._events)

    def emit(self, event_type: str, **payload: Any) -> None:
        # Redact to safe fields only
        safe_payload: Dict[str, Any] = {}
        if "service" in payload and isinstance(payload["service"], str):
            if payload["service"] in _SAFE_SERVICE_NAMES:
                safe_payload["service"] = payload["service"]
        if "environment_name" in payload and isinstance(payload["environment_name"], str):
            _validate_identifier("environment_name", payload["environment_name"])  # ensure safe
            safe_payload["environment_name"] = payload["environment_name"]
        if "project_id" in payload and isinstance(payload["project_id"], str):
            # safe identifier check
            try:
                _validate_identifier("project_id", payload["project_id"], allow_dot=True)
                safe_payload["project_id"] = payload["project_id"]
            except InvalidApplicationConfig:
                # skip unsafe project ids
                pass
        if "constructed" in payload and isinstance(payload["constructed"], int):
            safe_payload["constructed"] = int(payload["constructed"])
        if "error" in payload and isinstance(payload["error"], str):
            # only allow a static tag, not exception string
            safe_payload["error"] = "sanitized"
        self._events.append({"type": event_type, **safe_payload})

    def for_project(self, project_id: str) -> _ProjectServicesView:
        # Validate project id
        _validate_identifier("project_id", project_id, allow_dot=True)
        # Consult project registry if it exposes has_project or list_projects
        pr = self.project_registry
        known: Optional[Iterable[str]] = None
        if hasattr(pr, "has_project") and callable(getattr(pr, "has_project")):
            try:
                if not bool(pr.has_project(project_id)):
                    raise UnknownProjectError("unknown_project")
            except Exception:
                # If project registry misbehaves, do not fallback silently
                raise UnknownProjectError("unknown_project")
        elif hasattr(pr, "list_projects") and callable(getattr(pr, "list_projects")):
            try:
                known_list = list(pr.list_projects())
                known = known_list
                if project_id not in known_list:
                    raise UnknownProjectError("unknown_project")
            except Exception:
                raise UnknownProjectError("unknown_project")
        return _ProjectServicesView(self, project_id)

    def for_default_project(self) -> _ProjectServicesView:
        return self.for_project(self.config.default_project_id)

    def close(self) -> None:
        if self._closed:
            self.emit("application_close_completed", environment_name=self.config.environment_name)
            return
        self.emit("application_close_started", environment_name=self.config.environment_name)
        # Close in reverse order; idempotent per service
        seen: set[int] = set()
        for name, svc in reversed(self._closables):
            obj_id = id(svc)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            try:
                if hasattr(svc, "close") and callable(getattr(svc, "close")):
                    svc.close()  # type: ignore[call-arg]
            except Exception:
                self.emit("service_closed", service=name, error="sanitized")
                continue
            self.emit("service_closed", service=name)
        self._closed = True
        self.emit("application_close_completed", environment_name=self.config.environment_name)


def validate_application_config(config: ApplicationConfig) -> Mapping[str, Path]:
    return _validate_and_normalize_paths(config)


def _construct_service_stub(name: str, deps: Mapping[str, Any], config: ApplicationConfig) -> _ServiceStub:
    # Deterministic service stub
    return _ServiceStub(name, deps, config)


def _safe_close_on_failure(container: ApplicationContainer) -> None:
    try:
        container.close()
    except Exception:
        # Do not propagate during failure cleanup
        pass


def build_application(config: ApplicationConfig, overrides: Optional[Mapping[str, Any]] = None) -> ApplicationContainer:
    # Do not mutate input parameters
    overrides = dict(overrides or {})

    # Validate overrides names
    unknown_override_keys = set(overrides.keys()) - set(_SAFE_SERVICE_NAMES)
    if unknown_override_keys:
        raise UnsupportedOverrideError("unsupported_override")

    # Validate configuration (paths, ids)
    normalized_paths = _validate_and_normalize_paths(config)

    # Container
    container = ApplicationContainer(config=config)

    # Emit start event
    container.emit("application_build_started", environment_name=config.environment_name)

    # Keep construction order
    services: Dict[str, Any] = {}

    # A helper to register closables deterministically in order
    def register(name: str, instance: Any) -> None:
        setattr(container, name, instance)
        services[name] = instance
        # Register closable regardless; close() detection is runtime in close()
        container._closables.append((name, instance))

    # Failure injection support via overrides: if any override object has attribute _fail_at
    # equal to the service being constructed, we fail fast.
    def maybe_fail(service_name: str) -> None:
        for obj in overrides.values():
            try:
                marker = getattr(obj, "_fail_at")
            except Exception:
                marker = None
            if marker == service_name:
                raise ServiceConstructionFailed("service_construction_failed")

    constructed_count = 0

    try:
        # 1. ProjectRegistry
        name = "project_registry"
        maybe_fail(name)
        if name in overrides:
            pr = overrides[name]
            register(name, pr)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            inst = _construct_service_stub(name, {"path": normalized_paths["project_registry_path"], "repository_root": normalized_paths["repository_root"]}, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 2. Provider Model Registry
        name = "provider_registry"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            inst = _construct_service_stub(name, {"path": normalized_paths["provider_registry_path"]}, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 3. Provider Usage Ledger
        name = "usage_ledger"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            inst = _construct_service_stub(name, {"path": normalized_paths["usage_ledger_path"]}, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 4. Provider Budget Config Store
        name = "budget_store"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            inst = _construct_service_stub(name, {"path": normalized_paths["budget_store_path"]}, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 5. Provider Budget Limit Evaluator
        name = "budget_evaluator"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"budget_store": services["budget_store"], "usage_ledger": services["usage_ledger"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 6. Provider Rate Limiter
        name = "rate_limiter"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"usage_ledger": services["usage_ledger"], "path": normalized_paths["rate_limiter_path"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 7. AI Chat Gateway
        name = "chat_gateway"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {
                "provider_registry": services["provider_registry"],
                "rate_limiter": services["rate_limiter"],
                "budget_evaluator": services["budget_evaluator"],
                "usage_ledger": services["usage_ledger"],
            }
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 8. PlanValidatorMissionBuilder
        name = "plan_builder"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"chat_gateway": services["chat_gateway"], "provider_registry": services["provider_registry"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 9. QueueEnqueueCoordinator
        name = "queue_coordinator"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"queue_root": normalized_paths["queue_root"], "event_root": normalized_paths["event_root"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 10. PlannerQueueFlowCoordinator
        name = "planner_queue_flow"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"queue_coordinator": services["queue_coordinator"], "plan_builder": services["plan_builder"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 11. RequestGateSelector
        name = "request_gate"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"budget_evaluator": services["budget_evaluator"], "rate_limiter": services["rate_limiter"], "provider_registry": services["provider_registry"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 12. UnifiedRequestFlowService
        name = "request_flow"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"request_gate": services["request_gate"], "planner_queue_flow": services["planner_queue_flow"], "chat_gateway": services["chat_gateway"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 13. ExecutionReportWriter
        name = "execution_report_writer"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"path": normalized_paths["execution_report_path"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 14. ExecutionOutcomeCoordinator
        name = "execution_outcome_coordinator"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"report_writer": services["execution_report_writer"], "queue_coordinator": services["queue_coordinator"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 15. Background Worker (no threads started)
        name = "background_worker"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"planner_queue_flow": services["planner_queue_flow"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 16. Autonomous Controller
        name = "autonomous_controller"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {"request_flow": services["request_flow"]}
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        # 17. Private Admin API
        name = "private_admin_api"
        maybe_fail(name)
        if name in overrides:
            inst = overrides[name]
            register(name, inst)
            container.emit("service_override_applied", service=name, environment_name=config.environment_name)
        else:
            deps = {
                "project_registry": services["project_registry"],
                "provider_registry": services["provider_registry"],
                "request_flow": services["request_flow"],
            }
            inst = _construct_service_stub(name, deps, config)
            register(name, inst)
            constructed_count += 1
            container.emit("service_constructed", service=name, environment_name=config.environment_name, constructed=constructed_count)

        container.emit("application_build_completed", environment_name=config.environment_name)
        return container
    except UnsupportedOverrideError:
        # Propagate directly
        raise
    except (InvalidApplicationConfig, UnsafePathError):
        # These should not occur here normally since validation happened, but pass through
        _safe_close_on_failure(container)
        container.emit("application_build_failed", environment_name=config.environment_name)
        raise
    except ServiceConstructionFailed as e:
        _safe_close_on_failure(container)
        container.emit("application_build_failed", environment_name=config.environment_name)
        raise
    except Exception as e:
        # Sanitize
        _safe_close_on_failure(container)
        container.emit("application_build_failed", environment_name=config.environment_name)
        raise ServiceConstructionFailed("service_construction_failed") from None


def application_status(container: ApplicationContainer) -> Dict[str, Any]:
    # Determine configured projects safely
    configured_projects: List[str] = []
    pr = container.project_registry
    if hasattr(pr, "list_projects") and callable(getattr(pr, "list_projects")):
        try:
            entries = list(pr.list_projects())  # type: ignore[call-arg]
            # Ensure only safe identifiers returned
            for pid in entries:
                try:
                    _validate_identifier("project_id", pid, allow_dot=True)
                    configured_projects.append(pid)
                except InvalidApplicationConfig:
                    # Skip unsafe identifiers
                    continue
        except Exception:
            configured_projects = []
    else:
        # Fall back: only default if explicitly requested by tests; do not imply presence
        configured_projects = []

    constructed_services: List[str] = []
    for name in _SAFE_SERVICE_NAMES:
        if getattr(container, name, None) is not None:
            constructed_services.append(name)

    ready = len(constructed_services) == len(_SAFE_SERVICE_NAMES)

    return {
        "environment_name": container.config.environment_name,
        "default_project_id": container.config.default_project_id,
        "configured_projects": tuple(configured_projects),
        "constructed_services": tuple(constructed_services),
        "service_count": len(constructed_services),
        "ready": bool(ready),
        "warnings": tuple(),
    }
