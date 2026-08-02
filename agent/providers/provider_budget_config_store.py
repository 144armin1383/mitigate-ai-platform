from __future__ import annotations

import errno
import io
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

__all__ = [
    "ProviderBudgetConfigStore",
    "StorageCorruptionError",
]


class StorageCorruptionError(RuntimeError):
    """Raised when on-disk storage is corrupted or not trustworthy."""


# ----------------------------
# Cross-platform file locking
# ----------------------------
class _FileLock:
    """Cross-platform advisory file lock with bounded timeout.

    - Uses fcntl.flock on POSIX.
    - Uses msvcrt.locking on Windows.
    - Non-reentrant per-process per instance.
    - Locks a dedicated lock file; callers should use a single lock instance
      for the entire store to avoid nested locking.
    """

    def __init__(self, lock_path: str, timeout: float = 5.0) -> None:
        self._lock_path = lock_path
        self._timeout = float(timeout)
        self._fh: Optional[io.TextIOBase] = None
        self._owner_thread: Optional[int] = None

    def acquire(self) -> None:
        if self._owner_thread is not None:
            raise RuntimeError("_FileLock is non-reentrant")

        # Ensure directory exists
        base_dir = os.path.dirname(os.path.abspath(self._lock_path))
        os.makedirs(base_dir, exist_ok=True)

        start = time.monotonic()
        # Open in append+ so file persists; permission 0o600-like behavior inherited by OS umask
        fh = open(self._lock_path, mode="a+")
        self._fh = fh
        acquired = False
        try:
            while True:
                try:
                    self._platform_lock(fh)
                    acquired = True
                    self._owner_thread = threading.get_ident()
                    return
                except OSError:
                    if (time.monotonic() - start) >= self._timeout:
                        raise TimeoutError("Timed out acquiring file lock")
                    time.sleep(0.01)
        finally:
            if not acquired:
                try:
                    fh.close()
                except Exception:
                    pass
                self._fh = None

    def release(self) -> None:
        if self._owner_thread != threading.get_ident():
            raise RuntimeError("Lock not held by current thread")
        assert self._fh is not None
        try:
            self._platform_unlock(self._fh)
        finally:
            try:
                self._fh.close()
            finally:
                self._fh = None
                self._owner_thread = None

    def __enter__(self) -> "_FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    # Platform-specific helpers
    if os.name == "nt":  # pragma: no cover - behavior validated via logic, OS-specific path not required by CI
        import msvcrt as _msvcrt  # type: ignore

        def _platform_lock(self, fh: io.TextIOBase) -> None:  # type: ignore[override]
            # Lock 1 byte at start of file exclusively
            self._msvcrt.locking(fh.fileno(), self._msvcrt.LK_NBLCK, 1)

        def _platform_unlock(self, fh: io.TextIOBase) -> None:  # type: ignore[override]
            self._msvcrt.locking(fh.fileno(), self._msvcrt.LK_UNLCK, 1)

    else:
        import fcntl as _fcntl  # type: ignore

        def _platform_lock(self, fh: io.TextIOBase) -> None:  # type: ignore[override]
            self._fcntl.flock(fh.fileno(), self._fcntl.LOCK_EX | self._fcntl.LOCK_NB)

        def _platform_unlock(self, fh: io.TextIOBase) -> None:  # type: ignore[override]
            self._fcntl.flock(fh.fileno(), self._fcntl.LOCK_UN)


# ----------------------------
# Provider Budget Config Store
# ----------------------------
class ProviderBudgetConfigStore:
    """Persistent, deterministic, provider-neutral budget configuration store.

    Persistence layout (within base_dir):
      - provider_budgets.json: mapping project_id -> configuration dict
      - provider_budget_events.json: list of event dicts
      - provider_budgets.lock: advisory lock for atomic operations

    Deterministic JSON serialization is enforced (sorted keys, compact separators, ASCII).
    """

    CONFIG_FILENAME = "provider_budgets.json"
    EVENTS_FILENAME = "provider_budget_events.json"
    LOCK_FILENAME = "provider_budgets.lock"

    # Allowed values
    _POLICY_VALUES = {"allow", "warn", "block"}

    # Config field set (canonical order for validation; serialization is sorted by key for determinism)
    _CONFIG_FIELDS = (
        "project_id",
        "enabled",
        "daily_budget",
        "monthly_budget",
        "per_request_budget",
        "daily_token_limit",
        "monthly_token_limit",
        "per_request_input_token_limit",
        "per_request_output_token_limit",
        "soft_warning_percent",
        "hard_limit_enabled",
        "currency",
        "unknown_pricing_policy",
        "created_at",
        "updated_at",
    )

    # Input fields users may set when creating/updating (timestamps are managed by the store)
    _INPUT_ALLOWED_FIELDS = {
        "enabled",
        "daily_budget",
        "monthly_budget",
        "per_request_budget",
        "daily_token_limit",
        "monthly_token_limit",
        "per_request_input_token_limit",
        "per_request_output_token_limit",
        "soft_warning_percent",
        "hard_limit_enabled",
        "currency",
        "unknown_pricing_policy",
    }

    def __init__(
        self,
        base_dir: str,
        project_resolver: Any,
        *,
        clock: Optional[Callable[[], datetime]] = None,
        lock_timeout: float = 5.0,
    ) -> None:
        # Resolve and secure base directory
        real_base = os.path.realpath(os.path.abspath(base_dir))
        if os.path.islink(real_base):
            raise ValueError("Base directory must not be a symbolic link")
        os.makedirs(real_base, exist_ok=True)
        self._base_dir = real_base

        self._project_resolver = project_resolver
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = _FileLock(self._safe_join(self.LOCK_FILENAME), timeout=lock_timeout)

        self._config_path = self._safe_join(self.CONFIG_FILENAME)
        self._events_path = self._safe_join(self.EVENTS_FILENAME)

        # Load existing or initialize storage, validating correctness
        with self._lock:
            self._configs, self._events, self._last_event_id = self._load_state()

    # ----------------------------
    # Public API
    # ----------------------------
    def configure_budget(self, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        self._require_known_project(project_id)
        self._reject_unknown_fields(config)
        with self._lock:
            self._reload_if_changed()
            if project_id in self._configs:
                raise ValueError(f"Configuration already exists for project_id '{project_id}'")
            prepared = self._prepare_config(project_id, config, creating=True)
            self._configs[project_id] = prepared
            self._append_event(
                "budget_configured",
                project_id,
                details={"configured_fields": sorted(list(config.keys()))},
            )
            self._save_state()
            return self._copy_config(prepared)

    def update_budget(self, project_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        self._require_known_project(project_id)
        self._reject_unknown_fields(changes)
        if not changes:
            raise ValueError("No changes provided")
        with self._lock:
            self._reload_if_changed()
            if project_id not in self._configs:
                raise KeyError(f"No configuration found for project_id '{project_id}'")
            current = dict(self._configs[project_id])
            updated = self._prepare_config(project_id, changes, creating=False, base=current)
            self._configs[project_id] = updated
            self._append_event(
                "budget_updated",
                project_id,
                details={"updated_fields": sorted(list(changes.keys()))},
            )
            self._save_state()
            return self._copy_config(updated)

    def get_budget(self, project_id: str) -> Dict[str, Any]:
        self._require_known_project(project_id)
        with self._lock:
            self._reload_if_changed()
            if project_id not in self._configs:
                raise KeyError(f"No configuration found for project_id '{project_id}'")
            return self._copy_config(self._configs[project_id])

    def remove_budget(self, project_id: str) -> bool:
        self._require_known_project(project_id)
        with self._lock:
            self._reload_if_changed()
            if project_id in self._configs:
                del self._configs[project_id]
                self._append_event("budget_removed", project_id, details={})
                self._save_state()
                return True
            return False

    def list_budgets(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._reload_if_changed()
            # Deterministic: sort by project_id
            return [self._copy_config(self._configs[pid]) for pid in sorted(self._configs.keys())]

    def status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            self._reload_if_changed()
            if project_id is not None:
                configured = project_id in self._configs
                last_updated = self._configs[project_id]["updated_at"] if configured else None
                return {
                    "project_id": project_id,
                    "configured": configured,
                    "last_updated": last_updated,
                    "last_event_id": self._last_event_id,
                }
            return {
                "projects": len(self._configs),
                "events": len(self._events),
                "last_event_id": self._last_event_id,
            }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            self._reload_if_changed()
            items = self._events
            if project_id is not None:
                items = [e for e in items if e.get("project_id") == project_id]
            # Return newest first deterministically by id desc
            out = list(reversed(items[-limit:]))
            return [json.loads(json.dumps(e, sort_keys=True)) for e in out]

    # ----------------------------
    # Internal helpers
    # ----------------------------
    def _now_str(self) -> str:
        dt = self._clock()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        # Use ISO 8601 with Zulu suffix, include microseconds for ordering
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def _require_known_project(self, project_id: str) -> None:
        if not self._is_known_project(project_id):
            raise PermissionError(f"Unknown project_id '{project_id}'")

    def _is_known_project(self, project_id: str) -> bool:
        pr = self._project_resolver
        try:
            if callable(pr):
                return bool(pr(project_id))
            if hasattr(pr, "is_valid") and callable(getattr(pr, "is_valid")):
                return bool(pr.is_valid(project_id))  # type: ignore[attr-defined]
            if hasattr(pr, "exists") and callable(getattr(pr, "exists")):
                return bool(pr.exists(project_id))  # type: ignore[attr-defined]
        except Exception:
            return False
        raise ValueError("Invalid project_resolver: must be callable or provide is_valid/exists")

    def _reject_unknown_fields(self, data: Dict[str, Any]) -> None:
        for k in data.keys():
            if k not in self._INPUT_ALLOWED_FIELDS and k not in ("project_id", "created_at", "updated_at"):
                # Explicitly reject unknown user-provided fields
                raise ValueError(f"Unknown field '{k}' in configuration")
        if "project_id" in data or "created_at" in data or "updated_at" in data:
            # These are managed by the store; reject user attempts to set
            raise ValueError("Fields 'project_id', 'created_at', and 'updated_at' are managed by the store")

    def _prepare_config(
        self,
        project_id: str,
        incoming: Dict[str, Any],
        *,
        creating: bool,
        base: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Start from base or empty with defaults as None
        dest: Dict[str, Any] = {} if base is None else dict(base)

        # Apply incoming validated values
        for key, value in incoming.items():
            self._validate_field_value(key, value)
            dest[key] = value

        # Ensure required invariant fields
        dest["project_id"] = project_id

        # Validate presence of minimally necessary fields when creating
        required_when_creating = [
            "enabled",
            "currency",
            "unknown_pricing_policy",
        ]
        if creating:
            for req in required_when_creating:
                if req not in dest:
                    raise ValueError(f"Missing required field '{req}' for new configuration")

        # Defaults for unspecified optional fields to None
        optional_numerics = [
            "daily_budget",
            "monthly_budget",
            "per_request_budget",
            "daily_token_limit",
            "monthly_token_limit",
            "per_request_input_token_limit",
            "per_request_output_token_limit",
            "soft_warning_percent",
        ]
        for f in optional_numerics:
            if f not in dest:
                dest[f] = None

        if "hard_limit_enabled" not in dest:
            dest["hard_limit_enabled"] = False

        # Final validation of the assembled record
        self._validate_complete_config(dest)

        # Timestamps
        now = self._now_str()
        if creating:
            dest["created_at"] = now
        dest["updated_at"] = now

        # Return canonical dict with only allowed fields
        canonical: Dict[str, Any] = {}
        for k in self._CONFIG_FIELDS:
            if k in dest:
                canonical[k] = dest[k]
            else:
                # created_at/updated_at will be set; ensure present even in base merge
                canonical[k] = None
        return canonical

    def _validate_field_value(self, key: str, value: Any) -> None:
        if key not in self._INPUT_ALLOWED_FIELDS:
            raise ValueError(f"Unknown field '{key}' in configuration")
        if key in {"daily_budget", "monthly_budget", "per_request_budget"}:
            self._validate_monetary(value, key)
        elif key in {
            "daily_token_limit",
            "monthly_token_limit",
            "per_request_input_token_limit",
            "per_request_output_token_limit",
        }:
            self._validate_token_limit(value, key)
        elif key == "soft_warning_percent":
            self._validate_soft_warning(value)
        elif key == "hard_limit_enabled":
            if type(value) is not bool:
                raise ValueError("hard_limit_enabled must be a boolean")
        elif key == "currency":
            self._validate_currency(value)
        elif key == "enabled":
            if type(value) is not bool:
                raise ValueError("enabled must be a boolean")
        elif key == "unknown_pricing_policy":
            if not isinstance(value, str) or value not in self._POLICY_VALUES:
                raise ValueError("unknown_pricing_policy must be one of: allow, warn, block")
        else:
            # Should not happen due to allowed fields gating
            raise ValueError(f"Unsupported field '{key}'")

    @staticmethod
    def _is_number(x: Any) -> bool:
        # Exclude booleans (subclass of int)
        return (isinstance(x, (int, float)) and type(x) is not bool)

    def _validate_monetary(self, value: Any, field: str) -> None:
        if value is None:
            return
        if not self._is_number(value):
            raise ValueError(f"{field} must be a non-negative number or null")
        if value < 0:
            raise ValueError(f"{field} must be a non-negative number or null")

    def _validate_token_limit(self, value: Any, field: str) -> None:
        if value is None:
            return
        if type(value) is bool or not isinstance(value, int):
            raise ValueError(f"{field} must be a non-negative integer or null")
        if value < 0:
            raise ValueError(f"{field} must be a non-negative integer or null")

    def _validate_soft_warning(self, value: Any) -> None:
        if value is None:
            return
        if not self._is_number(value):
            raise ValueError("soft_warning_percent must be a number between 0 and 100 or null")
        if not (0 <= value <= 100):
            raise ValueError("soft_warning_percent must be between 0 and 100")

    @staticmethod
    def _validate_currency(value: Any) -> None:
        if not isinstance(value, str) or len(value) != 3 or not value.isalpha() or value.upper() != value:
            raise ValueError("currency must be a three-letter uppercase code")

    def _validate_complete_config(self, cfg: Dict[str, Any]) -> None:
        # project_id consistency
        if not isinstance(cfg.get("project_id"), str) or not cfg["project_id"]:
            raise ValueError("project_id must be a non-empty string")
        # Validate all present values via field validators
        for k, v in cfg.items():
            if k in self._INPUT_ALLOWED_FIELDS:
                self._validate_field_value(k, v)
        # Policy check
        pol = cfg.get("unknown_pricing_policy")
        if pol not in self._POLICY_VALUES:
            raise ValueError("unknown_pricing_policy must be one of: allow, warn, block")
        # Currency format already validated when present

    # ----------------------------
    # Persistence helpers
    # ----------------------------
    def _safe_join(self, filename: str) -> str:
        # Prevent path traversal and symlink escape
        candidate = os.path.realpath(os.path.join(self._base_dir, filename))
        if not candidate.startswith(self._base_dir + os.sep) and candidate != self._base_dir:
            raise ValueError("Unsafe file path resolution attempted")
        return candidate

    def _atomic_write(self, path: str, data: str) -> None:
        directory = os.path.dirname(path)
        base = os.path.basename(path)
        tmp_name = f".{base}.tmp-{os.getpid()}-{int(time.time()*1e6)}"
        tmp_path = os.path.join(directory, tmp_name)
        # Use os.open to ensure no following of symlinks on creation when supported (no O_NOFOLLOW portable)
        # We'll still verify the final target is not a symlink before replace.
        fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="ascii", newline="\n") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            # Ensure target is not a symlink; if it is, raise
            if os.path.islink(path):
                raise StorageCorruptionError("Target path is a symbolic link")
            # Replace atomically
            os.replace(tmp_path, path)
            # fsync directory to ensure durability
            dfd = os.open(directory, os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    def _json_dumps(self, obj: Any) -> str:
        # Deterministic serialization: ASCII, sorted keys, compact separators
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _load_state(self) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], int]:
        # Clean up safe temp files (leftovers) quietly
        self._cleanup_temp_files()
        configs: Dict[str, Dict[str, Any]] = {}
        events: List[Dict[str, Any]] = []
        last_event_id = 0

        if os.path.exists(self._config_path):
            if os.path.islink(self._config_path):
                raise StorageCorruptionError("Config path is a symbolic link")
            try:
                with open(self._config_path, "r", encoding="ascii") as f:
                    data = json.load(f)
            except Exception as e:
                raise StorageCorruptionError(f"Failed to load configurations: {e}") from e
            if not isinstance(data, dict):
                raise StorageCorruptionError("Configurations file must contain an object")
            # Validate structure and values
            for pid, cfg in data.items():
                if not isinstance(pid, str) or not isinstance(cfg, dict):
                    raise StorageCorruptionError("Invalid configuration entry structure")
                # basic validation of fields and values
                try:
                    # Accept only known fields, reject extras
                    unknowns = set(cfg.keys()) - set(self._CONFIG_FIELDS)
                    if unknowns:
                        raise StorageCorruptionError(f"Unknown fields in stored configuration: {unknowns}")
                    self._validate_complete_config(cfg)
                except Exception as e:
                    raise StorageCorruptionError(f"Invalid configuration for project '{pid}': {e}") from e
                configs[pid] = cfg

        if os.path.exists(self._events_path):
            if os.path.islink(self._events_path):
                raise StorageCorruptionError("Events path is a symbolic link")
            try:
                with open(self._events_path, "r", encoding="ascii") as f:
                    ev = json.load(f)
            except Exception as e:
                raise StorageCorruptionError(f"Failed to load events: {e}") from e
            if not isinstance(ev, list):
                raise StorageCorruptionError("Events file must contain a list")
            # Validate events are safe and well-formed
            for item in ev:
                if not isinstance(item, dict):
                    raise StorageCorruptionError("Invalid event entry")
                if not {"id", "type", "project_id", "timestamp", "details"}.issubset(item.keys()):
                    raise StorageCorruptionError("Event missing required fields")
                if not isinstance(item.get("id"), int) or item["id"] <= 0:
                    raise StorageCorruptionError("Invalid event id")
                if not isinstance(item.get("project_id"), str):
                    raise StorageCorruptionError("Invalid event project_id")
                if item.get("type") not in {"budget_configured", "budget_updated", "budget_removed"}:
                    raise StorageCorruptionError("Invalid event type")
                if not isinstance(item.get("details"), dict):
                    raise StorageCorruptionError("Invalid event details")
                # Ensure details do not contain values that could be secrets (just names expected)
                for k, v in item["details"].items():
                    if not isinstance(k, str):
                        raise StorageCorruptionError("Invalid event detail key type")
                    if k.endswith("_fields") and not (
                        isinstance(v, list) and all(isinstance(x, str) for x in v)
                    ):
                        raise StorageCorruptionError("Invalid event detail structure")
                events.append(item)
                if item["id"] > last_event_id:
                    last_event_id = item["id"]

        return configs, events, last_event_id

    def _save_state(self) -> None:
        # Deterministic order: sort configs by project_id
        ordered_configs: Dict[str, Dict[str, Any]] = {k: self._configs[k] for k in sorted(self._configs.keys())}
        cfg_data = self._json_dumps(ordered_configs)
        ev_data = self._json_dumps(self._events)
        self._atomic_write(self._config_path, cfg_data)
        self._atomic_write(self._events_path, ev_data)

    def _append_event(self, etype: str, project_id: str, *, details: Dict[str, Any]) -> None:
        self._last_event_id += 1
        event = {
            "id": self._last_event_id,
            "type": etype,
            "project_id": project_id,
            "timestamp": self._now_str(),
            "details": details,
        }
        self._events.append(event)

    def _reload_if_changed(self) -> None:
        # For single-process test usage it's generally unchanged; still, implement simple reload semantics.
        # If files are missing, treat as empty (first-time init) and write on save.
        # If files changed externally, reload state safely.
        # We will simply re-load fully; corruption will raise immediately.
        self._configs, self._events, self._last_event_id = self._load_state()

    def _cleanup_temp_files(self) -> None:
        # Remove safe temporary files created by _atomic_write if left behind from a crash
        directory = self._base_dir
        for name in os.listdir(directory):
            if not isinstance(name, str):
                continue
            # Accept only our expected temp naming for these two files
            if name.startswith("." + self.CONFIG_FILENAME + ".tmp-") or name.startswith(
                "." + self.EVENTS_FILENAME + ".tmp-"
            ):
                path = os.path.join(directory, name)
                try:
                    if os.path.isfile(path) and os.path.realpath(os.path.dirname(path)) == self._base_dir:
                        os.unlink(path)
                except Exception:
                    # Best-effort cleanup; ignore failures
                    pass

    @staticmethod
    def _copy_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
        return json.loads(json.dumps(cfg, sort_keys=True))
