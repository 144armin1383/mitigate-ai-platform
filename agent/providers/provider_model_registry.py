from __future__ import annotations

import json
import os
import time
import errno
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple, TypedDict

# Exceptions


class RegistryError(Exception):
    pass


class RegistryValidationError(RegistryError):
    pass


class RegistryNotFoundError(RegistryError):
    pass


class RegistryCorruptionError(RegistryError):
    pass


# Dependency Injection Protocols


class SecretStore(Protocol):
    def has_reference(self, reference: str) -> bool:  # nosec - only checks presence
        ...


class ProjectResolver(Protocol):
    def is_known_project(self, project_id: str) -> bool:
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        ...


class IdGenerator(Protocol):
    def new_id(self, kind: str) -> str:
        ...


class ProviderAdapter(Protocol):
    def list_models(self, provider_config: Dict[str, Any]) -> Sequence[Dict[str, Any]]:
        """
        Return a sequence of model metadata dicts with stable fields:
        - model_id: str
        - display_name: str
        - capabilities: List[str]
        - context_window: int
        - maximum_output_tokens: int
        - supports_text: bool
        - supports_vision: bool
        - supports_tools: bool
        - supports_json: bool
        - supports_reasoning: bool
        - supports_streaming: bool
        Note: Must not access or return any secret values.
        """
        ...

    def test_connectivity(self, provider_config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Return (ok, error_message). Must not expose secrets in error_message."""
        ...


# Constants and validation helpers

SUPPORTED_TASK_TYPES: Tuple[str, ...] = (
    "planning",
    "coding",
    "code_review",
    "validation",
    "vision",
    "chat",
    "summarization",
    "fast_tasks",
    "fallback",
)

# tasks that require tool use support
TOOL_REQUIRED_TASKS: Tuple[str, ...] = ("coding", "code_review", "validation")

# Providers allowed identifiers are provider-neutral. Additional providers allowed without code changes.
PROVIDER_ID_PATTERN_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_-.")
MODEL_ID_PATTERN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:/")
SECRET_REF_PATTERN_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-/")


def _validate_identifier(value: str, allowed: set[str], field: str) -> None:
    if not value or any(ch not in allowed for ch in value):
        raise RegistryValidationError(f"Invalid {field} '{value}'")


def _validate_secret_reference(ref: Optional[str], field: str) -> None:
    if ref is None:
        raise RegistryValidationError(f"Missing {field}")
    if not ref or any(ch not in SECRET_REF_PATTERN_CHARS for ch in ref):
        raise RegistryValidationError(f"Invalid {field}")


# Storage with locking and atomic writes


class _FileLock:
    def __init__(self, path: Path, timeout: float = 2.0):
        self.path = path
        self.timeout = timeout
        self._fd: Optional[int] = None

    def __enter__(self) -> "_FileLock":
        start = time.time()
        flags = os.O_CREAT | os.O_RDWR
        while True:
            try:
                self._fd = os.open(self.path, flags, 0o600)
                break
            except OSError as e:
                if e.errno != errno.EINTR:
                    raise
        # Try to acquire an exclusive lock using fcntl or msvcrt
        acquired = False
        while not acquired:
            try:
                try:
                    import fcntl  # type: ignore

                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except ImportError:
                    import msvcrt  # type: ignore

                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError as e:  # pragma: no cover (windows-only)
                        if e.winerror not in (33,):  # lock violation
                            raise
                if acquired:
                    return self
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
            if time.time() - start > self.timeout:
                raise TimeoutError("Timed out acquiring registry lock")
            time.sleep(0.01)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            try:
                try:
                    import fcntl  # type: ignore

                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                except ImportError:
                    import msvcrt  # type: ignore

                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)  # pragma: no cover
                    except OSError:
                        pass
            finally:
                os.close(self._fd)
                self._fd = None


class _AtomicJSONStore:
    def __init__(self, base_dir: Path, filename: str = "provider_registry.json", lock_filename: str = ".provider_registry.lock"):
        self.base_dir = base_dir
        self.filename = filename
        self.filepath = (base_dir / filename).resolve()
        self.lockpath = (base_dir / lock_filename).resolve()
        # Ensure base_dir exists and is not a symlink pointed elsewhere (best effort)
        base_dir.mkdir(parents=True, exist_ok=True)
        if os.path.islink(self.filepath):
            raise RegistryValidationError("Registry path must not be a symlink")
        if os.path.islink(self.lockpath):
            raise RegistryValidationError("Registry lock path must not be a symlink")

    def load(self) -> Dict[str, Any]:
        with _FileLock(self.lockpath):
            if not self.filepath.exists():
                return {}
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                raise RegistryCorruptionError(f"Corrupted registry JSON: {e}")
            if not isinstance(data, dict):
                raise RegistryCorruptionError("Registry JSON root must be an object")
            return data

    def save(self, data: Dict[str, Any]) -> None:
        # Deterministic serialization
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        with _FileLock(self.lockpath):
            tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self.base_dir), prefix=".registry.", suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                    tmp.write(payload)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_path, self.filepath)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass


# Data types for internal state


@dataclass(frozen=True)
class ProviderState:
    provider_id: str
    display_name: str
    enabled: bool
    credential_reference: str
    base_url_reference: Optional[str]
    organization_reference: Optional[str]
    project_reference: Optional[str]
    default_timeout_seconds: int
    maximum_retries: int
    created_at: str
    updated_at: str
    status: str  # active, disabled, degraded, unavailable


@dataclass(frozen=True)
class ModelState:
    model_id: str
    provider_id: str
    display_name: str
    enabled: bool
    capabilities: List[str]
    context_window: int
    maximum_output_tokens: int
    supports_text: bool
    supports_vision: bool
    supports_tools: bool
    supports_json: bool
    supports_reasoning: bool
    supports_streaming: bool
    input_cost_reference: Optional[str]
    output_cost_reference: Optional[str]
    created_at: str
    updated_at: str
    status: str  # available, disabled, unavailable, deprecated


@dataclass(frozen=True)
class AssignmentState:
    project_id: str
    task_type: str
    primary_provider_id: str
    primary_model_id: str
    fallback_chain: List[Dict[str, str]]
    maximum_input_tokens: int
    maximum_output_tokens: int
    timeout_seconds: int
    maximum_cost_per_request: Optional[float]
    reasoning_level: Optional[str]
    temperature: Optional[float]
    enabled: bool


@dataclass(frozen=True)
class EventState:
    id: str
    type: str
    at: str
    project_id: Optional[str]
    details: Dict[str, Any] = field(default_factory=dict)


# Provider Model Registry


class ProviderModelRegistry:
    def __init__(
        self,
        storage_dir: Path,
        *,
        secret_store: SecretStore,
        project_resolver: ProjectResolver,
        clock: Optional[Clock] = None,
        id_generator: Optional[IdGenerator] = None,
        provider_adapters: Optional[Dict[str, ProviderAdapter]] = None,
    ) -> None:
        self._store = _AtomicJSONStore(storage_dir)
        self._secret_store = secret_store
        self._project_resolver = project_resolver
        self._clock = clock or _SystemClock()
        self._idgen = id_generator or _SimpleIdGenerator()
        self._adapters = provider_adapters or {}
        self._state: Dict[str, Any] = {}
        self._load_or_initialize()

    # Public interface methods

    def create_provider(self, config: Dict[str, Any]) -> Dict[str, Any]:
        provider_id = config.get("provider_id")
        display_name = config.get("display_name") or provider_id
        enabled = bool(config.get("enabled", False))
        credential_reference = config.get("credential_reference")
        base_url_reference = config.get("base_url_reference")
        organization_reference = config.get("organization_reference")
        project_reference = config.get("project_reference")
        default_timeout_seconds = int(config.get("default_timeout_seconds", 60))
        maximum_retries = int(config.get("maximum_retries", 2))

        _validate_identifier(str(provider_id), PROVIDER_ID_PATTERN_CHARS, "provider_id")
        _validate_secret_reference(credential_reference, "credential_reference")
        if not self._secret_store.has_reference(credential_reference):
            raise RegistryValidationError("Credential reference is not configured in secret store")
        if base_url_reference is not None:
            _validate_secret_reference(base_url_reference, "base_url_reference")
        if organization_reference is not None:
            _validate_secret_reference(organization_reference, "organization_reference")
        if project_reference is not None:
            _validate_secret_reference(project_reference, "project_reference")

        providers = self._state["providers"]
        if any(p["provider_id"] == provider_id for p in providers):
            raise RegistryValidationError(f"Provider '{provider_id}' already exists")

        now = self._now_iso()
        status = "active" if enabled else "disabled"
        record = ProviderState(
            provider_id=provider_id,
            display_name=display_name,
            enabled=enabled,
            credential_reference=credential_reference,
            base_url_reference=base_url_reference,
            organization_reference=organization_reference,
            project_reference=project_reference,
            default_timeout_seconds=default_timeout_seconds,
            maximum_retries=maximum_retries,
            created_at=now,
            updated_at=now,
            status=status,
        )
        providers.append(_asdict(record))
        self._persist()
        self._emit_event("provider_created", None, {
            "provider_id": provider_id,
            "display_name": display_name,
            "credential_configured": True,
        })
        return self.get_provider(provider_id)

    def update_provider(self, provider_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        rec = self._get_provider_rec(provider_id)
        # Update allowed fields; never allow secrets values here, only references
        mutable = dict(rec)
        allowed_fields = {
            "display_name",
            "enabled",
            "credential_reference",
            "base_url_reference",
            "organization_reference",
            "project_reference",
            "default_timeout_seconds",
            "maximum_retries",
            "status",
        }
        for k, v in changes.items():
            if k not in allowed_fields:
                continue
            if k in ("credential_reference", "base_url_reference", "organization_reference", "project_reference"):
                if v is not None:
                    _validate_secret_reference(v, k)
                    if k == "credential_reference" and not self._secret_store.has_reference(v):
                        raise RegistryValidationError("Credential reference is not configured in secret store")
            if k == "enabled":
                v = bool(v)
                # Update status accordingly if not explicitly set
                if "status" not in changes:
                    mutable["status"] = "active" if v else "disabled"
            mutable[k] = v
        mutable["updated_at"] = self._now_iso()
        self._replace_provider(provider_id, mutable)
        self._persist()
        self._emit_event("provider_updated", None, {"provider_id": provider_id})
        return self.get_provider(provider_id)

    def enable_provider(self, provider_id: str) -> Dict[str, Any]:
        return self.update_provider(provider_id, {"enabled": True, "status": "active"})

    def disable_provider(self, provider_id: str) -> Dict[str, Any]:
        return self.update_provider(provider_id, {"enabled": False, "status": "disabled"})

    def get_provider(self, provider_id: str) -> Dict[str, Any]:
        rec = self._get_provider_rec(provider_id)
        return dict(rec)

    def list_providers(self) -> List[Dict[str, Any]]:
        providers = [dict(p) for p in self._state["providers"]]
        providers.sort(key=lambda p: p["provider_id"])  # deterministic order
        return providers

    def register_model(self, config: Dict[str, Any]) -> Dict[str, Any]:
        provider_id = config.get("provider_id")
        model_id = config.get("model_id")
        display_name = config.get("display_name") or model_id
        enabled = bool(config.get("enabled", False))
        capabilities: List[str] = list(config.get("capabilities", []))
        context_window = int(config.get("context_window", 0))
        maximum_output_tokens = int(config.get("maximum_output_tokens", 0))
        supports_text = bool(config.get("supports_text", True))
        supports_vision = bool(config.get("supports_vision", False))
        supports_tools = bool(config.get("supports_tools", False))
        supports_json = bool(config.get("supports_json", False))
        supports_reasoning = bool(config.get("supports_reasoning", False))
        supports_streaming = bool(config.get("supports_streaming", False))
        input_cost_reference = config.get("input_cost_reference")
        output_cost_reference = config.get("output_cost_reference")

        _validate_identifier(str(provider_id), PROVIDER_ID_PATTERN_CHARS, "provider_id")
        _validate_identifier(str(model_id), MODEL_ID_PATTERN_CHARS, "model_id")
        # Ensure provider exists
        _ = self._get_provider_rec(provider_id)

        models = self._state["models"]
        if any(m["model_id"] == model_id and m["provider_id"] == provider_id for m in models):
            raise RegistryValidationError(f"Model '{model_id}' already exists for provider '{provider_id}'")

        if input_cost_reference is not None:
            _validate_secret_reference(input_cost_reference, "input_cost_reference")
        if output_cost_reference is not None:
            _validate_secret_reference(output_cost_reference, "output_cost_reference")

        now = self._now_iso()
        status = "available" if enabled else "disabled"
        rec = ModelState(
            model_id=model_id,
            provider_id=provider_id,
            display_name=display_name,
            enabled=enabled,
            capabilities=capabilities,
            context_window=context_window,
            maximum_output_tokens=maximum_output_tokens,
            supports_text=supports_text,
            supports_vision=supports_vision,
            supports_tools=supports_tools,
            supports_json=supports_json,
            supports_reasoning=supports_reasoning,
            supports_streaming=supports_streaming,
            input_cost_reference=input_cost_reference,
            output_cost_reference=output_cost_reference,
            created_at=now,
            updated_at=now,
            status=status,
        )
        models.append(_asdict(rec))
        self._persist()
        self._emit_event("model_registered", None, {"provider_id": provider_id, "model_id": model_id})
        return self.get_model(provider_id, model_id)

    def update_model(self, provider_id: str, model_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        rec = self._get_model_rec(provider_id, model_id)
        mutable = dict(rec)
        allowed_fields = {
            "display_name",
            "enabled",
            "capabilities",
            "context_window",
            "maximum_output_tokens",
            "supports_text",
            "supports_vision",
            "supports_tools",
            "supports_json",
            "supports_reasoning",
            "supports_streaming",
            "input_cost_reference",
            "output_cost_reference",
            "status",
        }
        for k, v in changes.items():
            if k not in allowed_fields:
                continue
            if k in ("input_cost_reference", "output_cost_reference") and v is not None:
                _validate_secret_reference(v, k)
            if k == "enabled":
                v = bool(v)
                if "status" not in changes:
                    mutable["status"] = "available" if v else "disabled"
            mutable[k] = v
        mutable["updated_at"] = self._now_iso()
        self._replace_model(provider_id, model_id, mutable)
        self._persist()
        self._emit_event("model_updated", None, {"provider_id": provider_id, "model_id": model_id})
        return self.get_model(provider_id, model_id)

    def enable_model(self, provider_id: str, model_id: str) -> Dict[str, Any]:
        return self.update_model(provider_id, model_id, {"enabled": True, "status": "available"})

    def disable_model(self, provider_id: str, model_id: str) -> Dict[str, Any]:
        return self.update_model(provider_id, model_id, {"enabled": False, "status": "disabled"})

    def get_model(self, provider_id: str, model_id: str) -> Dict[str, Any]:
        rec = self._get_model_rec(provider_id, model_id)
        return dict(rec)

    def list_models(self, provider_id: Optional[str] = None) -> List[Dict[str, Any]]:
        models = self._state["models"]
        out = [dict(m) for m in models if provider_id is None or m["provider_id"] == provider_id]
        out.sort(key=lambda m: (m["provider_id"], m["model_id"]))
        return out

    def refresh_models(self, provider_id: str) -> Dict[str, Any]:
        provider = self._get_provider_rec(provider_id)
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            raise RegistryValidationError(f"No provider adapter configured for '{provider_id}'")
        # keep previous state in case of failure
        before_models = { (m["provider_id"], m["model_id"]): dict(m) for m in self._state["models"] if m["provider_id"] == provider_id }
        try:
            models_meta = adapter.list_models(provider)
        except Exception as e:  # do not expose secrets
            # Emit failure event, preserve previous registry
            self._emit_event("provider_health_failed", None, {"provider_id": provider_id, "error": str(e)[:200]})
            return {"provider_id": provider_id, "refreshed": False}
        # Update or register models accordingly, mark missing as deprecated
        seen_ids: set[str] = set()
        now = self._now_iso()
        for meta in models_meta:
            mid = str(meta.get("model_id"))
            _validate_identifier(mid, MODEL_ID_PATTERN_CHARS, "model_id")
            seen_ids.add(mid)
            exists = before_models.get((provider_id, mid))
            model_payload = {
                "provider_id": provider_id,
                "model_id": mid,
                "display_name": meta.get("display_name") or mid,
                "enabled": True if exists is None else bool(exists.get("enabled", True)),
                "capabilities": list(meta.get("capabilities", [])),
                "context_window": int(meta.get("context_window", 0)),
                "maximum_output_tokens": int(meta.get("maximum_output_tokens", 0)),
                "supports_text": bool(meta.get("supports_text", True)),
                "supports_vision": bool(meta.get("supports_vision", False)),
                "supports_tools": bool(meta.get("supports_tools", False)),
                "supports_json": bool(meta.get("supports_json", False)),
                "supports_reasoning": bool(meta.get("supports_reasoning", False)),
                "supports_streaming": bool(meta.get("supports_streaming", False)),
                "input_cost_reference": exists.get("input_cost_reference") if exists else None,
                "output_cost_reference": exists.get("output_cost_reference") if exists else None,
                "status": "available",
            }
            if exists is None:
                # new model
                model_payload["created_at"] = now
            else:
                model_payload["created_at"] = exists.get("created_at", now)
            model_payload["updated_at"] = now
            if exists is None:
                self._state["models"].append(model_payload)
            else:
                self._replace_model(provider_id, mid, model_payload)
        # Mark missing as deprecated, do not delete
        for (pid, mid), rec in before_models.items():
            if mid not in seen_ids:
                if rec.get("status") != "deprecated":
                    rec2 = dict(rec)
                    rec2["status"] = "deprecated"
                    rec2["enabled"] = rec2.get("enabled", False)
                    rec2["updated_at"] = now
                    self._replace_model(provider_id, mid, rec2)
                    self._emit_event("model_deprecated", None, {"provider_id": provider_id, "model_id": mid})
        self._persist()
        self._emit_event("models_refreshed", None, {"provider_id": provider_id, "count": len(models_meta)})
        return {"provider_id": provider_id, "refreshed": True, "count": len(models_meta)}

    def test_provider(self, provider_id: str) -> Dict[str, Any]:
        provider = self._get_provider_rec(provider_id)
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            # If no adapter, cannot test; mark unavailable
            self.update_provider(provider_id, {"status": "degraded"})
            self._emit_event("provider_health_failed", None, {"provider_id": provider_id, "error": "no_adapter"})
            return {"provider_id": provider_id, "ok": False, "error": "no_adapter"}
        ok, err = adapter.test_connectivity(provider)
        if ok:
            self.update_provider(provider_id, {"status": "active"})
            self._emit_event("provider_health_succeeded", None, {"provider_id": provider_id})
            return {"provider_id": provider_id, "ok": True}
        else:
            # Do not expose secret values; err must already be redacted by adapter
            self.update_provider(provider_id, {"status": "degraded"})
            self._emit_event("provider_health_failed", None, {"provider_id": provider_id, "error": err or "failed"})
            return {"provider_id": provider_id, "ok": False, "error": err or "failed"}

    def assign_model(self, project_id: str, task_type: str, assignment: Dict[str, Any]) -> Dict[str, Any]:
        self._assert_project(project_id)
        self._assert_task_type(task_type)
        primary_provider_id = assignment.get("primary_provider_id")
        primary_model_id = assignment.get("primary_model_id")
        fallback_chain = list(assignment.get("fallback_chain", []))

        # validate provider-model ownership
        _ = self._get_model_rec(primary_provider_id, primary_model_id)
        # Validate fallback chain: list of {provider_id, model_id}
        seen: set[Tuple[str, str]] = set()
        for idx, entry in enumerate(fallback_chain):
            pid = entry.get("provider_id")
            mid = entry.get("model_id")
            if not pid or not mid:
                raise RegistryValidationError("Invalid fallback entry")
            _ = self._get_model_rec(pid, mid)
            key = (pid, mid)
            if key in seen:
                raise RegistryValidationError("Duplicate in fallback chain")
            seen.add(key)
        if (primary_provider_id, primary_model_id) in seen:
            raise RegistryValidationError("Fallback chain must not contain the primary model")

        maximum_input_tokens = int(assignment.get("maximum_input_tokens", 0))
        maximum_output_tokens = int(assignment.get("maximum_output_tokens", 0))
        timeout_seconds = int(assignment.get("timeout_seconds", 60))
        maximum_cost_per_request = assignment.get("maximum_cost_per_request")
        reasoning_level = assignment.get("reasoning_level")
        temperature = assignment.get("temperature")
        enabled = bool(assignment.get("enabled", True))

        rec = AssignmentState(
            project_id=project_id,
            task_type=task_type,
            primary_provider_id=primary_provider_id,
            primary_model_id=primary_model_id,
            fallback_chain=[{"provider_id": e["provider_id"], "model_id": e["model_id"]} for e in fallback_chain],
            maximum_input_tokens=maximum_input_tokens,
            maximum_output_tokens=maximum_output_tokens,
            timeout_seconds=timeout_seconds,
            maximum_cost_per_request=maximum_cost_per_request,
            reasoning_level=reasoning_level,
            temperature=temperature,
            enabled=enabled,
        )
        # Upsert by project_id + task_type
        key = (project_id, task_type)
        existing = self._find_assignment(project_id, task_type)
        if existing is None:
            self._state["assignments"].append(_asdict(rec))
            self._persist()
            self._emit_event("assignment_created", project_id, {"task_type": task_type})
        else:
            self._replace_assignment(project_id, task_type, _asdict(rec))
            self._persist()
            self._emit_event("assignment_updated", project_id, {"task_type": task_type})
        return self.get_assignment(project_id, task_type)

    def remove_assignment(self, project_id: str, task_type: str) -> None:
        self._assert_project(project_id)
        self._assert_task_type(task_type)
        idx = self._find_assignment_index(project_id, task_type)
        if idx is None:
            return
        del self._state["assignments"][idx]
        self._persist()
        self._emit_event("assignment_removed", project_id, {"task_type": task_type})

    def get_assignment(self, project_id: str, task_type: str) -> Dict[str, Any]:
        self._assert_project(project_id)
        self._assert_task_type(task_type)
        a = self._find_assignment(project_id, task_type)
        if a is None:
            raise RegistryNotFoundError("Assignment not found")
        return dict(a)

    def list_assignments(self, project_id: str) -> List[Dict[str, Any]]:
        self._assert_project(project_id)
        out = [dict(a) for a in self._state["assignments"] if a["project_id"] == project_id]
        out.sort(key=lambda a: (a["project_id"], a["task_type"]))
        return out

    def select_model(self, project_id: str, task_type: str) -> Dict[str, Any]:
        self._assert_project(project_id)
        self._assert_task_type(task_type)
        try:
            a = self.get_assignment(project_id, task_type)
        except RegistryNotFoundError:
            return {"project_id": project_id, "task_type": task_type, "provider_id": None, "model_id": None, "source": "none"}
        # primary
        if self._is_model_selectable(a["primary_provider_id"], a["primary_model_id"], task_type):
            return {
                "project_id": project_id,
                "task_type": task_type,
                "provider_id": a["primary_provider_id"],
                "model_id": a["primary_model_id"],
                "source": "primary",
            }
        # fallbacks
        for entry in a["fallback_chain"]:
            pid = entry["provider_id"]
            mid = entry["model_id"]
            if (pid, mid) == (a["primary_provider_id"], a["primary_model_id"]):
                continue
            if self._is_model_selectable(pid, mid, task_type):
                self._emit_event("fallback_selected", project_id, {
                    "task_type": task_type,
                    "provider_id": pid,
                    "model_id": mid,
                })
                return {
                    "project_id": project_id,
                    "task_type": task_type,
                    "provider_id": pid,
                    "model_id": mid,
                    "source": "fallback",
                }
        return {"project_id": project_id, "task_type": task_type, "provider_id": None, "model_id": None, "source": "none"}

    def select_fallback(self, project_id: str, task_type: str, failed_provider_id: str, failed_model_id: str) -> Dict[str, Any]:
        self._assert_project(project_id)
        self._assert_task_type(task_type)
        try:
            a = self.get_assignment(project_id, task_type)
        except RegistryNotFoundError:
            return {"provider_id": None, "model_id": None, "source": "none"}
        tried = {(failed_provider_id, failed_model_id)}
        tried.add((a["primary_provider_id"], a["primary_model_id"]))
        for entry in a["fallback_chain"]:
            pid = entry["provider_id"]
            mid = entry["model_id"]
            if (pid, mid) in tried:
                continue
            if self._is_model_selectable(pid, mid, task_type):
                self._emit_event("fallback_selected", project_id, {
                    "task_type": task_type,
                    "provider_id": pid,
                    "model_id": mid,
                })
                return {"provider_id": pid, "model_id": mid, "source": "fallback"}
        return {"provider_id": None, "model_id": None, "source": "none"}

    def validate_assignment(self, project_id: str, task_type: str) -> Dict[str, Any]:
        self._assert_project(project_id)
        self._assert_task_type(task_type)
        issues: List[str] = []
        try:
            a = self.get_assignment(project_id, task_type)
        except RegistryNotFoundError:
            return {"ok": False, "issues": ["missing_assignment"]}
        # Validate primary ownership exists
        try:
            self._get_model_rec(a["primary_provider_id"], a["primary_model_id"]) 
        except RegistryNotFoundError:
            issues.append("primary_missing")
        # Fallback chain duplicates
        chain = [(e["provider_id"], e["model_id"]) for e in a["fallback_chain"]]
        if len(chain) != len(set(chain)):
            issues.append("fallback_duplicates")
        if (a["primary_provider_id"], a["primary_model_id"]) in set(chain):
            issues.append("fallback_contains_primary")
        ok = len(issues) == 0
        return {"ok": ok, "issues": issues}

    def get_active_configuration(self, project_id: str) -> Dict[str, Any]:
        self._assert_project(project_id)
        # Return a minimal active configuration for the project (assignments only)
        assignments = self.list_assignments(project_id)
        return {
            "project_id": project_id,
            "assignments": assignments,
        }

    def status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        providers = self.list_providers()
        models = self.list_models()
        if project_id is not None:
            self._assert_project(project_id)
        assignments = self._state["assignments"]
        if project_id is not None:
            assignments = [a for a in assignments if a["project_id"] == project_id]
        return {
            "providers": {
                "count": len(providers),
                "active": sum(1 for p in providers if p["enabled"] and p["status"] in ("active", "degraded")),
                "disabled": sum(1 for p in providers if not p["enabled"] or p["status"] == "disabled"),
            },
            "models": {
                "count": len(models),
                "available": sum(1 for m in models if m["enabled"] and m["status"] == "available"),
                "disabled": sum(1 for m in models if not m["enabled"] or m["status"] == "disabled"),
                "deprecated": sum(1 for m in models if m["status"] == "deprecated"),
            },
            "assignments": len(assignments),
        }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        events = self._state["events"]
        if project_id is not None:
            self._assert_project(project_id)
            events = [e for e in events if e.get("project_id") == project_id]
        # events are stored in chronological order; return last N
        return [dict(e) for e in events[-int(limit):]]

    # Internal helpers

    def _load_or_initialize(self) -> None:
        data = self._store.load()
        if not data:
            self._state = {
                "version": 1,
                "providers": [],
                "models": [],
                "assignments": [],
                "events": [],
            }
            self._persist()
            return
        # Validate structure minimally
        for required in ("version", "providers", "models", "assignments", "events"):
            if required not in data:
                raise RegistryCorruptionError(f"Missing '{required}' in registry")
        if not isinstance(data["providers"], list) or not isinstance(data["models"], list) or not isinstance(data["assignments"], list) or not isinstance(data["events"], list):
            raise RegistryCorruptionError("Registry lists are not arrays")
        # Assign deterministic ordering
        data["providers"].sort(key=lambda p: p.get("provider_id", ""))
        data["models"].sort(key=lambda m: (m.get("provider_id", ""), m.get("model_id", "")))
        data["assignments"].sort(key=lambda a: (a.get("project_id", ""), a.get("task_type", "")))
        data["events"].sort(key=lambda e: (e.get("at", ""), e.get("id", "")))
        self._state = data

    def _persist(self) -> None:
        # Prepare deterministic serialization by sorting lists
        state = {
            "version": 1,
            "providers": sorted([dict(p) for p in self._state["providers"]], key=lambda p: p["provider_id"]),
            "models": sorted([dict(m) for m in self._state["models"]], key=lambda m: (m["provider_id"], m["model_id"])) ,
            "assignments": sorted([dict(a) for a in self._state["assignments"]], key=lambda a: (a["project_id"], a["task_type"])) ,
            "events": sorted([dict(e) for e in self._state["events"]], key=lambda e: (e["at"], e["id"])) ,
        }
        self._store.save(state)
        # Update in-memory with what we wrote (sorted copies)
        self._state = state

    def _get_provider_rec(self, provider_id: str) -> Dict[str, Any]:
        for p in self._state["providers"]:
            if p["provider_id"] == provider_id:
                return p
        raise RegistryNotFoundError(f"Provider '{provider_id}' not found")

    def _replace_provider(self, provider_id: str, new_rec: Dict[str, Any]) -> None:
        for i, p in enumerate(self._state["providers"]):
            if p["provider_id"] == provider_id:
                self._state["providers"][i] = new_rec
                return
        raise RegistryNotFoundError(f"Provider '{provider_id}' not found")

    def _get_model_rec(self, provider_id: str, model_id: str) -> Dict[str, Any]:
        for m in self._state["models"]:
            if m["provider_id"] == provider_id and m["model_id"] == model_id:
                return m
        raise RegistryNotFoundError(f"Model '{model_id}' for provider '{provider_id}' not found")

    def _replace_model(self, provider_id: str, model_id: str, new_rec: Dict[str, Any]) -> None:
        for i, m in enumerate(self._state["models"]):
            if m["provider_id"] == provider_id and m["model_id"] == model_id:
                self._state["models"][i] = new_rec
                return
        # If not found, append (used during refresh new model)
        self._state["models"].append(new_rec)

    def _find_assignment(self, project_id: str, task_type: str) -> Optional[Dict[str, Any]]:
        for a in self._state["assignments"]:
            if a["project_id"] == project_id and a["task_type"] == task_type:
                return a
        return None

    def _find_assignment_index(self, project_id: str, task_type: str) -> Optional[int]:
        for i, a in enumerate(self._state["assignments"]):
            if a["project_id"] == project_id and a["task_type"] == task_type:
                return i
        return None

    def _replace_assignment(self, project_id: str, task_type: str, new_rec: Dict[str, Any]) -> None:
        idx = self._find_assignment_index(project_id, task_type)
        if idx is None:
            self._state["assignments"].append(new_rec)
        else:
            self._state["assignments"][idx] = new_rec

    def _assert_project(self, project_id: str) -> None:
        if not self._project_resolver.is_known_project(project_id):
            raise RegistryValidationError(f"Unknown project '{project_id}'")

    def _assert_task_type(self, task_type: str) -> None:
        if task_type not in SUPPORTED_TASK_TYPES:
            raise RegistryValidationError(f"Unknown task type '{task_type}'")

    def _is_model_selectable(self, provider_id: str, model_id: str, task_type: str) -> bool:
        try:
            provider = self._get_provider_rec(provider_id)
            model = self._get_model_rec(provider_id, model_id)
        except RegistryNotFoundError:
            return False
        # Provider must be enabled and not unavailable/disabled
        if not provider.get("enabled", False):
            return False
        if provider.get("status") in ("disabled", "unavailable"):
            return False
        # Model must be enabled and available
        if not model.get("enabled", False):
            return False
        if model.get("status") in ("disabled", "unavailable", "deprecated"):
            return False
        # Capability checks
        if task_type == "vision" and not model.get("supports_vision", False):
            return False
        if task_type in TOOL_REQUIRED_TASKS and not model.get("supports_tools", False):
            return False
        if task_type != "vision" and not model.get("supports_text", True):
            return False
        return True

    def _emit_event(self, etype: str, project_id: Optional[str], details: Dict[str, Any]) -> None:
        # Redact any sensitive fields from details if present
        sanitized = {}
        for k, v in details.items():
            if k in ("credential_reference", "authorization", "headers", "raw_response"):
                continue
            sanitized[k] = v
        evt = EventState(
            id=self._idgen.new_id("evt"),
            type=etype,
            at=self._now_iso(),
            project_id=project_id,
            details=sanitized,
        )
        self._state["events"].append(_asdict(evt))
        # Keep event list bounded in memory if desired; for now, persist all
        self._persist()

    def _now_iso(self) -> str:
        dt = self._clock.now()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()


# Utility implementations for defaults


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class _SimpleIdGenerator:
    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}

    def new_id(self, kind: str) -> str:
        n = self._counters.get(kind, 0) + 1
        self._counters[kind] = n
        return f"{kind}_{n:08d}"


# Helper to convert dataclass to dict without importing asdict to avoid recursive/complex handling

def _asdict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: getattr(obj, k) for k in obj.__dataclass_fields__.keys()}  # type: ignore[attr-defined]
    if isinstance(obj, dict):
        return dict(obj)
    raise TypeError("Unsupported type for _asdict")
