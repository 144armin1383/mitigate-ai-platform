from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Tuple, Union

try:
    import fcntl  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - on Windows
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - on POSIX
    msvcrt = None  # type: ignore[assignment]


# ---- Clock protocol for dependency injection ----
class Clock(Protocol):
    def now(self) -> datetime:  # must be timezone-aware UTC
        ...


class SystemUTCClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


# ---- Utilities ----
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _ensure_utc(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # Treat naive as UTC per contract of this implementation
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _isoformat(dt: datetime) -> str:
    dt = _ensure_utc(dt)
    # Use microseconds and Z suffix for determinism
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_isoformat(s: str) -> datetime:
    # Accept strictly the _isoformat format
    if not s.endswith("Z"):
        raise ValueError("timestamp must end with 'Z'")
    # Remove 'Z'
    base = s[:-1]
    # Expect microseconds always present
    dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    return dt


def _json_dumps(obj: Any) -> str:
    # Deterministic serialization
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class FileLock:
    """Cross-platform advisory file lock with bounded timeout.

    Creates/opens a lock file at the given path and acquires an exclusive lock.
    Not re-entrant. Intended for inter-process mutual exclusion.
    """

    def __init__(self, path: Path):
        self._path = path
        self._fh: Optional[Any] = None

    def acquire(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+b")
        self._fh = fh
        if fcntl is not None:
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        fh.close()
                        self._fh = None
                        raise TimeoutError(f"timeout acquiring lock: {self._path}")
                    time.sleep(0.01)
        elif msvcrt is not None:  # pragma: no cover - windows fallback
            # Use msvcrt.locking on the file region
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        fh.close()
                        self._fh = None
                        raise TimeoutError(f"timeout acquiring lock: {self._path}")
                    time.sleep(0.01)
        else:  # pragma: no cover - extremely rare
            # Fallback to thread lock only (not process-safe)
            # But we still hold the file handle to signal usage
            pass

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
            elif msvcrt is not None:  # pragma: no cover
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            try:
                self._fh.close()
            finally:
                self._fh = None

    def __enter__(self) -> "FileLock":
        self.acquire(timeout=5.0)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


# ---- Provider Rate Limiter ----

ConfigDict = Dict[str, Any]
StateDict = Dict[str, Any]
EventDict = Dict[str, Any]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    blocked_reason: Optional[str]
    remaining_requests: Optional[int]
    reset_at: Optional[str]
    project_id: str
    request_id: str
    evaluated_at: str


class ProviderRateLimiter:
    """A provider-neutral, per-project request rate limiter with persistence.

    Persistence layout (under storage_root):
    - events.json: deterministic JSON array of event objects.
    - events.lock: file lock for events.json writes.
    - projects/<project_id>/state.json: deterministic per-project state (config + window entries).
    - projects/<project_id>/lock: file lock for state operations.

    Concurrency: atomic check_and_register guarded by per-project file lock.
    Deterministic JSON: all persisted JSON uses sorted keys and compact separators.
    Time: all timestamps are in UTC with microseconds and 'Z' suffix.
    """

    def __init__(
        self,
        storage_root: Union[str, os.PathLike[str]],
        project_resolver: Callable[[str], bool],
        *,
        clock: Optional[Clock] = None,
        lock_timeout: float = 5.0,
    ) -> None:
        self._root = Path(storage_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._projects_dir = self._root / "projects"
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._root / "events.json"
        self._events_lock_path = self._root / "events.lock"
        self._project_resolver = project_resolver
        self._clock = clock if clock is not None else SystemUTCClock()
        self._lock_timeout = float(lock_timeout)
        # Thread-level mutexes to avoid re-acquiring non-reentrant file locks in same process
        self._thread_locks: Dict[str, threading.RLock] = {}
        self._global_lock = threading.RLock()
        # Ensure events.json initialized deterministically
        if not self._events_path.exists():
            self._atomic_write_json(self._events_path, [])

    # ---- Public API ----
    def configure_limit(self, project_id: str, config: Mapping[str, Any]) -> ConfigDict:
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        # Validate full config with required fields, reject unknown
        cfg = self._validate_new_config(pid, config)
        # Acquire project lock
        with self._project_lock(pid):
            state = self._load_state(pid)
            # Overwrite config
            state["config"] = cfg
            state["updated_at"] = _isoformat(self._clock.now())
            # Reset window entries on configure for determinism
            state["window"] = {"entries": {}, "last_evaluated_at": state["updated_at"]}
            self._write_state(pid, state)
        # Emit event out of project lock to avoid nested file locks
        self._emit_event({
            "type": "rate_limit_configured",
            "project_id": pid,
            "timestamp": cfg["updated_at"],
            "request_limit": cfg["request_limit"],
            "window_seconds": cfg["window_seconds"],
            "burst_limit": cfg["burst_limit"],
            "enabled": cfg["enabled"],
        })
        return cfg

    def update_limit(self, project_id: str, changes: Mapping[str, Any]) -> ConfigDict:
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        self._validate_update_fields(changes)
        with self._project_lock(pid):
            state = self._load_state(pid)
            cfg = state.get("config")
            if cfg is None:
                raise ValueError("no active configuration to update")
            # Apply changes
            new_cfg = dict(cfg)
            for k, v in changes.items():
                if k == "updated_at" or k == "created_at" or k == "project_id":
                    raise ValueError("cannot update protected field")
                new_cfg[k] = v
            # Re-validate final config
            new_cfg = self._validate_existing_config_update(new_cfg)
            new_cfg["updated_at"] = _isoformat(self._clock.now())
            state["config"] = new_cfg
            state["updated_at"] = new_cfg["updated_at"]
            # Do not clear window entries on update
            self._write_state(pid, state)
        self._emit_event({
            "type": "rate_limit_updated",
            "project_id": pid,
            "timestamp": new_cfg["updated_at"],
            "request_limit": new_cfg["request_limit"],
            "window_seconds": new_cfg["window_seconds"],
            "burst_limit": new_cfg["burst_limit"],
            "enabled": new_cfg["enabled"],
        })
        return new_cfg

    def get_limit(self, project_id: str) -> Optional[ConfigDict]:
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        state = self._load_state(pid)
        cfg = state.get("config")
        return cfg

    def remove_limit(self, project_id: str) -> bool:
        """Remove only the active configuration. State file and directory remain.
        Returns True if a config was removed, False if already absent.
        """
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        removed = False
        with self._project_lock(pid):
            state = self._load_state(pid)
            if state.get("config") is not None:
                removed = True
            # Clear config and window, but retain valid state.json
            state["config"] = None
            state["updated_at"] = _isoformat(self._clock.now())
            state["window"] = {"entries": {}, "last_evaluated_at": state["updated_at"]}
            self._write_state(pid, state)
        if removed:
            self._emit_event({
                "type": "rate_limit_removed",
                "project_id": pid,
                "timestamp": state["updated_at"],
            })
        return removed

    def check_request(self, project_id: str, request_id: str, timestamp: Optional[datetime] = None) -> Decision:
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        rid = self._validate_request_id(request_id)
        now = _ensure_utc(timestamp or self._clock.now())
        with self._project_lock(pid, write=False):
            state = self._load_state(pid)
            cfg = state.get("config")
            if not cfg or not cfg.get("enabled", False):
                return Decision(True, None, None, None, pid, rid, _isoformat(now))
            # Prune expired in-memory view (do not persist on check)
            entries = dict(state.get("window", {}).get("entries", {}))
            self._prune_entries_inplace(entries, now, int(cfg["window_seconds"]))
            if rid in entries:
                return Decision(False, "duplicate_request", len(entries) - int(bool(rid in entries)),
                                self._compute_reset_at(entries, int(cfg["window_seconds"])), pid, rid, _isoformat(now))
            capacity = int(cfg["burst_limit"]) if cfg.get("burst_limit") is not None else int(cfg["request_limit"])
            remaining = max(0, capacity - len(entries))
            reset_at = self._compute_reset_at(entries, int(cfg["window_seconds"]))
            allowed = remaining > 0
            return Decision(allowed, None if allowed else "rate_limit_exceeded", remaining, reset_at, pid, rid, _isoformat(now))

    def register_request(self, project_id: str, request_id: str, timestamp: Optional[datetime] = None) -> Decision:
        # Registration must be atomic and ensure no over-commit; delegate to check_and_register
        return self.check_and_register(project_id, request_id, timestamp)

    def check_and_register(self, project_id: str, request_id: str, timestamp: Optional[datetime] = None) -> Decision:
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        rid = self._validate_request_id(request_id)
        now = _ensure_utc(timestamp or self._clock.now())
        with self._project_lock(pid):
            state = self._load_state(pid)
            cfg = state.get("config")
            # Missing or disabled config: unrestricted behavior, do not mutate window
            if not cfg or not cfg.get("enabled", False):
                decision = Decision(True, None, None, None, pid, rid, _isoformat(now))
                self._emit_event({
                    "type": "request_registered",
                    "project_id": pid,
                    "request_id": rid,
                    "timestamp": decision.evaluated_at,
                    "unrestricted": True,
                })
                return decision
            # Active config: enforce
            window_seconds = int(cfg["window_seconds"])  # validated
            entries: Dict[str, str] = dict(state.get("window", {}).get("entries", {}))
            # Prune expired entries first deterministically
            self._prune_entries_inplace(entries, now, window_seconds)
            if rid in entries:
                # Duplicate detected before capacity evaluation
                decision = Decision(False, "duplicate_request", None, self._compute_reset_at(entries, window_seconds), pid, rid, _isoformat(now))
                # Do not persist any change to state for duplicate (timestamp must not update)
                self._emit_event({
                    "type": "rate_limit_blocked",
                    "project_id": pid,
                    "request_id": rid,
                    "timestamp": decision.evaluated_at,
                    "reason": "duplicate_request",
                })
                return decision
            capacity = int(cfg["burst_limit"]) if cfg.get("burst_limit") is not None else int(cfg["request_limit"])
            current = len(entries)
            remaining_before = max(0, capacity - current)
            if remaining_before <= 0:
                decision = Decision(False, "rate_limit_exceeded", 0, self._compute_reset_at(entries, window_seconds), pid, rid, _isoformat(now))
                self._emit_event({
                    "type": "rate_limit_blocked",
                    "project_id": pid,
                    "request_id": rid,
                    "timestamp": decision.evaluated_at,
                    "reason": "rate_limit_exceeded",
                    "window_size": window_seconds,
                    "capacity": capacity,
                })
                return decision
            # Register deterministically
            entries[rid] = _isoformat(now)
            # Persist state
            state["window"] = {
                "entries": self._sorted_entries_dict(entries),
                "last_evaluated_at": _isoformat(now),
            }
            state["updated_at"] = _isoformat(now)
            self._write_state(pid, state)
            remaining_after = max(0, capacity - len(entries))
            reset_at = self._compute_reset_at(entries, window_seconds)
            decision = Decision(True, None, remaining_after, reset_at, pid, rid, _isoformat(now))
        # Emit events after releasing project file lock
        self._emit_event({
            "type": "request_registered",
            "project_id": pid,
            "request_id": rid,
            "timestamp": decision.evaluated_at,
            "remaining": decision.remaining_requests,
        })
        # Warning when near capacity (<=10% or <=1)
        warn_thresh = max(1, capacity // 10)
        if remaining_after <= warn_thresh:
            self._emit_event({
                "type": "rate_limit_warning",
                "project_id": pid,
                "timestamp": decision.evaluated_at,
                "remaining": remaining_after,
                "capacity": capacity,
            })
        return decision

    def remaining(self, project_id: str, timestamp: Optional[datetime] = None) -> Optional[int]:
        pid = self._validate_project_id(project_id)
        self._ensure_known_project(pid)
        now = _ensure_utc(timestamp or self._clock.now())
        state = self._load_state(pid)
        cfg = state.get("config")
        if not cfg or not cfg.get("enabled", False):
            return None
        entries = dict(state.get("window", {}).get("entries", {}))
        self._prune_entries_inplace(entries, now, int(cfg["window_seconds"]))
        capacity = int(cfg["burst_limit"]) if cfg.get("burst_limit") is not None else int(cfg["request_limit"])
        return max(0, capacity - len(entries))

    def status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        now = _isoformat(self._clock.now())
        if project_id is not None:
            pid = self._validate_project_id(project_id)
            self._ensure_known_project(pid)
            return {pid: self._project_status(pid, now)}
        # All projects under storage
        result: Dict[str, Any] = {}
        for proj_dir in sorted(self._projects_dir.iterdir()):
            if not proj_dir.is_dir():
                continue
            pid = proj_dir.name
            if not _SAFE_PROJECT_ID.match(pid):
                continue
            result[pid] = self._project_status(pid, now)
        return result

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[EventDict]:
        if limit <= 0:
            return []
        events = self._read_events()
        if project_id is not None:
            pid = self._validate_project_id(project_id)
            events = [e for e in events if e.get("project_id") == pid]
        # Return latest deterministically by original order tail
        return events[-limit:]

    # ---- Internal helpers ----
    def _project_status(self, pid: str, now_iso: str) -> Dict[str, Any]:
        state = self._load_state(pid)
        cfg = state.get("config")
        entries = dict(state.get("window", {}).get("entries", {}))
        if not cfg or not cfg.get("enabled", False):
            return {
                "project_id": pid,
                "configured": bool(cfg is not None),
                "enabled": False if cfg is not None else None,
                "request_limit": cfg.get("request_limit") if cfg else None,
                "window_seconds": cfg.get("window_seconds") if cfg else None,
                "burst_limit": cfg.get("burst_limit") if cfg else None,
                "current_count": len(entries),
                "remaining": None,
                "reset_at": None,
                "updated_at": state.get("updated_at"),
                "now": now_iso,
            }
        window_seconds = int(cfg["window_seconds"])  # validated
        self._prune_entries_inplace(entries, _parse_isoformat(now_iso), window_seconds)
        capacity = int(cfg["burst_limit"]) if cfg.get("burst_limit") is not None else int(cfg["request_limit"])
        return {
            "project_id": pid,
            "configured": True,
            "enabled": True,
            "request_limit": int(cfg["request_limit"]),
            "window_seconds": window_seconds,
            "burst_limit": cfg.get("burst_limit"),
            "current_count": len(entries),
            "remaining": max(0, capacity - len(entries)),
            "reset_at": self._compute_reset_at(entries, window_seconds),
            "updated_at": state.get("updated_at"),
            "now": now_iso,
        }

    def _validate_project_id(self, project_id: str) -> str:
        if not isinstance(project_id, str) or not _SAFE_PROJECT_ID.fullmatch(project_id or ""):
            raise ValueError("invalid project_id")
        return project_id

    def _validate_request_id(self, request_id: str) -> str:
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise ValueError("invalid request_id")
        # Limit to safe printable set for events and persistence; reject path-like ids
        if any(ch in request_id for ch in ("/", "\\", "\n", "\r", "\t")):
            raise ValueError("invalid request_id characters")
        return request_id

    def _ensure_known_project(self, project_id: str) -> None:
        if not self._project_resolver(project_id):
            raise ValueError("unknown project")

    def _project_dir(self, project_id: str) -> Path:
        d = self._projects_dir / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "state.json"

    def _project_lock_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "lock"

    def _project_lock(self, project_id: str, *, write: bool = True):
        # Combine thread-level lock with file lock to avoid deadlocks in-process
        class _Ctx:
            def __init__(self, outer: "ProviderRateLimiter", pid: str, write: bool) -> None:
                self.outer = outer
                self.pid = pid
                self.write = write
                self.thread_lock: Optional[threading.RLock] = None
                self.file_lock: Optional[FileLock] = None

            def __enter__(self):
                # Thread lock
                with self.outer._global_lock:
                    lock = self.outer._thread_locks.get(self.pid)
                    if lock is None:
                        lock = threading.RLock()
                        self.outer._thread_locks[self.pid] = lock
                    self.thread_lock = lock
                self.thread_lock.acquire()  # type: ignore[union-attr]
                # File lock only for write operations; reads use shared thread lock
                if self.write:
                    self.file_lock = FileLock(self.outer._project_lock_path(self.pid))
                    self.file_lock.acquire(self.outer._lock_timeout)
                return self

            def __exit__(self, exc_type, exc, tb):
                if self.file_lock is not None:
                    self.file_lock.release()
                if self.thread_lock is not None:
                    self.thread_lock.release()

        return _Ctx(self, project_id, write)

    def _load_state(self, project_id: str) -> StateDict:
        path = self._state_path(project_id)
        if not path.exists():
            # Initialize new state deterministically
            now = _isoformat(self._clock.now())
            state: StateDict = {
                "version": 1,
                "project_id": project_id,
                "config": None,
                "window": {"entries": {}, "last_evaluated_at": now},
                "updated_at": now,
            }
            self._atomic_write_json(path, state)
            return state
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"corrupted storage for project {project_id}: invalid JSON") from e
        # Basic validation of structure
        if not isinstance(data, dict) or data.get("project_id") != project_id or "window" not in data:
            raise RuntimeError(f"corrupted storage for project {project_id}: invalid structure")
        # Reject symlink escape: ensure file is regular file
        if not path.is_file():
            raise RuntimeError("state path is not a file")
        return data

    def _write_state(self, project_id: str, state: StateDict) -> None:
        # Deterministic order of entries
        if "window" in state and isinstance(state["window"], dict):
            entries = state["window"].get("entries", {})
            state["window"]["entries"] = self._sorted_entries_dict(entries)
        self._atomic_write_json(self._state_path(project_id), state)

    def _sorted_entries_dict(self, entries: Mapping[str, str]) -> Dict[str, str]:
        # Sort by (timestamp, request_id) for deterministic JSON
        items = list(entries.items())
        try:
            items.sort(key=lambda kv: (_parse_isoformat(kv[1]), kv[0]))
        except Exception:
            # If timestamps invalid (should not happen), fall back to id sort
            items.sort(key=lambda kv: kv[0])
        return {k: v for k, v in items}

    def _atomic_write_json(self, path: Path, obj: Any) -> None:
        # Write using a safe temp name in the same directory then os.replace
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = f".tmp-{int(time.time_ns())}-{os.getpid()}.json"
        tmp = directory / safe_name
        data = _json_dumps(obj)
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def _emit_event(self, event: Mapping[str, Any]) -> None:
        # Sanitize event to keep only safe identifiers, counters, and timestamps
        safe: Dict[str, Any] = {}
        for k, v in event.items():
            if k in {"type", "project_id", "request_id", "timestamp", "reason", "remaining", "capacity", "window_size", "request_limit", "window_seconds", "burst_limit", "enabled", "unrestricted"}:
                safe[k] = v
        # Deterministic append
        with FileLock(self._events_lock_path) as _:
            events = self._read_events()
            events.append(safe)
            self._atomic_write_json(self._events_path, events)

    def _read_events(self) -> List[EventDict]:
        if not self._events_path.exists():
            return []
        raw = self._events_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError("corrupted events storage") from e
        if not isinstance(data, list):
            raise RuntimeError("corrupted events storage structure")
        # Ensure each is a dict with minimal keys
        cleaned: List[EventDict] = []
        for ev in data:
            if isinstance(ev, dict):
                cleaned.append(ev)
        return cleaned

    def _validate_new_config(self, project_id: str, config: Mapping[str, Any]) -> ConfigDict:
        required = {"project_id", "enabled", "request_limit", "window_seconds", "burst_limit"}
        allowed = required | {"created_at", "updated_at"}
        # Reject unknown fields
        for k in config.keys():
            if k not in allowed:
                raise ValueError(f"unknown config field: {k}")
        # Check required present
        for k in required:
            if k not in config:
                raise ValueError(f"missing config field: {k}")
        if config.get("project_id") != project_id:
            raise ValueError("project_id mismatch in config")
        enabled = config.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        req_limit = config.get("request_limit")
        if not isinstance(req_limit, int) or req_limit <= 0:
            raise ValueError("request_limit must be a positive integer")
        win_sec = config.get("window_seconds")
        if not isinstance(win_sec, int) or win_sec <= 0:
            raise ValueError("window_seconds must be a positive integer")
        burst_val = config.get("burst_limit")
        if burst_val is not None and (not isinstance(burst_val, int) or burst_val < 0):
            raise ValueError("burst_limit must be non-negative integer or null")
        now_iso = _isoformat(self._clock.now())
        created_at = config.get("created_at") or now_iso
        updated_at = config.get("updated_at") or created_at
        # Normalize and return deterministic dict
        return {
            "project_id": project_id,
            "enabled": enabled,
            "request_limit": int(req_limit),
            "window_seconds": int(win_sec),
            "burst_limit": int(burst_val) if burst_val is not None else None,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _validate_update_fields(self, changes: Mapping[str, Any]) -> None:
        allowed = {"enabled", "request_limit", "window_seconds", "burst_limit"}
        for k in changes.keys():
            if k not in allowed:
                raise ValueError(f"unknown update field: {k}")
        # Validate types if present
        if "enabled" in changes and not isinstance(changes["enabled"], bool):
            raise ValueError("enabled must be boolean")
        if "request_limit" in changes:
            v = changes["request_limit"]
            if not isinstance(v, int) or v <= 0:
                raise ValueError("request_limit must be a positive integer")
        if "window_seconds" in changes:
            v2 = changes["window_seconds"]
            if not isinstance(v2, int) or v2 <= 0:
                raise ValueError("window_seconds must be a positive integer")
        if "burst_limit" in changes:
            b = changes["burst_limit"]
            if b is not None and (not isinstance(b, int) or b < 0):
                raise ValueError("burst_limit must be non-negative integer or null")

    def _validate_existing_config_update(self, cfg: Mapping[str, Any]) -> ConfigDict:
        # Ensure final config is valid
        project_id = cfg.get("project_id")
        if not isinstance(project_id, str) or not _SAFE_PROJECT_ID.fullmatch(project_id):
            raise ValueError("invalid project_id in existing config")
        enabled = cfg.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        req = cfg.get("request_limit")
        if not isinstance(req, int) or req <= 0:
            raise ValueError("request_limit must be a positive integer")
        win = cfg.get("window_seconds")
        if not isinstance(win, int) or win <= 0:
            raise ValueError("window_seconds must be a positive integer")
        burst = cfg.get("burst_limit")
        if burst is not None and (not isinstance(burst, int) or burst < 0):
            raise ValueError("burst_limit must be non-negative integer or null")
        created_at = cfg.get("created_at")
        if not isinstance(created_at, str):
            created_at = _isoformat(self._clock.now())
        updated_at = cfg.get("updated_at") if isinstance(cfg.get("updated_at"), str) else _isoformat(self._clock.now())
        return {
            "project_id": project_id,
            "enabled": enabled,
            "request_limit": int(req),
            "window_seconds": int(win),
            "burst_limit": int(burst) if burst is not None else None,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _prune_entries_inplace(self, entries: MutableMapping[str, str], now: datetime, window_seconds: int) -> None:
        cutoff = now - timedelta(seconds=window_seconds)
        to_del: List[str] = []
        for rid, ts in entries.items():
            try:
                dt = _parse_isoformat(ts)
            except Exception:
                # Corrupted entry; prune defensively
                to_del.append(rid)
                continue
            if dt <= cutoff:
                to_del.append(rid)
        if to_del:
            for rid in to_del:
                entries.pop(rid, None)

    def _compute_reset_at(self, entries: Mapping[str, str], window_seconds: int) -> Optional[str]:
        if not entries:
            return None
        # Earliest timestamp plus window
        try:
            earliest = min((_parse_isoformat(ts) for ts in entries.values()))
        except Exception:
            return None
        reset = earliest + timedelta(seconds=window_seconds)
        return _isoformat(reset)


__all__ = [
    "ProviderRateLimiter",
    "SystemUTCClock",
    "Decision",
]
