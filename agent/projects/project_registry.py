from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePath
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

try:
    import fcntl  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - platform without fcntl (e.g., Windows)
    fcntl = None  # type: ignore[assignment]

__all__ = [
    "ProjectRegistry",
    "ProjectContext",
    "ProjectRegistryError",
    "ProjectValidationError",
    "DuplicateProjectError",
    "UnknownProjectError",
    "CrossProjectViolation",
    "RegistryStorageCorrupted",
    "ProtectedDeletionError",
]


class ProjectRegistryError(Exception):
    pass


class ProjectValidationError(ProjectRegistryError):
    pass


class DuplicateProjectError(ProjectRegistryError):
    pass


class UnknownProjectError(ProjectRegistryError):
    pass


class CrossProjectViolation(ProjectRegistryError):
    pass


class RegistryStorageCorrupted(ProjectRegistryError):
    pass


class ProtectedDeletionError(ProjectRegistryError):
    pass


_REQUIRED_FIELDS = [
    "project_id",
    "display_name",
    "repository_root",
    "default_branch",
    "project_type",
    "mission_queue_path",
    "conversations_path",
    "uploads_metadata_path",
    "uploads_directory",
    "events_path",
    "reports_path",
    "worker_heartbeat_path",
    "deployment_target",
    "allowed_domains",
    "enabled_providers",
    "policy_profile",
    "created_at",
    "updated_at",
    "status",
]

# Public states and types
_SUPPORTED_STATES = {"active", "suspended", "archived"}
_SUPPORTED_TYPES = {"generic", "wordpress", "python", "node", "nextjs", "react", "static"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(dt: datetime) -> str:
    # Always format with microseconds and trailing Z
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_isoformat_utc(s: str) -> datetime:
    # Accept ...Z with microseconds
    if not s.endswith("Z"):
        raise ValueError("timestamp must end with Z")
    base = s[:-1]
    # datetime.fromisoformat requires +00:00 or no Z; parse manually
    try:
        # try microseconds
        return datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    except ValueError:
        # try seconds only
        return datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def _canonical_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_git_repo(path: Path) -> bool:
    # No network or process invocation; only filesystem checks
    if not path.exists() or not path.is_dir():
        return False
    git_dir = path / ".git"
    if git_dir.is_dir() or git_dir.is_file():
        return True
    # Accept bare repo (has HEAD and objects/ dirs)
    if (path / "HEAD").exists() and (path / "objects").is_dir():
        return True
    return False


def _validate_project_id(project_id: str) -> None:
    # Valid: lowercase letters, digits, hyphen, underscore; cannot start/end with hyphen/underscore
    # Accept one-character ids like 'b'
    if not isinstance(project_id, str):
        raise ProjectValidationError("project_id must be a string")
    if not project_id:
        raise ProjectValidationError("project_id must not be empty")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?", project_id):
        raise ProjectValidationError("invalid project_id format")
    # Additional safety: reject control chars, slashes, backslashes, dots
    if any(ch in project_id for ch in ("/", "\\", ".", " ")):
        raise ProjectValidationError("project_id contains invalid characters")


def _reject_unknown_fields(profile: Mapping[str, object]) -> None:
    unknown = set(profile.keys()) - set(_REQUIRED_FIELDS)
    if unknown:
        raise ProjectValidationError(f"unknown fields: {sorted(unknown)}")


def _ensure_list_of_str(name: str, value: object) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ProjectValidationError(f"{name} must be a list of strings")
    return list(value)


def _ensure_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ProjectValidationError(f"{name} must be a string")
    return value


def _safe_relative_path_str(name: str, value: object) -> str:
    s = _ensure_str(name, value)
    # Allow relative or absolute paths; traversal will be checked when resolving
    # Disallow control characters and null bytes
    if any(ord(ch) < 32 for ch in s):
        raise ProjectValidationError(f"{name} contains control characters")
    return s


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    repository_root: Path
    default_branch: str
    queue_path: Path
    conversations_path: Path
    uploads_metadata_path: Path
    uploads_directory: Path
    events_path: Path
    reports_path: Path
    worker_heartbeat_path: Path
    deployment_target: str
    allowed_domains: Tuple[str, ...]
    enabled_providers: Tuple[str, ...]
    policy_profile: str | Mapping[str, object]
    project_type: str

    def to_dict(self) -> Mapping[str, object]:
        # Deterministic ordering in construction
        return {
            "project_id": self.project_id,
            "repository_root": str(self.repository_root),
            "default_branch": self.default_branch,
            "queue_path": str(self.queue_path),
            "conversations_path": str(self.conversations_path),
            "uploads_metadata_path": str(self.uploads_metadata_path),
            "uploads_directory": str(self.uploads_directory),
            "events_path": str(self.events_path),
            "reports_path": str(self.reports_path),
            "worker_heartbeat_path": str(self.worker_heartbeat_path),
            "deployment_target": self.deployment_target,
            "allowed_domains": list(self.allowed_domains),
            "enabled_providers": list(self.enabled_providers),
            "policy_profile": self.policy_profile,
            "project_type": self.project_type,
        }


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: Optional[int] = None

    def __enter__(self) -> "_FileLock":
        # Create/open lock file for duration; use fcntl if available
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._path), os.O_RDWR | os.O_CREAT, 0o600)
        self._fd = fd
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:  # Best-effort on platforms without fcntl: rely on atomic replace operations elsewhere
            pass
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            if fcntl is not None:
                try:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                except Exception:
                    pass
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None


class ProjectRegistry:
    """
    Persistent project registry with deterministic atomic JSON storage and strict validation.

    Thread-safety:
    - Public methods acquire a non-reentrant lock (self._lock) exactly once.
    - Private helpers with suffix _unlocked must be called with self._lock already held and never acquire it.
    - No nested calls to other public methods while holding the lock.
    """

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # Private data root for all projects under this registry
        self._data_root = self._storage_dir / "data"
        self._data_root.mkdir(parents=True, exist_ok=True)
        self._projects_dir = self._data_root / "projects"
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = self._storage_dir / "project_registry.json"
        self._lock = threading.Lock()
        self._clock = clock or _utcnow
        self._events_file = self._storage_dir / "registry_events.jsonl"
        # Internal in-memory map
        self._projects: Dict[str, Dict[str, object]] = {}
        # Track last updated timestamps per project to ensure monotonicity
        self._last_updated: Dict[str, datetime] = {}
        # Load existing storage
        self._load_registry()

    # -------------- Internal FS helpers --------------
    def _atomic_write(self, path: Path, content: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _load_registry(self) -> None:
        # Load file if exists
        if not self._registry_file.exists():
            self._projects = {}
            return
        try:
            with open(self._registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise RegistryStorageCorrupted("registry root must be an object")
            # Validate entries
            projects: Dict[str, Dict[str, object]] = {}
            for pid, raw in sorted(data.items(), key=lambda kv: kv[0]):
                if not isinstance(pid, str) or not isinstance(raw, dict):
                    raise RegistryStorageCorrupted("invalid registry entry")
                # Validate ID format again to ensure integrity
                _validate_project_id(pid)
                _reject_unknown_fields(raw)
                # Parse timestamps
                _parse_isoformat_utc(_ensure_str("created_at", raw.get("created_at")))
                updated = _parse_isoformat_utc(_ensure_str("updated_at", raw.get("updated_at")))
                self._last_updated[pid] = updated
                projects[pid] = raw
            self._projects = projects
        except json.JSONDecodeError as e:  # pragma: no cover - explicit test will cover branch
            raise RegistryStorageCorrupted("registry JSON is corrupted") from e
        except (OSError, ValueError, ProjectValidationError) as e:
            raise RegistryStorageCorrupted("registry storage invalid") from e

    def _persist_unlocked(self) -> None:
        # Deterministic ordered by project_id keys
        content = _canonical_json(self._projects)
        # File lock during write to prevent concurrent corruption across processes
        lock = _FileLock(self._registry_file.with_suffix(self._registry_file.suffix + ".lock"))
        with lock:
            self._atomic_write(self._registry_file, content)

    # -------------- Event helpers --------------
    def _emit_event_unlocked(self, event: str, project_id: str, status: Optional[str] = None) -> None:
        evt = {
            "event": event,
            "project_id": project_id,
            "timestamp": _isoformat_utc(self._clock()),
        }
        if status is not None:
            evt["status"] = status
        line = _canonical_json(evt)
        # Best-effort append; do not raise exceptions that break registry operations
        try:
            self._events_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._events_file, "a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
        except Exception:
            # Swallow event writing errors silently to not disrupt registry behavior
            pass

    # -------------- Validation --------------
    def validate_project(self, profile: Mapping[str, object], *, validate_repository: bool = True) -> Dict[str, object]:
        # Public method does not acquire lock to allow external validation independently.
        # Validate schema and values, returning a sanitized copy.
        sanitized: Dict[str, object] = {}
        _reject_unknown_fields(profile)
        pid = _ensure_str("project_id", profile.get("project_id"))
        _validate_project_id(pid)
        sanitized["project_id"] = pid

        display_name = _ensure_str("display_name", profile.get("display_name"))
        sanitized["display_name"] = display_name

        repository_root_str = _ensure_str("repository_root", profile.get("repository_root"))
        repository_root_path = Path(repository_root_str)
        if validate_repository and not _is_git_repo(repository_root_path):
            raise ProjectValidationError("repository_root is not a valid Git repository")
        sanitized["repository_root"] = str(repository_root_path)

        default_branch = _ensure_str("default_branch", profile.get("default_branch"))
        if not default_branch or any(ch.isspace() for ch in default_branch):
            raise ProjectValidationError("default_branch must be a non-empty string without whitespace")
        sanitized["default_branch"] = default_branch

        project_type = _ensure_str("project_type", profile.get("project_type"))
        if project_type not in _SUPPORTED_TYPES:
            raise ProjectValidationError("unsupported project_type")
        sanitized["project_type"] = project_type

        # Paths (relative preferred). Traversal and symlink escapes will be checked when resolving
        for key in (
            "mission_queue_path",
            "conversations_path",
            "uploads_metadata_path",
            "uploads_directory",
            "events_path",
            "reports_path",
            "worker_heartbeat_path",
        ):
            sanitized[key] = _safe_relative_path_str(key, profile.get(key))

        deployment_target = _ensure_str("deployment_target", profile.get("deployment_target"))
        sanitized["deployment_target"] = deployment_target

        allowed_domains = _ensure_list_of_str("allowed_domains", profile.get("allowed_domains"))
        sanitized["allowed_domains"] = allowed_domains

        enabled_providers = _ensure_list_of_str("enabled_providers", profile.get("enabled_providers"))
        # Ensure only identifiers, not secrets. Simple policy: alnum, hyphen, underscore, colon, dot allowed
        for p in enabled_providers:
            if not re.fullmatch(r"[A-Za-z0-9._:-]+", p):
                raise ProjectValidationError("enabled_providers contains invalid identifier")
        sanitized["enabled_providers"] = enabled_providers

        policy_profile = profile.get("policy_profile")
        if isinstance(policy_profile, (str, dict)):
            sanitized["policy_profile"] = policy_profile
        else:
            raise ProjectValidationError("policy_profile must be a string or object reference")

        status = _ensure_str("status", profile.get("status"))
        if status not in _SUPPORTED_STATES:
            raise ProjectValidationError("unsupported project status")
        sanitized["status"] = status

        # created_at / updated_at may be provided by callers for initial fixtures; validate or set placeholders
        created_raw = profile.get("created_at")
        updated_raw = profile.get("updated_at")
        if created_raw is None:
            sanitized["created_at"] = _isoformat_utc(self._clock())
        else:
            # validate format; keep provided value
            _parse_isoformat_utc(_ensure_str("created_at", created_raw))
            sanitized["created_at"] = created_raw  # type: ignore[assignment]
        if updated_raw is None:
            sanitized["updated_at"] = _isoformat_utc(self._clock())
        else:
            _parse_isoformat_utc(_ensure_str("updated_at", updated_raw))
            sanitized["updated_at"] = updated_raw  # type: ignore[assignment]

        # Never accept secrets or unknown fields because _reject_unknown_fields already enforced
        return sanitized

    # -------------- Public API --------------
    def create_project(self, profile: Mapping[str, object]) -> Dict[str, object]:
        with self._lock:
            # Validate before creation
            try:
                validated = self.validate_project(profile, validate_repository=True)
            except ProjectValidationError as e:
                pid = str(profile.get("project_id", "")) if isinstance(profile.get("project_id"), str) else ""
                self._emit_event_unlocked("project_validation_failed", pid)
                raise
            pid = validated["project_id"]  # type: ignore[index]
            if pid in self._projects:
                raise DuplicateProjectError(f"project_id already exists: {pid}")
            # Ensure timestamps are deterministic and microsecond precision
            now = self._clock()
            created = now
            updated = now
            validated["created_at"] = _isoformat_utc(created)
            validated["updated_at"] = _isoformat_utc(updated)
            self._projects[pid] = validated
            self._last_updated[pid] = updated
            # Persist
            self._persist_unlocked()
            self._emit_event_unlocked("project_created", pid, status=str(validated.get("status")))
            self._emit_event_unlocked("project_validation_succeeded", pid)
            return dict(validated)

    def update_project(self, project_id: str, updates: Mapping[str, object]) -> Dict[str, object]:
        with self._lock:
            _validate_project_id(project_id)
            if project_id not in self._projects:
                raise UnknownProjectError(project_id)
            current = dict(self._projects[project_id])
            # Do not allow updating project_id or created_at
            if "project_id" in updates and updates["project_id"] != project_id:
                raise ProjectValidationError("project_id is immutable")
            if "created_at" in updates and updates["created_at"] != current.get("created_at"):
                raise ProjectValidationError("created_at is immutable")
            # Apply updates to a candidate profile
            candidate = dict(current)
            for k, v in updates.items():
                candidate[k] = v
            # Validate candidate
            validated = self.validate_project(candidate, validate_repository=True)
            # Ensure created_at remains from original
            validated["created_at"] = current["created_at"]
            # Monotonic updated_at
            now = self._clock()
            last = self._last_updated.get(project_id, _parse_isoformat_utc(str(current["updated_at"])))
            if now <= last:
                # Advance at least 1 microsecond deterministically
                now = last + timedelta(microseconds=1)
            validated["updated_at"] = _isoformat_utc(now)
            self._last_updated[project_id] = now
            self._projects[project_id] = validated
            self._persist_unlocked()
            self._emit_event_unlocked("project_updated", project_id, status=str(validated.get("status")))
            return dict(validated)

    def get_project(self, project_id: str) -> Dict[str, object]:
        with self._lock:
            _validate_project_id(project_id)
            if project_id not in self._projects:
                raise UnknownProjectError(project_id)
            return dict(self._projects[project_id])

    def list_projects(self) -> List[Dict[str, object]]:
        with self._lock:
            # Deterministic order by project_id
            return [dict(self._projects[pid]) for pid in sorted(self._projects.keys())]

    def suspend_project(self, project_id: str) -> Dict[str, object]:
        return self._set_status(project_id, "suspended", event_name="project_suspended")

    def activate_project(self, project_id: str) -> Dict[str, object]:
        return self._set_status(project_id, "active", event_name="project_activated")

    def archive_project(self, project_id: str) -> Dict[str, object]:
        return self._set_status(project_id, "archived", event_name="project_archived")

    def _set_status(self, project_id: str, status: str, *, event_name: str) -> Dict[str, object]:
        if status not in _SUPPORTED_STATES:
            raise ProjectValidationError("unsupported status")
        with self._lock:
            _validate_project_id(project_id)
            if project_id not in self._projects:
                raise UnknownProjectError(project_id)
            profile = dict(self._projects[project_id])
            if profile.get("status") == status:
                # No-op but update timestamp to reflect explicit state change request? Keep deterministic and idempotent; do not change timestamp
                self._emit_event_unlocked(event_name, project_id, status=status)
                return dict(profile)
            profile["status"] = status
            # Validate and persist
            validated = self.validate_project(profile, validate_repository=False)
            validated["created_at"] = self._projects[project_id]["created_at"]
            # Update updated_at monotonic
            now = self._clock()
            last = self._last_updated.get(project_id, _parse_isoformat_utc(str(self._projects[project_id]["updated_at"])) )
            if now <= last:
                now = last + timedelta(microseconds=1)
            validated["updated_at"] = _isoformat_utc(now)
            self._last_updated[project_id] = now
            self._projects[project_id] = validated
            self._persist_unlocked()
            self._emit_event_unlocked(event_name, project_id, status=status)
            return dict(validated)

    def delete_project(self, project_id: str, *, force: bool = False) -> None:
        with self._lock:
            _validate_project_id(project_id)
            profile = self._projects.get(project_id)
            if profile is None:
                raise UnknownProjectError(project_id)
            if not force and profile.get("status") == "active":
                raise ProtectedDeletionError("cannot delete active project without force=True")
            # Deleting affects registry metadata only
            del self._projects[project_id]
            self._last_updated.pop(project_id, None)
            self._persist_unlocked()
            self._emit_event_unlocked("project_deleted", project_id, status=str(profile.get("status")))

    def status(self) -> Mapping[str, int]:
        with self._lock:
            counts: Dict[str, int] = {"active": 0, "suspended": 0, "archived": 0}
            for p in self._projects.values():
                st = str(p.get("status"))
                if st in counts:
                    counts[st] += 1
            return counts

    def latest_events(self, limit: int = 50) -> List[Mapping[str, object]]:
        # Read last 'limit' events from events file without exposing unrestricted paths
        if limit <= 0:
            return []
        events: List[Mapping[str, object]] = []
        if not self._events_file.exists():
            return events
        try:
            with open(self._events_file, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                    if isinstance(evt, dict):
                        # Ensure only safe fields are exposed
                        safe_evt = {
                            "event": evt.get("event"),
                            "project_id": evt.get("project_id"),
                            "timestamp": evt.get("timestamp"),
                        }
                        if "status" in evt:
                            safe_evt["status"] = evt["status"]
                        events.append(safe_evt)
                except Exception:
                    continue
        except Exception:
            return []
        return events

    # -------------- Path resolution --------------
    def resolve_project_paths(self, project_id: str) -> Mapping[str, Path]:
        with self._lock:
            _validate_project_id(project_id)
            profile = self._projects.get(project_id)
            if profile is None:
                raise UnknownProjectError(project_id)
            return self._resolve_project_paths_unlocked(project_id, profile)

    def _resolve_project_paths_unlocked(self, project_id: str, profile: Mapping[str, object]) -> Mapping[str, Path]:
        base = self._projects_dir / project_id
        base_resolved = base.resolve(strict=False)
        # Never create directories here; purely resolve and validate
        def resolve_one(key: str) -> Path:
            raw = str(profile[key])
            p = Path(raw)
            if p.is_absolute():
                # Must remain within the project's base directory
                resolved = p.resolve(strict=False)
            else:
                resolved = (base / p).resolve(strict=False)
            # Prevent symlink escape: ensure resolved is within base
            try:
                if not resolved.is_relative_to(base_resolved):
                    raise ProjectValidationError(f"{key} escapes project base directory")
            except AttributeError:
                # For Python < 3.9; not applicable here but keep safe
                resolved_parts = resolved.parts
                base_parts = base_resolved.parts
                if base_parts != resolved_parts[: len(base_parts)]:
                    raise ProjectValidationError(f"{key} escapes project base directory")
            # Additional traversal prevention using PurePath parts
            pure = PurePath(resolved)
            if ".." in pure.parts:
                raise ProjectValidationError(f"{key} contains path traversal")
            return resolved

        return {
            "mission_queue_path": resolve_one("mission_queue_path"),
            "conversations_path": resolve_one("conversations_path"),
            "uploads_metadata_path": resolve_one("uploads_metadata_path"),
            "uploads_directory": resolve_one("uploads_directory"),
            "events_path": resolve_one("events_path"),
            "reports_path": resolve_one("reports_path"),
            "worker_heartbeat_path": resolve_one("worker_heartbeat_path"),
        }

    def get_context(self, project_id: str) -> ProjectContext:
        with self._lock:
            _validate_project_id(project_id)
            profile = self._projects.get(project_id)
            if profile is None:
                raise UnknownProjectError(project_id)
            paths = self._resolve_project_paths_unlocked(project_id, profile)
            ctx = ProjectContext(
                project_id=project_id,
                repository_root=Path(str(profile["repository_root"])).resolve(strict=False),
                default_branch=str(profile["default_branch"]),
                queue_path=paths["mission_queue_path"],
                conversations_path=paths["conversations_path"],
                uploads_metadata_path=paths["uploads_metadata_path"],
                uploads_directory=paths["uploads_directory"],
                events_path=paths["events_path"],
                reports_path=paths["reports_path"],
                worker_heartbeat_path=paths["worker_heartbeat_path"],
                deployment_target=str(profile["deployment_target"]),
                allowed_domains=tuple(str(x) for x in profile["allowed_domains"]),
                enabled_providers=tuple(str(x) for x in profile["enabled_providers"]),
                policy_profile=profile["policy_profile"],
                project_type=str(profile["project_type"]),
            )
            return ctx

    # -------------- Cross-project guards --------------
    def ensure_same_project(self, a_project_id: str, b_project_id: str, what: str = "reference") -> None:
        if a_project_id != b_project_id:
            raise CrossProjectViolation(f"cross-project {what} is not allowed: {a_project_id} -> {b_project_id}")

    # -------------- Utility --------------
    def data_root(self) -> Path:
        return self._data_root

    def projects_base_dir(self) -> Path:
        return self._projects_dir
