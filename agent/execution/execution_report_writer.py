from __future__ import annotations

import errno
import io
import json
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

__all__ = [
    "ExecutionReportWriter",
    "ValidationError",
    "StorageError",
]


class ValidationError(ValueError):
    """Raised when a report fails validation."""


class StorageError(RuntimeError):
    """Raised when storage is corrupted or unavailable."""


class _InterProcessFileLock:
    """Simple non-reentrant cross-platform inter-process file lock.

    Uses fcntl on POSIX and msvcrt on Windows. Avoids nested non-reentrant locking by
    tracking ownership in the current process/thread.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._fh: Optional[io.TextIOWrapper] = None
        self._owner: Optional[int] = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            tid = threading.get_ident()
            if self._owner == tid:
                raise RuntimeError("Non-reentrant lock acquisition attempted")
            if self._fh is None:
                # Create or open the lock file in a safe way.
                # Use text mode for simplicity; locking is on file descriptor.
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                self._fh = open(self._path, mode="a+", encoding="utf-8")
            fh = self._fh
            if fh is None:
                raise RuntimeError("Failed to open lock file")
            fileno = fh.fileno()
            if os.name == "nt":
                # Windows locking
                import msvcrt  # type: ignore

                try:
                    # _LK_LOCK constant is 1, but using name for clarity if available.
                    # Lock the entire file by seeking to start.
                    fh.seek(0)
                    # Lock 1 byte (sufficient to lock the file); exclusive lock.
                    msvcrt.locking(fileno, msvcrt.LK_LOCK, 1)
                except OSError as e:  # pragma: no cover - platform specific
                    raise StorageError(f"Failed to acquire lock: {e}") from e
            else:
                # POSIX locking
                import fcntl  # type: ignore

                try:
                    fcntl.flock(fileno, fcntl.LOCK_EX)
                except OSError as e:  # pragma: no cover - platform specific
                    raise StorageError(f"Failed to acquire lock: {e}") from e
            self._owner = tid

    def release(self) -> None:
        with self._lock:
            if self._fh is None:
                return
            if self._owner != threading.get_ident():
                # Only the owner can release; ignore spurious releases to be safe.
                return
            fh = self._fh
            fileno = fh.fileno()
            if os.name == "nt":
                import msvcrt  # type: ignore

                try:
                    fh.seek(0)
                    msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)
                except OSError as e:  # pragma: no cover - platform specific
                    raise StorageError(f"Failed to release lock: {e}") from e
            else:
                import fcntl  # type: ignore

                try:
                    fcntl.flock(fileno, fcntl.LOCK_UN)
                except OSError as e:  # pragma: no cover - platform specific
                    raise StorageError(f"Failed to release lock: {e}") from e
            self._owner = None

    def __enter__(self) -> "_InterProcessFileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.release()


_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "api-key",
    "authorization",
    "bearer",
    "credential",
    "private_key",
    "access_key",
    # Additional high-risk content that must never be persisted in raw form
    "prompt",
    "prompts",
    "completion",
    "completions",
    "messages",
    "full_messages",
    "uploaded_content",
    "raw_provider_response",
    "traceback",
    "environment",
    "env",
    "path",
    "paths",
    "file_path",
    "file_paths",
    "absolute_path",
    "absolute_paths",
    "system_prompt",
}


_ALLOWED_FIELDS: Tuple[str, ...] = (
    "execution_id",
    "project_id",
    "request_id",
    "conversation_id",
    "plan_id",
    "mission_id",
    "step_id",
    "task_type",
    "provider_id",
    "model_id",
    "worker_id",
    "started_at",
    "completed_at",
    "status",
    "success",
    "retryable",
    "fallback_used",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost",
    "cost_currency",
    "safe_error_code",
    "summary",
    "changed_files",
    "git_branch",
    "git_commit",
    "validation_status",
    "metadata",
)

_SUPPORTED_STATUSES: Tuple[str, ...] = (
    "completed",
    "failed",
    "blocked",
    "cancelled",
    "retrying",
)

# Safe identifier (filenames etc.)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
_BRANCH_PATTERN = re.compile(r"^(?![./-])(?!.*//)(?!.*\.$)[A-Za-z0-9._/\-]{1,255}(?<![./-])$")
_COMMIT_PATTERN = re.compile(r"^[A-Fa-f0-9]{7,64}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3,5}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_utc_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        # Accept trailing Z for UTC
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            raise ValidationError(f"Field '{field_name}' must be ISO-8601 datetime: {value!r}") from e
    else:
        raise ValidationError(f"Field '{field_name}' must be a datetime or ISO-8601 string")

    if dt.tzinfo is None:
        raise ValidationError(f"Field '{field_name}' must be timezone-aware in UTC")
    # Normalize to UTC
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc


def _isoformat_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_id(value: Any, name: str) -> str:
    if not _is_non_empty_str(value):
        raise ValidationError(f"Field '{name}' must be a non-empty string")
    s = value.strip()
    if not _ID_PATTERN.match(s):
        raise ValidationError(
            f"Field '{name}' must match pattern '{_ID_PATTERN.pattern}' and be length 1..128"
        )
    return s


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_non_negative_number(value: Any) -> bool:
    return (
        (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
        or (isinstance(value, float) and value >= 0.0)
    )


def _contains_control_chars(s: str) -> bool:
    return any(ord(ch) < 32 for ch in s)


def _is_safe_repo_relative_path(p: Any) -> bool:
    if not isinstance(p, str):
        return False
    if p == "":
        return False
    if os.path.isabs(p):
        return False
    if "\\" in p:
        return False
    if p.startswith("/") or p.endswith("/"):
        return False
    if _contains_control_chars(p):
        return False
    # No path traversal or empty segments
    segments = p.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        return False
    # Keep reasonable length
    if len(p) > 4096:
        return False
    return True


def _redact_value(value: Any) -> Any:
    # Replace sensitive content with a fixed marker deterministically
    return "[redacted]"


def _sanitize_structure(obj: Any) -> Any:
    """Recursively sanitize a structure by redacting sensitive keys case-insensitively.

    Does not mutate input.
    """
    if isinstance(obj, Mapping):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            key_str = str(k)
            lower = key_str.lower()
            if lower in _SENSITIVE_KEYS:
                out[key_str] = _redact_value(v)
            else:
                out[key_str] = _sanitize_structure(v)
        return out
    if isinstance(obj, list):
        return [_sanitize_structure(v) for v in obj]
    # Only allow JSON-safe primitive types; if not, coerce to string safely
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # Avoid bytes or other objects: convert to string in a safe deterministic way
    return str(obj)


def _safe_json_dumps(data: Any) -> str:
    # Deterministic JSON (sorted keys, no trailing spaces)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _safe_makedirs(path: str) -> None:
    # Ensure we do not traverse outside the intended storage root
    os.makedirs(path, exist_ok=True)
    # Prevent symlink escape
    if os.path.islink(path):
        raise StorageError(f"Storage path is a symbolic link and not allowed: {path}")


def _assert_within(parent: str, child: str) -> None:
    parent_real = os.path.realpath(parent)
    child_real = os.path.realpath(child)
    if os.path.commonpath([parent_real, child_real]) != parent_real:
        raise StorageError("Path traversal or symlink escape detected")


class ExecutionReportWriter:
    """Validates, sanitizes, and atomically persists mission execution reports.

    Public interface:
      - store_report(report)
      - validate_report(report)
      - get_report(execution_id)
      - status(project_id=None)
      - latest_events(limit, project_id=None)
    """

    def __init__(self, storage_dir: str, project_resolver: Callable[[str], Optional[str]]) -> None:
        if not _is_non_empty_str(storage_dir):
            raise ValueError("storage_dir must be a non-empty string")
        self._storage_root = os.path.abspath(storage_dir)
        _safe_makedirs(self._storage_root)
        # Subdirectories
        self._reports_dir = os.path.join(self._storage_root, "reports", "by-execution")
        self._events_dir = os.path.join(self._storage_root, "events")
        _safe_makedirs(self._reports_dir)
        _safe_makedirs(self._events_dir)
        _assert_within(self._storage_root, self._reports_dir)
        _assert_within(self._storage_root, self._events_dir)
        # Locks
        self._reports_lock = _InterProcessFileLock(os.path.join(self._storage_root, "locks", "reports.lock"))
        _safe_makedirs(os.path.dirname(self._reports_lock._path))  # ensure lock dir exists
        self._project_resolver = project_resolver
        # Per-process counter for event file uniqueness
        self._event_counter = 0
        self._event_counter_lock = threading.Lock()

    # ------------- Public API -------------

    def validate_report(self, report: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize an execution report.

        Returns a sanitized and redacted dictionary safe to persist.
        Does not mutate the input.
        """
        if not isinstance(report, Mapping):
            raise ValidationError("Report must be a mapping/dictionary")

        # Reject unknown fields
        for key in report.keys():
            if key not in _ALLOWED_FIELDS:
                raise ValidationError(f"Unknown field: {key}")

        sanitized: Dict[str, Any] = {}

        # Required minimal identifiers and status
        execution_id = _validate_id(report.get("execution_id"), "execution_id")
        project_id_raw = report.get("project_id")
        if not _is_non_empty_str(project_id_raw):
            raise ValidationError("Field 'project_id' must be a non-empty string")
        project_canonical = self._project_resolver(str(project_id_raw))
        if not _is_non_empty_str(project_canonical):
            raise ValidationError("Unknown or unresolved project_id")
        project_id = str(project_canonical)
        status = report.get("status")
        if not _is_non_empty_str(status):
            raise ValidationError("Field 'status' must be a non-empty string")
        status_l = str(status).lower().strip()
        if status_l not in _SUPPORTED_STATUSES:
            raise ValidationError(f"Unsupported status: {status}")
        success = report.get("success")
        if not _is_bool(success):
            raise ValidationError("Field 'success' must be boolean")

        # Time fields
        if "started_at" not in report or "completed_at" not in report:
            raise ValidationError("Fields 'started_at' and 'completed_at' are required")
        started_at_dt = _as_utc_datetime(report.get("started_at"), "started_at")
        completed_at_dt = _as_utc_datetime(report.get("completed_at"), "completed_at")
        if completed_at_dt < started_at_dt:
            raise ValidationError("'completed_at' must not be earlier than 'started_at'")

        # Logical consistency of status and success
        if status_l == "completed" and success is not True:
            raise ValidationError("Status 'completed' requires success=True")
        if status_l in {"failed", "blocked", "cancelled", "retrying"} and success is True:
            raise ValidationError(f"Status '{status_l}' requires success=False")

        # Optional booleans
        for bkey in ("retryable", "fallback_used"):
            if bkey in report and not _is_bool(report[bkey]):
                raise ValidationError(f"Field '{bkey}' must be boolean if provided")
        if status_l == "retrying" and not report.get("retryable", False):
            raise ValidationError("Status 'retrying' requires 'retryable'=True")

        # Token validation and normalization
        input_tokens = report.get("input_tokens")
        output_tokens = report.get("output_tokens")
        total_tokens = report.get("total_tokens")
        have_any_tokens = any(k in report for k in ("input_tokens", "output_tokens", "total_tokens"))
        if have_any_tokens:
            if not _is_non_negative_int(input_tokens):
                raise ValidationError("'input_tokens' must be a non-negative integer")
            if not _is_non_negative_int(output_tokens):
                raise ValidationError("'output_tokens' must be a non-negative integer")
            expected_total = int(input_tokens) + int(output_tokens)
            if total_tokens is None:
                total_tokens_val = expected_total
            else:
                if not _is_non_negative_int(total_tokens):
                    raise ValidationError("'total_tokens' must be a non-negative integer")
                if int(total_tokens) != expected_total:
                    raise ValidationError("'total_tokens' must equal 'input_tokens' + 'output_tokens'")
                total_tokens_val = int(total_tokens)
        else:
            total_tokens_val = None

        # Cost validation
        estimated_cost = report.get("estimated_cost")
        if estimated_cost is None:
            cost_val: Optional[float] = None
        else:
            if not _is_non_negative_number(estimated_cost):
                raise ValidationError("'estimated_cost' must be non-negative or null")
            # Normalize to float with fixed precision to avoid non-determinism
            cost_val = float(estimated_cost)
        cost_currency = report.get("cost_currency")
        if cost_val is not None and cost_currency is not None:
            if not _is_non_empty_str(cost_currency) or not _CURRENCY_PATTERN.match(cost_currency):
                raise ValidationError("'cost_currency' must be an uppercase alphabetic code (e.g. 'USD')")
        # If cost unknown, do not alter it; currency can be present or omitted.

        # changed_files validation
        changed_files_val: Optional[List[str]] = None
        if "changed_files" in report:
            cf = report.get("changed_files")
            if cf is None:
                changed_files_val = None
            elif isinstance(cf, list):
                out_files: List[str] = []
                for item in cf:
                    if not _is_safe_repo_relative_path(item):
                        raise ValidationError(f"Unsafe changed_files path: {item!r}")
                    out_files.append(str(item))
                changed_files_val = out_files
            else:
                raise ValidationError("'changed_files' must be a list of repository-relative paths")

        # Git info validation
        git_branch_val: Optional[str] = None
        if "git_branch" in report and report.get("git_branch") is not None:
            gb = str(report.get("git_branch"))
            if not _BRANCH_PATTERN.match(gb):
                raise ValidationError("'git_branch' contains invalid syntax")
            git_branch_val = gb
        git_commit_val: Optional[str] = None
        if "git_commit" in report and report.get("git_commit") is not None:
            gc = str(report.get("git_commit"))
            if not _COMMIT_PATTERN.match(gc):
                raise ValidationError("'git_commit' must be a hex commit id (7-64 chars)")
            git_commit_val = gc

        # Optional identifier-like fields when provided must be non-empty strings
        optional_id_fields = (
            "request_id",
            "conversation_id",
            "plan_id",
            "mission_id",
            "step_id",
            "task_type",
            "provider_id",
            "model_id",
            "worker_id",
            "safe_error_code",
            "validation_status",
        )
        for f in optional_id_fields:
            if f in report and report.get(f) is not None:
                _ = _validate_id(report.get(f), f)
                sanitized[f] = str(report.get(f)).strip()

        # Summary (plain string, avoid control chars)
        if "summary" in report and report.get("summary") is not None:
            if not isinstance(report.get("summary"), str):
                raise ValidationError("'summary' must be a string if provided")
            ssum = report.get("summary", "")
            if _contains_control_chars(ssum):
                # Replace control characters defensively
                cleaned = "".join(ch for ch in ssum if ord(ch) >= 32)
            else:
                cleaned = ssum
            # Limit size to a safe bound (e.g., 20k chars) deterministically
            sanitized["summary"] = cleaned[:20000]

        # Metadata: JSON-safe and redacted
        if "metadata" in report and report.get("metadata") is not None:
            meta = report.get("metadata")
            if not isinstance(meta, Mapping):
                raise ValidationError("'metadata' must be a dictionary if provided")
            meta_sanitized = _sanitize_structure(meta)
            # Ensure JSON-safe
            try:
                _ = _safe_json_dumps(meta_sanitized)
            except (TypeError, ValueError) as e:
                raise ValidationError("'metadata' contains non-JSON-serializable values") from e
            sanitized["metadata"] = meta_sanitized

        # Assign core fields (after validation)
        sanitized["execution_id"] = execution_id
        sanitized["project_id"] = project_id
        sanitized["status"] = status_l
        sanitized["success"] = bool(success)

        if "retryable" in report:
            sanitized["retryable"] = bool(report.get("retryable"))
        if "fallback_used" in report:
            sanitized["fallback_used"] = bool(report.get("fallback_used"))

        sanitized["started_at"] = _isoformat_utc(started_at_dt)
        sanitized["completed_at"] = _isoformat_utc(completed_at_dt)

        if have_any_tokens:
            sanitized["input_tokens"] = int(input_tokens)  # type: ignore[arg-type]
            sanitized["output_tokens"] = int(output_tokens)  # type: ignore[arg-type]
            sanitized["total_tokens"] = int(total_tokens_val)  # type: ignore[arg-type]

        if estimated_cost is None:
            sanitized["estimated_cost"] = None
        else:
            # Normalize to 6 decimal places for determinism
            sanitized["estimated_cost"] = float(round(cost_val if cost_val is not None else 0.0, 6))
        if cost_currency is not None:
            sanitized["cost_currency"] = str(cost_currency)

        if changed_files_val is not None:
            sanitized["changed_files"] = changed_files_val
        if git_branch_val is not None:
            sanitized["git_branch"] = git_branch_val
        if git_commit_val is not None:
            sanitized["git_commit"] = git_commit_val

        # Final redaction pass on the entire report to ensure no sensitive keys leak
        fully_sanitized = _sanitize_structure(sanitized)
        # Ensure deterministic JSON serializability
        try:
            _ = _safe_json_dumps(fully_sanitized)
        except Exception as e:  # pragma: no cover - extremely unlikely
            raise ValidationError(f"Sanitized report is not JSON-serializable: {e}") from e

        return fully_sanitized

    def store_report(self, report: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate, sanitize, and atomically persist a report.

        - Enforces duplicate detection atomically under a lock.
        - Returns the stored safe report, or the existing report if duplicate.
        - Emits events (after releasing the report-storage lock) for observability.
        """
        # Emit received event as early as possible with minimal safe details (no lock held)
        try:
            exec_id_for_event = None
            proj_for_event = None
            if isinstance(report, Mapping):
                if _is_non_empty_str(report.get("execution_id")):
                    exec_id_for_event = str(report.get("execution_id")).strip()
                if _is_non_empty_str(report.get("project_id")):
                    proj_for_event = str(report.get("project_id")).strip()
            self._emit_event("execution_report_received", {
                "execution_id": exec_id_for_event,
                "project_id": proj_for_event,
            })
        except Exception:
            # Events must never disrupt storage
            pass

        try:
            safe_report = self.validate_report(report)
        except ValidationError as ve:
            # Emit rejection event
            try:
                self._emit_event("execution_report_rejected", {
                    "reason": str(ve),
                    "execution_id": report.get("execution_id") if isinstance(report, Mapping) else None,
                    "project_id": report.get("project_id") if isinstance(report, Mapping) else None,
                })
            except Exception:
                pass
            raise

        execution_id = safe_report["execution_id"]
        report_path = self._report_path_for_execution(execution_id)

        # Persist atomically under lock
        duplicate = False
        existing: Optional[Dict[str, Any]] = None
        try:
            with self._reports_lock:
                # Ensure parent exists and safe
                parent = os.path.dirname(report_path)
                _safe_makedirs(parent)
                _assert_within(self._reports_dir, parent)

                if os.path.exists(report_path):
                    # Duplicate; read existing safely to return
                    existing = self._read_json_file(report_path)
                    duplicate = True
                else:
                    # Write to temporary deterministic JSON and atomically move into place
                    data = _safe_json_dumps(safe_report)
                    tmp_name = f".tmp-{execution_id}-{os.getpid()}-{secrets.token_hex(8)}.json"
                    tmp_path = os.path.join(parent, tmp_name)
                    _assert_within(self._reports_dir, tmp_path)
                    self._atomic_write(tmp_path, report_path, data)
        except Exception as e:
            # Emit store failed event after releasing the lock
            try:
                self._emit_event("execution_report_store_failed", {
                    "execution_id": execution_id,
                    "project_id": safe_report.get("project_id"),
                    "reason": str(e),
                })
            except Exception:
                pass
            # Re-raise as storage error to the caller if unexpected
            if isinstance(e, (ValidationError, StorageError)):
                raise
            raise StorageError(f"Failed to persist report: {e}") from e

        # Emit events (outside of lock)
        if duplicate:
            try:
                self._emit_event("duplicate_execution_detected", {
                    "execution_id": execution_id,
                    "project_id": (existing or safe_report).get("project_id"),
                })
            except Exception:
                pass
            return existing if existing is not None else safe_report
        else:
            try:
                self._emit_event("execution_report_persisted", {
                    "execution_id": execution_id,
                    "project_id": safe_report.get("project_id"),
                    "status": safe_report.get("status"),
                })
            except Exception:
                pass
            return safe_report

    def get_report(self, execution_id: str) -> Dict[str, Any]:
        eid = _validate_id(execution_id, "execution_id")
        path = self._report_path_for_execution(eid)
        if not os.path.exists(path):
            raise StorageError(f"Report not found for execution_id={eid}")
        return self._read_json_file(path)

    def status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a minimal status summary.

        - total_reports: number of stored reports (optionally filtered by project)
        - total_events: number of stored events (optionally filtered by project)
        - last_event_at: ISO UTC timestamp of the most recent event or None
        """
        proj_filter: Optional[str] = None
        if project_id is not None:
            if not _is_non_empty_str(project_id):
                raise ValidationError("project_id must be a non-empty string when provided")
            resolved = self._project_resolver(str(project_id))
            if not _is_non_empty_str(resolved):
                raise ValidationError("Unknown or unresolved project_id")
            proj_filter = str(resolved)

        total_reports = 0
        try:
            for name in os.listdir(self._reports_dir):
                if not name.endswith(".json"):
                    continue
                fpath = os.path.join(self._reports_dir, name)
                try:
                    data = self._read_json_file(fpath)
                except StorageError:
                    # Corrupted storage detected; raise to caller per specification
                    raise
                if proj_filter is None or data.get("project_id") == proj_filter:
                    total_reports += 1
        except FileNotFoundError:
            total_reports = 0

        total_events = 0
        last_event_at: Optional[str] = None
        try:
            names = [n for n in os.listdir(self._events_dir) if n.endswith(".json")]
            names.sort()
            for name in names:
                fpath = os.path.join(self._events_dir, name)
                try:
                    evt = self._read_json_file(fpath)
                except StorageError:
                    # Corruption: raise
                    raise
                if proj_filter is None or evt.get("project_id") == proj_filter:
                    total_events += 1
                    last_event_at = evt.get("ts", last_event_at)
        except FileNotFoundError:
            total_events = 0

        return {
            "total_reports": total_reports,
            "total_events": total_events,
            "last_event_at": last_event_at,
        }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValidationError("limit must be a positive integer")

        proj_filter: Optional[str] = None
        if project_id is not None:
            if not _is_non_empty_str(project_id):
                raise ValidationError("project_id must be a non-empty string when provided")
            resolved = self._project_resolver(str(project_id))
            if not _is_non_empty_str(resolved):
                raise ValidationError("Unknown or unresolved project_id")
            proj_filter = str(resolved)

        events: List[Tuple[str, str]] = []  # (name, path)
        try:
            for name in os.listdir(self._events_dir):
                if name.endswith(".json"):
                    events.append((name, os.path.join(self._events_dir, name)))
        except FileNotFoundError:
            return []
        events.sort(key=lambda x: x[0])

        result: List[Dict[str, Any]] = []
        for _, path in reversed(events):
            try:
                evt = self._read_json_file(path)
            except StorageError:
                raise
            if proj_filter is not None and evt.get("project_id") != proj_filter:
                continue
            result.append(evt)
            if len(result) >= limit:
                break
        return result

    # ------------- Internal helpers -------------

    def _report_path_for_execution(self, execution_id: str) -> str:
        safe_eid = _validate_id(execution_id, "execution_id")
        fname = f"{safe_eid}.json"
        path = os.path.join(self._reports_dir, fname)
        _assert_within(self._reports_dir, path)
        return path

    def _atomic_write(self, tmp_path: str, final_path: str, data: str) -> None:
        # Create temp file exclusively, write, fsync, and atomically replace
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        mode = 0o600
        fd: Optional[int] = None
        try:
            fd = os.open(tmp_path, flags, mode)
            b = data.encode("utf-8")
            total = 0
            while total < len(b):
                written = os.write(fd, b[total:])
                if written <= 0:
                    raise StorageError("Short write while persisting report")
                total += written
            os.fsync(fd)
        except FileExistsError:
            # Extremely unlikely temp name collision; retry once with a new name
            alt_tmp = tmp_path + "-" + secrets.token_hex(4)
            self._atomic_write(alt_tmp, final_path, data)
            return
        except OSError as e:
            raise StorageError(f"Failed to write temporary file: {e}") from e
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        try:
            os.replace(tmp_path, final_path)
        except OSError as e:
            # Clean up temp file if replace fails
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            # If target exists now, consider it as a race => duplicate
            if e.errno == errno.EEXIST and os.path.exists(final_path):
                return
            raise StorageError(f"Failed to move temporary file into place: {e}") from e

    def _emit_event(self, event_type: str, details: Mapping[str, Any]) -> None:
        event: Dict[str, Any] = {
            "type": str(event_type),
            "ts": _utc_now_iso(),
        }
        # Copy minimal fields deterministically and safely
        if isinstance(details, Mapping):
            # Redact and sanitize
            safe_details = _sanitize_structure(details)
            # Promote common fields to event top-level for easier filtering
            for k in ("execution_id", "project_id", "status"):
                if k in safe_details and k not in event:
                    event[k] = safe_details.get(k)
            event["details"] = safe_details
        else:
            event["details"] = str(details)
        # Serialize deterministically
        payload = _safe_json_dumps(event)
        # Unique deterministic-ish filename based on time and per-process counter
        with self._event_counter_lock:
            self._event_counter = (self._event_counter + 1) % 1_000_000_000
            seq = self._event_counter
        name = f"{event['ts'].replace(':', '').replace('-', '')}-{seq:09d}-{secrets.token_hex(4)}.json"
        path = os.path.join(self._events_dir, name)
        _assert_within(self._events_dir, path)
        # Write with O_EXCL to avoid accidental overwrite
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        mode = 0o600
        fd: Optional[int] = None
        try:
            fd = os.open(path, flags, mode)
            os.write(fd, payload.encode("utf-8"))
            os.fsync(fd)
        except FileExistsError:
            # Extremely unlikely; skip event rather than risk duplicate with lock nesting
            try:
                if fd is not None:
                    os.close(fd)
            except OSError:
                pass
            return
        except OSError:
            # Do not raise from event emission to avoid side effects
            try:
                if fd is not None:
                    os.close(fd)
            except OSError:
                pass
            return
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _read_json_file(self, path: str) -> Dict[str, Any]:
        _assert_within(self._storage_root, path)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            raise StorageError(f"Storage file not found: {path}")
        except OSError as e:
            raise StorageError(f"Failed to read storage file: {e}") from e
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise StorageError(f"Corrupted JSON in storage file: {path}") from e
        if not isinstance(data, dict):
            raise StorageError(f"Unexpected data in storage file (not a dict): {path}")
        return data


# End of module
