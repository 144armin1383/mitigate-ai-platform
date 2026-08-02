from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, TypedDict, Union

try:
    import fcntl  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore

try:
    import msvcrt  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore


# =====================
# Exceptions
# =====================

class LedgerError(Exception):
    pass


class DuplicateUsageError(LedgerError):
    pass


class LedgerValidationError(LedgerError):
    pass


class StorageCorruptedError(LedgerError):
    pass


class AccessError(LedgerError):
    pass


# =====================
# Types
# =====================

REQUIRED_FIELDS: Tuple[str, ...] = (
    "usage_id",
    "project_id",
    "request_id",
    "mission_id",
    "conversation_id",
    "task_type",
    "provider_id",
    "model_id",
    "started_at",
    "completed_at",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost",
    "cost_currency",
    "fallback_used",
    "success",
    "safe_error_code",
)

# Only these keys are persisted to respect privacy/security policy
SAFE_RECORD_KEYS: Tuple[str, ...] = REQUIRED_FIELDS

# Events
Event = Dict[str, Any]


class PricingInfo(TypedDict, total=False):
    currency: str
    input_per_token: float
    output_per_token: float
    # Optional single blended rate if resolver wants to provide only one
    per_token: float


# =====================
# Helpers
# =====================

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # trim microseconds to milliseconds for stable deterministic length
    ms = int(dt.microsecond / 1000)
    dt_trim = dt.replace(microsecond=ms * 1000)
    return dt_trim.strftime(_ISO_FORMAT)


def _parse_iso(s: str) -> datetime:
    # Accept ...Z or with +00:00; always return timezone-aware UTC
    if not isinstance(s, str) or not s:
        raise LedgerValidationError("Timestamp must be a non-empty string")
    try:
        if s.endswith("Z"):
            # fromisoformat cannot parse Z; replace
            base = s[:-1]
            # Support optional milliseconds
            dt = datetime.fromisoformat(base)
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
    except Exception as e:  # pragma: no cover - defensive
        raise LedgerValidationError(f"Invalid ISO timestamp: {s}") from e
    return dt


def _safe_int(name: str, v: Any) -> int:
    if not isinstance(v, int) or v < 0:
        raise LedgerValidationError(f"{name} must be a non-negative integer")
    return v


def _decimal_from_float(f: float) -> Decimal:
    # Convert via string to preserve determinism
    return Decimal(str(f))


def _quantize_money(d: Decimal) -> Decimal:
    # 1e-6 granularity for cost determinism
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# =====================
# File locking (cross-process) helpers
# =====================

class _FileLock:
    def __init__(self, path: Path, timeout: float = 2.0):
        self._path = path
        self._timeout = timeout
        self._fh: Optional[Any] = None

    def acquire(self) -> None:
        deadline = time.time() + self._timeout
        # Ensure directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Open lock file
        fh = open(self._path, "a+b")
        self._fh = fh
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                elif msvcrt is not None:  # pragma: no cover - Windows
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - very rare
                    # Fallback to no-op lock; still bounded time
                    pass
                break
            except (BlockingIOError, OSError):
                if time.time() > deadline:
                    fh.close()
                    self._fh = None
                    raise TimeoutError("Timeout acquiring file lock")
                time.sleep(0.01)

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
            elif msvcrt is not None:  # pragma: no cover - Windows
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            try:
                fh.close()
            finally:
                self._fh = None

    def __enter__(self) -> "_FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


# =====================
# ProviderUsageLedger
# =====================


class ProviderUsageLedger:
    """
    Provider-neutral usage ledger with deterministic JSON persistence and safe events.

    Pricing resolver signature: Callable[[str, str], Optional[PricingInfo]]
    - Returns None if unknown pricing.
    - May supply either per_token or input_per_token/output_per_token.

    Model resolver signature: Optional[Callable[[str, str], bool]]
    Project resolver signature: Callable[[str], bool]

    estimate_cost returns (estimated_cost: Optional[float], currency: Optional[str]).
    """

    _USAGE_FILE = "provider_usage.json"
    _EVENTS_FILE = "provider_events.json"
    _USAGE_LOCK_FILE = "provider_usage.lock"
    _EVENTS_LOCK_FILE = "provider_events.lock"

    def __init__(
        self,
        storage_dir: Union[str, Path],
        *,
        project_resolver: Callable[[str], bool],
        model_resolver: Optional[Callable[[str, str], bool]] = None,
        pricing_resolver: Optional[Callable[[str, str], Optional[PricingInfo]]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        id_generator: Optional[Callable[[], str]] = None,
        lock_timeout: float = 2.0,
    ) -> None:
        self._storage_dir = Path(storage_dir).resolve()
        self._project_resolver = project_resolver
        self._model_resolver = model_resolver
        self._pricing_resolver = pricing_resolver
        self._clock = clock or _utc_now
        self._id_generator = id_generator
        self._lock_timeout = float(lock_timeout)

        # Thread locks (non-reentrant)
        self._usage_lock = threading.Lock()
        self._event_lock = threading.Lock()

        # Paths
        self._usage_path = self._safe_file_path(self._USAGE_FILE)
        self._events_path = self._safe_file_path(self._EVENTS_FILE)
        self._usage_lock_path = self._safe_file_path(self._USAGE_LOCK_FILE)
        self._events_lock_path = self._safe_file_path(self._EVENTS_LOCK_FILE)

        # Initialize storage if missing; do not overwrite corrupted files
        self._init_files()

    # ---------------------
    # Public API
    # ---------------------

    def record_usage(self, record: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Validate and persist a usage record atomically. Emits usage_recorded or usage_rejected.

        This method may acquire the usage storage lock exactly once. Events are emitted only
        after the usage lock is released.
        """
        # Validate immutable/safe fields prior to acquiring usage lock when possible
        try:
            sanitized = self._sanitize_record_input(record)
            # Validate project early (does not persist)
            self._validate_project(sanitized["project_id"])
            # Validate provider/model if configured
            self._validate_provider_model(sanitized["provider_id"], sanitized["model_id"])  # may no-op
        except Exception as e:
            # Emit rejection event (no active usage lock)
            self._emit_event(
                "usage_rejected",
                {
                    "project_id": record.get("project_id", ""),
                    "usage_id": record.get("usage_id", ""),
                    "reason": type(e).__name__,
                    "message": str(e),
                },
            )
            raise

        # Compute estimated cost if not provided
        if sanitized.get("estimated_cost") is None:
            est_cost, currency = self.estimate_cost(
                sanitized["provider_id"],
                sanitized["model_id"],
                sanitized["input_tokens"],
                sanitized["output_tokens"],
            )
            sanitized["estimated_cost"] = est_cost
            sanitized["cost_currency"] = currency

        # Final validation of cost and timestamps
        if sanitized["estimated_cost"] is not None:
            if not isinstance(sanitized["estimated_cost"], (int, float)):
                raise LedgerValidationError("estimated_cost must be a non-negative number or null")
            if float(sanitized["estimated_cost"]) < 0:
                raise LedgerValidationError("estimated_cost must not be negative")
        # Timestamps already validated in _sanitize_record_input

        # Acquire usage locks and persist atomically
        with self._usage_lock:
            with _FileLock(self._usage_lock_path, timeout=self._lock_timeout):
                data = self._load_usage_nolock()
                # Enforce uniqueness of usage_id
                uid = sanitized["usage_id"]
                if any(r.get("usage_id") == uid for r in data["records"]):
                    # Do not modify state; release lock before emitting event
                    pass  # handled after release
                else:
                    # Append and write atomically
                    data["records"].append(self._persistable_record(sanitized))
                    data["updated_at"] = _to_iso_z(self._clock())
                    self._atomic_write_json(self._usage_path, data, ".provider_usage.json.tmp")
                    # Released after with-block
                    uid = None  # type: ignore[assignment]
                # end if
            # usage file lock is released here
            # Determine if duplicate
            if uid is not None and isinstance(uid, str):
                # Duplicate
                self._emit_event(
                    "usage_rejected",
                    {
                        "project_id": sanitized["project_id"],
                        "usage_id": sanitized["usage_id"],
                        "reason": "DuplicateUsageError",
                        "message": "Duplicate usage_id",
                    },
                )
                raise DuplicateUsageError("usage_id already exists")

        # Emit events after usage lock is released
        self._emit_event(
            "usage_recorded",
            {
                "project_id": sanitized["project_id"],
                "usage_id": sanitized["usage_id"],
                "provider_id": sanitized["provider_id"],
                "model_id": sanitized["model_id"],
                "input_tokens": sanitized["input_tokens"],
                "output_tokens": sanitized["output_tokens"],
                "total_tokens": sanitized["total_tokens"],
                "estimated_cost": sanitized["estimated_cost"],
                "currency": sanitized["cost_currency"],
                "success": sanitized["success"],
                "fallback_used": sanitized["fallback_used"],
            },
        )
        if sanitized.get("estimated_cost") is None:
            self._emit_event(
                "pricing_unknown",
                {
                    "project_id": sanitized["project_id"],
                    "usage_id": sanitized["usage_id"],
                    "provider_id": sanitized["provider_id"],
                    "model_id": sanitized["model_id"],
                    "input_tokens": sanitized["input_tokens"],
                    "output_tokens": sanitized["output_tokens"],
                },
            )

        return dict(sanitized)

    def estimate_cost(
        self,
        provider_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Tuple[Optional[float], Optional[str]]:
        if self._pricing_resolver is None:
            return None, None
        try:
            info = self._pricing_resolver(provider_id, model_id)
        except Exception as e:  # pragma: no cover - safe conversion
            raise LedgerValidationError("Pricing resolver error") from e
        if not info:
            return None, None
        currency = info.get("currency")
        per = info.get("per_token")
        if per is not None:
            inp_rate = out_rate = float(per)
        else:
            inp_rate = float(info.get("input_per_token", 0.0))
            out_rate = float(info.get("output_per_token", 0.0))
        # Compute with Decimal for determinism
        cost = _quantize_money(
            _decimal_from_float(inp_rate) * Decimal(int(input_tokens))
            + _decimal_from_float(out_rate) * Decimal(int(output_tokens))
        )
        return float(cost), currency

    def get_usage(self, usage_id: str) -> Optional[Mapping[str, Any]]:
        with self._usage_lock:
            data = self._load_usage_nolock()
            for r in data["records"]:
                if r.get("usage_id") == usage_id:
                    return dict(r)
        return None

    def list_usage(self, project_id: str, filters: Optional[Mapping[str, Any]] = None) -> List[Mapping[str, Any]]:
        self._validate_project(project_id)
        filters = dict(filters or {})
        with self._usage_lock:
            data = self._load_usage_nolock()
            res: List[Mapping[str, Any]] = []
            for r in data["records"]:
                if r.get("project_id") != project_id:
                    continue
                if not self._match_filters(r, filters):
                    continue
                res.append(dict(r))
            # Deterministic order
            res.sort(key=lambda x: (x.get("started_at", ""), x.get("usage_id", "")))
            return res

    def daily_summary(self, project_id: str, day: date) -> Mapping[str, Any]:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        summary = self.range_summary(project_id, start, end)
        self._emit_event(
            "usage_summary_created",
            {
                "project_id": project_id,
                "range": "daily",
                "start": _to_iso_z(start),
                "end": _to_iso_z(end),
                "request_count": summary["request_count"],
            },
        )
        return summary

    def monthly_summary(self, project_id: str, year: int, month: int) -> Mapping[str, Any]:
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        summary = self.range_summary(project_id, start, end)
        self._emit_event(
            "usage_summary_created",
            {
                "project_id": project_id,
                "range": "monthly",
                "start": _to_iso_z(start),
                "end": _to_iso_z(end),
                "request_count": summary["request_count"],
            },
        )
        return summary

    def range_summary(self, project_id: str, start: datetime, end: datetime) -> Mapping[str, Any]:
        self._validate_project(project_id)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        else:
            start = start.astimezone(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)
        # Inclusive start, exclusive end
        with self._usage_lock:
            data = self._load_usage_nolock()
            items = [
                r for r in data["records"]
                if r.get("project_id") == project_id and self._record_in_range(r, start, end)
            ]
        return self._aggregate_summary(items)

    def summary_by_provider(self, project_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[Mapping[str, Any]]:
        return self._summary_by_key(project_id, "provider_id", start, end)

    def summary_by_model(self, project_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[Mapping[str, Any]]:
        return self._summary_by_key(project_id, "model_id", start, end)

    def summary_by_task(self, project_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[Mapping[str, Any]]:
        return self._summary_by_key(project_id, "task_type", start, end)

    def status(self, project_id: Optional[str] = None) -> Mapping[str, Any]:
        with self._usage_lock:
            data = self._load_usage_nolock()
            records = data["records"]
            if project_id is not None:
                self._validate_project(project_id)
                recs = [r for r in records if r.get("project_id") == project_id]
            else:
                recs = list(records)
            projects = sorted({r.get("project_id") for r in recs})
        return {
            "projects": projects,
            "total_projects": len(projects),
            "total_records": len(recs),
            "storage": {
                "dir": str(self._storage_dir),
                "usage_file": str(self._usage_path.name),
                "events_file": str(self._events_path.name),
            },
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Event]:
        if not isinstance(limit, int) or limit < 0:
            raise LedgerValidationError("limit must be a non-negative integer")
        with self._event_lock:
            events = self._load_events_nolock()
            if project_id is not None:
                events = [e for e in events if e.get("project_id") == project_id]
            # Deterministic ordering: sort by (timestamp asc, type asc) then take last limit and reverse
            events.sort(key=lambda e: (e.get("timestamp", ""), e.get("type", "")))
            if limit == 0:
                return []
            latest = events[-limit:]
            latest.reverse()
            return latest

    # ---------------------
    # Internal helpers (no nested public locks)
    # ---------------------

    def _init_files(self) -> None:
        # Ensure storage dir
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # Initialize usage file if missing
        if not self._usage_path.exists():
            data = {
                "version": 1,
                "created_at": _to_iso_z(self._clock()),
                "updated_at": _to_iso_z(self._clock()),
                "records": [],
            }
            self._atomic_write_json(self._usage_path, data, ".provider_usage.json.tmp")
        # Initialize events file if missing
        if not self._events_path.exists():
            self._atomic_write_json(self._events_path, [], ".provider_events.json.tmp")

    def _sanitize_record_input(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        # Required keys present
        for k in REQUIRED_FIELDS:
            if k not in record:
                raise LedgerValidationError(f"Missing required field: {k}")
        # Enforce types and constraints
        usage_id = str(record["usage_id"]) if record.get("usage_id") is not None else ""
        if usage_id == "":
            raise LedgerValidationError("usage_id must be a non-empty string")
        project_id = str(record["project_id"]) if record.get("project_id") is not None else ""
        if project_id == "":
            raise LedgerValidationError("project_id must be a non-empty string")
        provider_id = str(record["provider_id"])
        model_id = str(record["model_id"])
        task_type = str(record["task_type"]) if record.get("task_type") is not None else ""
        request_id = str(record["request_id"]) if record.get("request_id") is not None else ""
        mission_id = str(record["mission_id"]) if record.get("mission_id") is not None else ""
        conversation_id = str(record["conversation_id"]) if record.get("conversation_id") is not None else ""

        started_at = _parse_iso(str(record["started_at"]))
        completed_at = _parse_iso(str(record["completed_at"]))
        if completed_at < started_at:
            raise LedgerValidationError("completed_at must not be earlier than started_at")

        input_tokens = _safe_int("input_tokens", record["input_tokens"])
        output_tokens = _safe_int("output_tokens", record["output_tokens"])
        total_tokens = _safe_int("total_tokens", record["total_tokens"])
        if total_tokens != input_tokens + output_tokens:
            raise LedgerValidationError("total_tokens must equal input_tokens + output_tokens")

        estimated_cost = record.get("estimated_cost")
        if estimated_cost is not None:
            if not isinstance(estimated_cost, (int, float)):
                raise LedgerValidationError("estimated_cost must be a number or null")
            if float(estimated_cost) < 0:
                raise LedgerValidationError("estimated_cost must not be negative")

        cost_currency = record.get("cost_currency")
        if cost_currency is not None:
            cost_currency = str(cost_currency)
            if cost_currency == "":
                cost_currency = None

        fallback_used = record.get("fallback_used")
        if not isinstance(fallback_used, bool):
            raise LedgerValidationError("fallback_used must be boolean")

        success = record.get("success")
        if not isinstance(success, bool):
            raise LedgerValidationError("success must be boolean")

        safe_error_code = str(record.get("safe_error_code", "") or "")

        sanitized = {
            "usage_id": usage_id,
            "project_id": project_id,
            "request_id": request_id,
            "mission_id": mission_id,
            "conversation_id": conversation_id,
            "task_type": task_type,
            "provider_id": provider_id,
            "model_id": model_id,
            "started_at": _to_iso_z(started_at),
            "completed_at": _to_iso_z(completed_at),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": float(estimated_cost) if estimated_cost is not None else None,
            "cost_currency": cost_currency,
            "fallback_used": fallback_used,
            "success": success,
            "safe_error_code": safe_error_code,
        }
        return sanitized

    def _validate_project(self, project_id: str) -> None:
        try:
            ok = bool(self._project_resolver(project_id))
        except Exception as e:  # pragma: no cover - defensive
            raise LedgerValidationError("Project resolver error") from e
        if not ok:
            raise LedgerValidationError("Unknown project")

    def _validate_provider_model(self, provider_id: str, model_id: str) -> None:
        if self._model_resolver is None:
            return
        try:
            ok = bool(self._model_resolver(provider_id, model_id))
        except Exception as e:  # pragma: no cover - defensive
            raise LedgerValidationError("Model resolver error") from e
        if not ok:
            raise LedgerValidationError("Unknown provider or model")

    def _match_filters(self, r: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
        for key in ("provider_id", "model_id", "task_type"):
            v = filters.get(key)
            if v is not None and r.get(key) != v:
                return False
        for key in ("success", "fallback_used"):
            v = filters.get(key)
            if v is not None:
                if not isinstance(v, bool):
                    raise LedgerValidationError(f"Filter {key} must be boolean if provided")
                if bool(r.get(key)) != v:
                    return False
        return True

    def _record_in_range(self, r: Mapping[str, Any], start: datetime, end: datetime) -> bool:
        ra = _parse_iso(r.get("started_at", ""))
        # inclusive start, exclusive end based on started_at
        return (ra >= start) and (ra < end)

    def _aggregate_summary(self, items: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        req_count = len(items)
        succ = sum(1 for r in items if r.get("success") is True)
        fail = req_count - succ
        input_tokens = sum(int(r.get("input_tokens", 0) or 0) for r in items)
        output_tokens = sum(int(r.get("output_tokens", 0) or 0) for r in items)
        total_tokens = sum(int(r.get("total_tokens", 0) or 0) for r in items)
        # Costs by currency
        costs: Dict[str, Decimal] = {}
        unknown_cost_count = 0
        for r in items:
            cost = r.get("estimated_cost")
            currency = r.get("cost_currency")
            if cost is None or currency in (None, ""):
                unknown_cost_count += 1
                continue
            key = str(currency)
            d = _decimal_from_float(float(cost))
            costs[key] = costs.get(key, Decimal(0)) + d
        # Quantize for determinism
        out_costs: Dict[str, float] = {}
        for k in sorted(costs.keys()):  # deterministic order
            out_costs[k] = float(_quantize_money(costs[k]))
        fallback_count = sum(1 for r in items if r.get("fallback_used") is True)
        return {
            "request_count": req_count,
            "successful_requests": succ,
            "failed_requests": fail,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_costs": out_costs,
            "unknown_cost_count": unknown_cost_count,
            "fallback_count": fallback_count,
        }

    def _summary_by_key(
        self, project_id: str, key: str, start: Optional[datetime], end: Optional[datetime]
    ) -> List[Mapping[str, Any]]:
        self._validate_project(project_id)
        if start is None:
            start = datetime.min.replace(tzinfo=timezone.utc)
        else:
            start = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
        if end is None:
            end = datetime.max.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)
        with self._usage_lock:
            data = self._load_usage_nolock()
            items = [
                r for r in data["records"]
                if r.get("project_id") == project_id and self._record_in_range(r, start, end)
            ]
        # Group by key and currency buckets
        buckets: Dict[Tuple[str, Optional[str]], List[Mapping[str, Any]]] = {}
        for r in items:
            group = str(r.get(key, ""))
            currency = r.get("cost_currency")
            buckets.setdefault((group, currency), []).append(r)
        rows: List[Mapping[str, Any]] = []
        for (group, currency), recs in buckets.items():
            s = self._aggregate_summary(recs)
            # For group rows, present single currency bucket per row; pick matching currency's total
            est_cost_val: Optional[float]
            if currency in (None, ""):
                est_cost_val = None
            else:
                est_cost_val = s["estimated_costs"].get(str(currency))
            row = {
                key: group,
                "currency": currency,
                "request_count": s["request_count"],
                "successful_requests": s["successful_requests"],
                "failed_requests": s["failed_requests"],
                "input_tokens": s["input_tokens"],
                "output_tokens": s["output_tokens"],
                "total_tokens": s["total_tokens"],
                "estimated_cost": est_cost_val,
                "unknown_cost_count": s["unknown_cost_count"],
                "fallback_count": s["fallback_count"],
            }
            rows.append(row)
        # Deterministic ordering by group then currency (None last)
        rows.sort(key=lambda r: (str(r.get(key) or ""), "~" if r.get("currency") in (None, "") else str(r.get("currency"))))
        return rows

    # ---------------------
    # Persistence helpers
    # ---------------------

    def _safe_file_path(self, name: Union[str, Path]) -> Path:
        # Validate file names (reject traversal, absolute, control chars). Allow internal temp files starting with dot and ending with .tmp
        if isinstance(name, Path):
            name = name.name
        if not isinstance(name, str) or name == "":
            raise LedgerValidationError("Invalid file name")
        if "/" in name or "\\" in name:
            raise LedgerValidationError("Invalid file name")
        if name.startswith(".."):
            raise LedgerValidationError("Invalid file name")
        for ch in name:
            if ord(ch) < 32:  # control characters
                raise LedgerValidationError("Invalid file name")
        # Resolve path and ensure within storage_dir
        p = (self._storage_dir / name)
        rp = p.resolve()
        if not str(rp).startswith(str(self._storage_dir)):
            raise LedgerValidationError("Path escape detected")
        # Disallow existing symlinks
        if p.exists() and p.is_symlink():
            raise LedgerValidationError("Symlink not allowed")
        return rp

    def _atomic_write_json(self, path: Path, data: Any, tmp_name: str) -> None:
        # tmp_name validated but may start with dot and end with .tmp
        tmp_path = self._safe_file_path(tmp_name)
        # Ensure same directory
        if tmp_path.parent != self._storage_dir:
            raise LedgerError("Temporary file must be in storage directory")
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        f = None
        try:
            f = open(tmp_path, "w", encoding="utf-8")
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
            f.close()
            f = None
            os.replace(tmp_path, path)
            # fsync directory for durability
            try:
                dir_fd = os.open(self._storage_dir, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
        except Exception:
            try:
                if f is not None:
                    try:
                        f.close()
                    except Exception:
                        pass
                if tmp_path.exists():
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            finally:
                raise

    def _load_usage_nolock(self) -> Dict[str, Any]:
        try:
            with open(self._usage_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "records" not in data or not isinstance(data["records"], list):
                raise StorageCorruptedError("Usage storage format invalid")
            return data
        except json.JSONDecodeError as e:
            raise StorageCorruptedError("Usage storage is corrupted") from e

    def _load_events_nolock(self) -> List[Event]:
        try:
            with open(self._events_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                raise StorageCorruptedError("Events storage format invalid")
            return data
        except json.JSONDecodeError as e:
            raise StorageCorruptedError("Events storage is corrupted") from e
        except FileNotFoundError:
            # Should not happen as _init_files ensures existence; but recover gracefully
            return []

    def _persistable_record(self, r: Mapping[str, Any]) -> Dict[str, Any]:
        # Only keep safe keys
        out: Dict[str, Any] = {}
        for k in SAFE_RECORD_KEYS:
            out[k] = r.get(k)
        return out

    def _emit_event(self, etype: str, payload: Mapping[str, Any]) -> None:
        # Never acquire usage storage lock here. Only event lock.
        event: Event = {
            "type": etype,
            "timestamp": _to_iso_z(self._clock()),
        }
        # Only persist safe scalar metadata
        for k, v in payload.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                event[k] = v
            else:
                # Convert to safe string representation
                event[k] = str(v)
        with self._event_lock:
            with _FileLock(self._events_lock_path, timeout=self._lock_timeout):
                events = self._load_events_nolock()
                events.append(event)
                self._atomic_write_json(self._events_path, events, ".provider_events.json.tmp")


__all__ = [
    "ProviderUsageLedger",
    "LedgerError",
    "DuplicateUsageError",
    "LedgerValidationError",
    "StorageCorruptedError",
    "AccessError",
]
