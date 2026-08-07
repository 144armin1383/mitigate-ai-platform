from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Sequence, Tuple, Union
import hashlib
import json
import re


# =============================
# Enums and Constants
# =============================


class MemoryRecordType(str, Enum):
    PROJECT_SNAPSHOT = "project_snapshot"
    ARCHITECTURE_DECISION = "architecture_decision"
    DEVELOPMENT_DECISION = "development_decision"
    COMPLETED_WORK = "completed_work"
    PENDING_WORK = "pending_work"
    FAILED_ATTEMPT = "failed_attempt"
    KNOWN_ISSUE = "known_issue"
    DEPLOYMENT_EVENT = "deployment_event"
    AUTONOMOUS_RUN_SUMMARY = "autonomous_run_summary"
    VALIDATION_SUMMARY = "validation_summary"
    PROVIDER_USAGE_SUMMARY = "provider_usage_summary"
    SECURITY_CONSTRAINT = "security_constraint"
    OPERATIONAL_CONSTRAINT = "operational_constraint"
    PROJECT_PREFERENCE = "project_preference"
    NEXT_ACTION = "next_action"
    HANDOFF_NOTE = "handoff_note"
    MIGRATION_NOTE = "migration_note"
    ROLLBACK_NOTE = "rollback_note"
    INCIDENT_SUMMARY = "incident_summary"


class HandoffStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"
    INVALID = "invalid"


# =============================
# Utility Interfaces
# =============================


class Clock(Protocol):
    def now(self) -> datetime:  # UTC
        ...


class IdGenerator(Protocol):
    def new_id(self, prefix: str | None = None) -> str:
        ...

    def deterministic_id(self, prefix: str, payload: Mapping[str, Any]) -> str:
        ...


class EventEmitter(Protocol):
    def emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
        ...


class Exporter(Protocol):
    def write_file(self, path: str, content: str) -> None:
        """Write content to repository-managed path. Must be safe and non-destructive.
        Implementations must ensure no unrestricted filesystem paths are allowed.
        """
        ...


# =============================
# Configuration
# =============================


@dataclass(frozen=True)
class RetentionPolicy:
    recent_detailed_limit: int = 500
    historical_summaries_limit: int = 2000
    provider_usage_limit: int = 1000
    validation_summaries_limit: int = 1000
    autonomous_run_summaries_limit: int = 1000


@dataclass(frozen=True)
class ProjectMemoryConfig:
    schema_version: str = "1.0.0"
    redaction_keys: Tuple[str, ...] = (
        "password",
        "secret",
        "token",
        "api_key",
        "authorization",
        "credential",
        "private_key",
        "access_key",
        "refresh_token",
        "session",
        "cookie",
    )
    max_record_bytes: int = 262144  # 256 KiB
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)


# =============================
# Data Models
# =============================


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    project_id: str
    type: MemoryRecordType
    created_at: datetime
    created_by: Optional[str]
    supersedes: Optional[str]
    related_records: Tuple[str, ...]
    data: Mapping[str, Any]
    preserve: bool = False


# ADR-style decision record
class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    project_id: str
    title: str
    context: str
    decision: str
    rationale: str
    alternatives_considered: Tuple[str, ...]
    consequences: str
    status: DecisionStatus
    supersedes: Optional[str]
    related_records: Tuple[str, ...]
    created_at: datetime
    created_by: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_memory_record(self) -> MemoryRecord:
        payload: Dict[str, Any] = {
            "decision_id": self.decision_id,
            "title": self.title,
            "context": self.context,
            "decision": self.decision,
            "rationale": self.rationale,
            "alternatives_considered": list(self.alternatives_considered),
            "consequences": self.consequences,
            "status": self.status.value,
            "metadata": dict(self.metadata),
        }
        return MemoryRecord(
            record_id=self.decision_id,
            project_id=self.project_id,
            type=MemoryRecordType.ARCHITECTURE_DECISION,
            created_at=self.created_at,
            created_by=self.created_by,
            supersedes=self.supersedes,
            related_records=self.related_records,
            data=payload,
        )


class WorkStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class WorkRecord:
    work_id: str
    project_id: str
    title: str
    summary: str
    objective: Optional[str]
    status: WorkStatus
    branch: Optional[str]
    commits: Tuple[str, ...]
    changed_files: Tuple[str, ...]
    tests_run: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    retry_count: int
    risk_level: Optional[str]
    approval_state: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    related_run_id: Optional[str]
    related_plan_id: Optional[str]
    related_mission_ids: Tuple[str, ...]
    warnings: Tuple[str, ...]
    next_action: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_memory_record(self) -> MemoryRecord:
        payload: Dict[str, Any] = {
            "work_id": self.work_id,
            "title": self.title,
            "summary": self.summary,
            "objective": self.objective,
            "status": self.status.value,
            "branch": self.branch,
            "commits": list(self.commits),
            "changed_files": list(self.changed_files),
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "retry_count": self.retry_count,
            "risk_level": self.risk_level,
            "approval_state": self.approval_state,
            "started_at": _dt_or_none(self.started_at),
            "completed_at": _dt_or_none(self.completed_at),
            "related_run_id": self.related_run_id,
            "related_plan_id": self.related_plan_id,
            "related_mission_ids": list(self.related_mission_ids),
            "warnings": list(self.warnings),
            "next_action": self.next_action,
            "metadata": dict(self.metadata),
        }
        rtype = (
            MemoryRecordType.COMPLETED_WORK
            if self.status == WorkStatus.COMPLETED
            else (
                MemoryRecordType.PENDING_WORK
                if self.status in (WorkStatus.PLANNED, WorkStatus.IN_PROGRESS, WorkStatus.BLOCKED)
                else MemoryRecordType.FAILED_ATTEMPT if self.status == WorkStatus.FAILED else MemoryRecordType.PENDING_WORK
            )
        )
        return MemoryRecord(
            record_id=self.work_id,
            project_id=self.project_id,
            type=rtype,
            created_at=datetime.now(timezone.utc),
            created_by=None,
            supersedes=None,
            related_records=tuple(),
            data=payload,
        )


class IssueStatus(str, Enum):
    OPEN = "open"
    MONITORING = "monitoring"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    ACCEPTED_RISK = "accepted_risk"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class IssueRecord:
    issue_id: str
    project_id: str
    title: str
    severity: Severity
    status: IssueStatus
    safe_description: str
    first_seen_at: datetime
    last_seen_at: datetime
    affected_components: Tuple[str, ...]
    workaround: Optional[str]
    planned_fix: Optional[str]
    related_records: Tuple[str, ...]

    def to_memory_record(self) -> MemoryRecord:
        payload: Dict[str, Any] = {
            "issue_id": self.issue_id,
            "title": self.title,
            "severity": self.severity.value,
            "status": self.status.value,
            "safe_description": self.safe_description,
            "first_seen_at": _dt_or_none(self.first_seen_at),
            "last_seen_at": _dt_or_none(self.last_seen_at),
            "affected_components": list(self.affected_components),
            "workaround": self.workaround,
            "planned_fix": self.planned_fix,
        }
        return MemoryRecord(
            record_id=self.issue_id,
            project_id=self.project_id,
            type=MemoryRecordType.KNOWN_ISSUE,
            created_at=datetime.now(timezone.utc),
            created_by=None,
            supersedes=None,
            related_records=self.related_records,
            data=payload,
        )


@dataclass(frozen=True)
class HandoffBundle:
    schema_version: str
    bundle_id: str
    generated_at: datetime
    project_id: str
    project_summary: Mapping[str, Any]
    architecture_summary: Mapping[str, Any]
    accepted_architecture_decisions: Tuple[Mapping[str, Any], ...]
    active_constraints: Mapping[str, Any]
    development_policy: Mapping[str, Any]
    security_policy_summary: Mapping[str, Any]
    deployment_policy_summary: Mapping[str, Any]
    portability_policy: Mapping[str, Any]
    provider_neutral_operating_instructions: Tuple[str, ...]
    completed_work: Tuple[Mapping[str, Any], ...]
    pending_work: Tuple[Mapping[str, Any], ...]
    blocked_work: Tuple[Mapping[str, Any], ...]
    known_issues: Tuple[Mapping[str, Any], ...]
    failed_attempts_to_avoid: Tuple[Mapping[str, Any], ...]
    current_branch_state: Mapping[str, Any]
    latest_validation_summary: Optional[Mapping[str, Any]]
    latest_test_summary: Optional[Mapping[str, Any]]
    latest_deployment_summary: Optional[Mapping[str, Any]]
    recent_autonomous_run_summaries: Tuple[Mapping[str, Any], ...]
    next_recommended_actions: Tuple[str, ...]
    required_approvals: Tuple[str, ...]
    warnings: Tuple[str, ...]
    record_references: Tuple[str, ...]
    status: HandoffStatus

    def to_json(self) -> str:
        return _stable_json_dumps(_jsonify_datetime(asdict(self)))


# =============================
# Storage Interface and In-Memory Implementation
# =============================


class ProjectMemoryStore(Protocol):
    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        ...

    def get_record(self, project_id: str, record_id: str) -> Optional[MemoryRecord]:
        ...

    def list_records(self, project_id: str) -> Tuple[MemoryRecord, ...]:
        ...

    def find_by_type(self, project_id: str, rtype: MemoryRecordType) -> Tuple[MemoryRecord, ...]:
        ...

    def find_related(self, project_id: str, record_id: str) -> Tuple[MemoryRecord, ...]:
        ...

    def get_latest_snapshot(self, project_id: str) -> Optional[MemoryRecord]:
        ...

    def write_snapshot(self, snapshot: MemoryRecord) -> MemoryRecord:
        ...

    def export_handoff(self, project_id: str, bundle: HandoffBundle) -> None:
        ...

    def load_handoff(self, project_id: str) -> Optional[HandoffBundle]:
        ...

    def health(self) -> Mapping[str, Any]:
        ...


class InMemoryProjectMemoryStore(ProjectMemoryStore):
    """Thread-safe, append-only in-memory store for compatibility and testing.
    Not persistent beyond process lifetime.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_project: Dict[str, Dict[str, MemoryRecord]] = {}
        self._by_project_order: Dict[str, List[str]] = {}
        self._handoffs: Dict[str, HandoffBundle] = {}

    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            pmap = self._by_project.setdefault(record.project_id, {})
            order = self._by_project_order.setdefault(record.project_id, [])
            existing = pmap.get(record.record_id)
            if existing is not None:
                # Idempotent write check
                if _records_equal(existing, record):
                    return existing
                raise ValueError("Record ID collision with differing content")
            pmap[record.record_id] = record
            order.append(record.record_id)
            return record

    def get_record(self, project_id: str, record_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            return self._by_project.get(project_id, {}).get(record_id)

    def list_records(self, project_id: str) -> Tuple[MemoryRecord, ...]:
        with self._lock:
            pmap = self._by_project.get(project_id, {})
            order = self._by_project_order.get(project_id, [])
            return tuple(pmap[rid] for rid in order)

    def find_by_type(self, project_id: str, rtype: MemoryRecordType) -> Tuple[MemoryRecord, ...]:
        return tuple(r for r in self.list_records(project_id) if r.type == rtype)

    def find_related(self, project_id: str, record_id: str) -> Tuple[MemoryRecord, ...]:
        return tuple(r for r in self.list_records(project_id) if record_id in r.related_records or r.supersedes == record_id)

    def get_latest_snapshot(self, project_id: str) -> Optional[MemoryRecord]:
        snaps = self.find_by_type(project_id, MemoryRecordType.PROJECT_SNAPSHOT)
        return snaps[-1] if snaps else None

    def write_snapshot(self, snapshot: MemoryRecord) -> MemoryRecord:
        if snapshot.type != MemoryRecordType.PROJECT_SNAPSHOT:
            raise ValueError("Snapshot must be of type project_snapshot")
        return self.append_record(snapshot)

    def export_handoff(self, project_id: str, bundle: HandoffBundle) -> None:
        with self._lock:
            self._handoffs[project_id] = bundle

    def load_handoff(self, project_id: str) -> Optional[HandoffBundle]:
        with self._lock:
            return self._handoffs.get(project_id)

    def health(self) -> Mapping[str, Any]:
        with self._lock:
            projects = len(self._by_project)
            records = sum(len(v) for v in self._by_project.values())
        return {"status": "ok", "projects": projects, "records": records}


# =============================
# Defaults for Clock, ID, Events
# =============================


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class DeterministicIdGen:
    def new_id(self, prefix: str | None = None) -> str:
        raw = f"{datetime.now(timezone.utc).timestamp()}-{hashlib.sha256(str(id(self)).encode()).hexdigest()}"
        hid = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix+'_' if prefix else ''}{hid}"

    def deterministic_id(self, prefix: str, payload: Mapping[str, Any]) -> str:
        digest = hashlib.sha256(_stable_json_dumps(payload).encode()).hexdigest()[:24]
        return f"{prefix}_{digest}"


class SafeEventEmitter:
    def __init__(self) -> None:
        self._lock = RLock()
        self._events: List[Tuple[str, Mapping[str, Any]]] = []

    def emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
        # Ensure payload is safe and small; do not block
        safe_payload = dict(payload)
        with self._lock:
            self._events.append((event_type, safe_payload))

    @property
    def events(self) -> Tuple[Tuple[str, Mapping[str, Any]], ...]:
        with self._lock:
            return tuple(self._events)


# =============================
# Helpers: Redaction, JSON, Size Control
# =============================


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(^|[_\-])(?:(?:pass)?word|secret|token|api[_\-]?key|authorization|credential|private[_\-]?key|access[_\-]?key|refresh[_\-]?token|session|cookie)([_\-]|$)",
    flags=re.IGNORECASE,
)


def _redact(obj: Any, redaction_keys: Sequence[str]) -> Any:
    # Merge configured keys with built-in pattern
    keys_set = {k.lower() for k in redaction_keys}

    def _redact_inner(value: Any) -> Any:
        if isinstance(value, Mapping):
            out: Dict[str, Any] = {}
            for k, v in value.items():
                if (
                    k.lower() in keys_set
                    or _SENSITIVE_KEY_PATTERN.search(k) is not None
                ):
                    out[k] = "[redacted]"
                else:
                    out[k] = _redact_inner(v)
            return out
        if isinstance(value, list):
            return [_redact_inner(v) for v in value]
        if isinstance(value, tuple):
            return tuple(_redact_inner(v) for v in value)
        return value

    return _redact_inner(obj)


def _stable_json_dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _jsonify_datetime(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc).isoformat()
    if isinstance(val, Mapping):
        return {k: _jsonify_datetime(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_jsonify_datetime(v) for v in val]
    if isinstance(val, tuple):
        return tuple(_jsonify_datetime(v) for v in val)
    return val


def _dt_or_none(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if isinstance(dt, datetime) else None


def _bounded_payload(data: Mapping[str, Any], max_bytes: int) -> Mapping[str, Any]:
    s = _stable_json_dumps(_jsonify_datetime(data))
    if len(s.encode()) <= max_bytes:
        return data

    # Truncate strategy: shorten long strings and lists
    def _truncate(value: Any, budget: int) -> Any:
        if budget <= 0:
            return "[truncated]"
        if isinstance(value, str):
            enc = value.encode()
            if len(enc) <= budget:
                return value
            # keep both ends
            keep = max(16, budget // 2)
            head = enc[: keep // 2].decode(errors="ignore")
            tail = enc[-keep // 2 :].decode(errors="ignore")
            return f"{head}...[truncated]...{tail}"
        if isinstance(value, list):
            if not value:
                return []
            # proportionally keep items
            keep_n = max(1, min(len(value), budget // 256))
            return [
                _truncate(v, max(0, budget // max(1, keep_n))) for v in value[:keep_n]
            ] + (["[truncated]"] if keep_n < len(value) else [])
        if isinstance(value, Mapping):
            out: Dict[str, Any] = {}
            items = list(value.items())
            # sort keys for determinism
            items.sort(key=lambda kv: str(kv[0]))
            each_budget = max(64, budget // max(1, len(items)))
            for k, v in items:
                out[k] = _truncate(v, each_budget)
            return out
        # scalars
        return value

    truncated = _truncate(data, max_bytes)
    # As a last check
    if len(_stable_json_dumps(_jsonify_datetime(truncated)).encode()) > max_bytes:
        return {"summary": "payload truncated to fit size limit"}
    return truncated


def _records_equal(a: MemoryRecord, b: MemoryRecord) -> bool:
    return (
        a.record_id == b.record_id
        and a.project_id == b.project_id
        and a.type == b.type
        and a.supersedes == b.supersedes
        and a.related_records == b.related_records
        and _stable_json_dumps(_jsonify_datetime(a.data))
        == _stable_json_dumps(_jsonify_datetime(b.data))
        and a.preserve == b.preserve
    )


# =============================
# Project Memory Manager
# =============================


@dataclass(frozen=True)
class _Deps:
    store: ProjectMemoryStore
    clock: Clock
    ids: IdGenerator
    events: EventEmitter


class ProjectMemoryManager:
    def __init__(self, config: ProjectMemoryConfig, deps: _Deps) -> None:
        self._config = config
        self._store = deps.store
        self._clock = deps.clock
        self._ids = deps.ids
        self._events = deps.events
        self._lock = RLock()

    # ------------- Core operations -------------
    def create_record(
        self,
        *,
        project_id: str,
        rtype: MemoryRecordType,
        data: Mapping[str, Any],
        created_by: Optional[str] = None,
        supersedes: Optional[str] = None,
        related_records: Optional[Sequence[str]] = None,
        preserve: bool = False,
    ) -> MemoryRecord:
        redacted = _redact(data, self._config.redaction_keys)
        bounded = _bounded_payload(redacted, self._config.max_record_bytes)

        with self._lock:
            # Validate references are project-scoped and no circular supersedes for ADR chains
            rel = tuple(sorted(set(related_records or ())))
            if supersedes is not None:
                self._validate_reference(project_id, supersedes)
            for rid in rel:
                self._validate_reference(project_id, rid)

            # Deterministic ID for idempotency
            pid_payload = {
                "project_id": project_id,
                "type": rtype.value,
                "data": bounded,
                "supersedes": supersedes,
                "related_records": list(rel),
            }
            record_id = self._ids.deterministic_id("mem", pid_payload)
            now = self._clock.now()
            record = MemoryRecord(
                record_id=record_id,
                project_id=project_id,
                type=rtype,
                created_at=now,
                created_by=created_by,
                supersedes=supersedes,
                related_records=rel,
                data=bounded,
                preserve=preserve,
            )
            appended = self._store.append_record(record)

        self._events.emit(
            "memory_record_created",
            {
                "project_id": project_id,
                "record_id": appended.record_id,
                "record_type": appended.type.value,
                "timestamp": _dt_or_none(appended.created_at),
            },
        )

        if supersedes:
            self._events.emit(
                "memory_record_superseded",
                {
                    "project_id": project_id,
                    "record_id": appended.record_id,
                    "superseded_id": supersedes,
                    "record_type": appended.type.value,
                    "timestamp": _dt_or_none(appended.created_at),
                },
            )
        return appended

    def get_record(self, project_id: str, record_id: str) -> Optional[MemoryRecord]:
        return self._store.get_record(project_id, record_id)

    def list_records(self, project_id: str) -> Tuple[MemoryRecord, ...]:
        return self._store.list_records(project_id)

    # ------------- ADR operations -------------
    def record_architecture_decision(self, adr: DecisionRecord) -> MemoryRecord:
        if adr.status == DecisionStatus.SUPERSEDED and not adr.supersedes:
            raise ValueError("Superseded decision must reference the superseded decision ID")
        # Check supersedes chain is within project
        if adr.supersedes:
            self._validate_reference(adr.project_id, adr.supersedes)
        # Ensure no circular supersedes (best-effort): disallow superseding a decision that already supersedes another in a chain that contains this decision id
        if adr.supersedes:
            if self._creates_cycle(adr.project_id, adr.supersedes, adr.decision_id):
                raise ValueError("Circular supersedes reference detected")
        rec = adr.to_memory_record()
        # Ensure fields are redacted and bounded
        return self.create_record(
            project_id=rec.project_id,
            rtype=rec.type,
            data=rec.data,
            created_by=rec.created_by,
            supersedes=rec.supersedes,
            related_records=list(rec.related_records),
            preserve=False,
        )

    # ------------- Work and Issue operations -------------
    def record_work(self, work: WorkRecord) -> MemoryRecord:
        rec = work.to_memory_record()
        return self.create_record(
            project_id=rec.project_id,
            rtype=rec.type,
            data=rec.data,
            created_by=rec.created_by,
            supersedes=rec.supersedes,
            related_records=list(rec.related_records),
            preserve=False,
        )

    def record_issue(self, issue: IssueRecord) -> MemoryRecord:
        rec = issue.to_memory_record()
        return self.create_record(
            project_id=rec.project_id,
            rtype=rec.type,
            data=rec.data,
            created_by=rec.created_by,
            supersedes=rec.supersedes,
            related_records=list(rec.related_records),
            preserve=False,
        )

    # ------------- Automatic safe captures -------------
    def capture_provider_usage_summary(self, project_id: str, summary: Mapping[str, Any], created_by: Optional[str] = None) -> MemoryRecord:
        safe = {
            "providers": summary.get("providers"),
            "models": summary.get("models"),
            "period": summary.get("period"),
            "total_operations": summary.get("total_operations"),
            "cost_estimate": summary.get("cost_estimate"),
            "notes": summary.get("notes"),
        }
        return self.create_record(
            project_id=project_id,
            rtype=MemoryRecordType.PROVIDER_USAGE_SUMMARY,
            data=safe,
            created_by=created_by,
        )

    def capture_autonomous_run_summary(self, project_id: str, report: Mapping[str, Any], created_by: Optional[str] = None) -> MemoryRecord:
        safe = {
            "run_id": report.get("run_id"),
            "outcome": report.get("outcome"),
            "summary": report.get("summary"),
            "warnings": report.get("warnings"),
            "next_actions": report.get("next_actions"),
            "started_at": report.get("started_at"),
            "completed_at": report.get("completed_at"),
        }
        try:
            rec = self.create_record(
                project_id=project_id,
                rtype=MemoryRecordType.AUTONOMOUS_RUN_SUMMARY,
                data=safe,
                created_by=created_by,
            )
            self._events.emit(
                "memory_capture_completed",
                {"project_id": project_id, "record_id": rec.record_id, "record_type": MemoryRecordType.AUTONOMOUS_RUN_SUMMARY.value, "timestamp": _dt_or_none(self._clock.now())},
            )
            return rec
        except Exception as ex:  # noqa: BLE001 - controlled to emit safe event
            self._events.emit(
                "memory_capture_failed",
                {"project_id": project_id, "record_type": MemoryRecordType.AUTONOMOUS_RUN_SUMMARY.value, "safe_failure_code": "capture_error", "timestamp": _dt_or_none(self._clock.now())},
            )
            raise ex

    def capture_validation_summary(self, project_id: str, summary: Mapping[str, Any], created_by: Optional[str] = None) -> MemoryRecord:
        safe = {
            "validation_id": summary.get("validation_id"),
            "status": summary.get("status"),
            "tests_run": summary.get("tests_run"),
            "tests_passed": summary.get("tests_passed"),
            "tests_failed": summary.get("tests_failed"),
            "summary": summary.get("summary"),
        }
        return self.create_record(
            project_id=project_id,
            rtype=MemoryRecordType.VALIDATION_SUMMARY,
            data=safe,
            created_by=created_by,
        )

    def capture_deployment_event(self, project_id: str, event: Mapping[str, Any], created_by: Optional[str] = None) -> MemoryRecord:
        safe = {
            "deployment_id": event.get("deployment_id"),
            "environment": event.get("environment"),
            "version": event.get("version"),
            "status": event.get("status"),
            "summary": event.get("summary"),
            "started_at": event.get("started_at"),
            "completed_at": event.get("completed_at"),
        }
        return self.create_record(
            project_id=project_id,
            rtype=MemoryRecordType.DEPLOYMENT_EVENT,
            data=safe,
            created_by=created_by,
        )

    def record_next_action(self, project_id: str, action: Mapping[str, Any], created_by: Optional[str] = None) -> MemoryRecord:
        safe = {
            "title": action.get("title"),
            "summary": action.get("summary"),
            "priority": action.get("priority"),
            "requires_approval": action.get("requires_approval"),
        }
        return self.create_record(project_id=project_id, rtype=MemoryRecordType.NEXT_ACTION, data=safe, created_by=created_by)

    # ------------- Snapshot and Handoff -------------
    def create_snapshot(self, project_id: str, created_by: Optional[str] = None) -> MemoryRecord:
        # Derive current state from history
        with self._lock:
            records = list(self._store.list_records(project_id))
        latest_accepted_adrs = [
            r for r in records if r.type == MemoryRecordType.ARCHITECTURE_DECISION and r.data.get("status") == DecisionStatus.ACCEPTED.value
        ]
        pending_work = [
            r for r in records if r.type in (MemoryRecordType.PENDING_WORK,) or (r.type == MemoryRecordType.COMPLETED_WORK and r.data.get("status") in (WorkStatus.IN_PROGRESS.value, WorkStatus.PLANNED.value, WorkStatus.BLOCKED.value))
        ]
        completed_work = [
            r for r in records if r.type == MemoryRecordType.COMPLETED_WORK or r.data.get("status") == WorkStatus.COMPLETED.value
        ]
        latest_deploys = [r for r in records if r.type == MemoryRecordType.DEPLOYMENT_EVENT]
        known_issues = [r for r in records if r.type == MemoryRecordType.KNOWN_ISSUE]
        constraints = [r for r in records if r.type in (MemoryRecordType.SECURITY_CONSTRAINT, MemoryRecordType.OPERATIONAL_CONSTRAINT)]
        preferences = [r for r in records if r.type == MemoryRecordType.PROJECT_PREFERENCE]
        provider_usage = [r for r in records if r.type == MemoryRecordType.PROVIDER_USAGE_SUMMARY]
        validation_summaries = [r for r in records if r.type == MemoryRecordType.VALIDATION_SUMMARY]
        autonomous_runs = [r for r in records if r.type == MemoryRecordType.AUTONOMOUS_RUN_SUMMARY]

        project_summary = {
            "project_id": project_id,
            "purpose": _latest_value(records, "project_purpose"),
            "project_name": _latest_value(records, "project_name"),
        }
        architecture_summary = {
            "accepted_decisions_count": len(latest_accepted_adrs),
        }
        snapshot_payload = {
            "schema_version": self._config.schema_version,
            "generated_at": _dt_or_none(self._clock.now()),
            "project_summary": project_summary,
            "architecture_summary": architecture_summary,
            "active_constraints": [r.record_id for r in constraints],
            "development_policy": _latest_policy(preferences, key="development_policy"),
            "security_policy_summary": _latest_policy(preferences, key="security_policy"),
            "deployment_policy_summary": _latest_policy(preferences, key="deployment_policy"),
            "portability_policy": _latest_policy(preferences, key="portability_policy"),
            "completed_work": [r.record_id for r in completed_work[-50:]],
            "pending_work": [r.record_id for r in pending_work[-50:]],
            "known_issues": [r.record_id for r in known_issues[-100:]],
            "latest_deployment": latest_deploys[-1].record_id if latest_deploys else None,
            "latest_validation": validation_summaries[-1].record_id if validation_summaries else None,
            "recent_autonomous_runs": [r.record_id for r in autonomous_runs[-20:]],
            "provider_usage_summary": provider_usage[-1].record_id if provider_usage else None,
        }

        snapshot = self.create_record(
            project_id=project_id,
            rtype=MemoryRecordType.PROJECT_SNAPSHOT,
            data=snapshot_payload,
            created_by=created_by,
            preserve=True,
        )

        self._store.write_snapshot(snapshot)
        self._events.emit(
            "project_snapshot_created",
            {"project_id": project_id, "record_id": snapshot.record_id, "timestamp": _dt_or_none(self._clock.now())},
        )
        return snapshot

    def generate_handoff(self, project_id: str) -> HandoffBundle:
        # Build from latest snapshot if present; else derive on the fly
        snapshot = self._store.get_latest_snapshot(project_id)
        records = list(self._store.list_records(project_id))
        if snapshot is None:
            snapshot = self.create_snapshot(project_id)

        # Resolve references into richer sections
        accepted_adrs = [
            r for r in records if r.type == MemoryRecordType.ARCHITECTURE_DECISION and r.data.get("status") == DecisionStatus.ACCEPTED.value
        ]
        pending_work = [r for r in records if r.type == MemoryRecordType.PENDING_WORK]
        blocked_work = [r for r in pending_work if r.data.get("status") == WorkStatus.BLOCKED.value]
        completed_work = [r for r in records if r.type == MemoryRecordType.COMPLETED_WORK]
        known_issues = [r for r in records if r.type == MemoryRecordType.KNOWN_ISSUE]
        failed_attempts = [r for r in records if r.type == MemoryRecordType.FAILED_ATTEMPT]
        validation_summaries = [r for r in records if r.type == MemoryRecordType.VALIDATION_SUMMARY]
        deployment_events = [r for r in records if r.type == MemoryRecordType.DEPLOYMENT_EVENT]
        autonomous_runs = [r for r in records if r.type == MemoryRecordType.AUTONOMOUS_RUN_SUMMARY]
        next_actions = [r for r in records if r.type == MemoryRecordType.NEXT_ACTION]
        constraints = [r for r in records if r.type in (MemoryRecordType.SECURITY_CONSTRAINT, MemoryRecordType.OPERATIONAL_CONSTRAINT)]
        preferences = [r for r in records if r.type == MemoryRecordType.PROJECT_PREFERENCE]

        bundle_id = self._ids.new_id("handoff")
        generated_at = self._clock.now()

        hb = HandoffBundle(
            schema_version=self._config.schema_version,
            bundle_id=bundle_id,
            generated_at=generated_at,
            project_id=project_id,
            project_summary=snapshot.data.get("project_summary", {}),
            architecture_summary=snapshot.data.get("architecture_summary", {}),
            accepted_architecture_decisions=tuple(_project_safe_section(accepted_adrs)),
            active_constraints={"constraints": [c.record_id for c in constraints]},
            development_policy=_latest_policy(preferences, key="development_policy") or {},
            security_policy_summary=_latest_policy(preferences, key="security_policy") or {},
            deployment_policy_summary=_latest_policy(preferences, key="deployment_policy") or {},
            portability_policy=_latest_policy(preferences, key="portability_policy") or {},
            provider_neutral_operating_instructions=tuple(_derive_provider_neutral_instructions()),
            completed_work=tuple(_project_safe_section(completed_work[-50:])),
            pending_work=tuple(_project_safe_section(pending_work[-50:])),
            blocked_work=tuple(_project_safe_section(blocked_work[-50:])),
            known_issues=tuple(_project_safe_section(known_issues[-100:])),
            failed_attempts_to_avoid=tuple(_project_safe_section(failed_attempts[-100:])),
            current_branch_state={
                "policy": _latest_policy(preferences, key="branch_policy") or {},
            },
            latest_validation_summary=_project_safe_section(validation_summaries[-1:])[0] if validation_summaries else None,
            latest_test_summary=None,  # Placeholder: derive from validations if available in inputs
            latest_deployment_summary=_project_safe_section(deployment_events[-1:])[0] if deployment_events else None,
            recent_autonomous_run_summaries=tuple(_project_safe_section(autonomous_runs[-20:])),
            next_recommended_actions=tuple(
                [str(na.data.get("title") or na.data.get("summary")) for na in next_actions[-20:]]
            ),
            required_approvals=tuple(_derive_required_approvals(preferences)),
            warnings=tuple(_derive_warnings(records)),
            record_references=tuple(sorted({r.record_id for r in (
                list(accepted_adrs) + list(pending_work) + list(blocked_work) + list(completed_work) + list(known_issues) + list(failed_attempts) + list(validation_summaries[-1:]) + list(deployment_events[-1:]) + list(autonomous_runs[-20:])
            )})),
            status=self._compute_handoff_status(project_id, generated_at),
        )

        self._store.export_handoff(project_id, hb)
        self._events.emit(
            "handoff_generated",
            {"project_id": project_id, "bundle_id": bundle_id, "status": hb.status.value, "timestamp": _dt_or_none(generated_at)},
        )
        return hb

    def export_to_repository(self, project_id: str, exporter: Exporter) -> None:
        # Export snapshot JSON, handoff JSON and HANDOFF.md, and directories for decisions/work/issues
        snapshot = self._store.get_latest_snapshot(project_id) or self.create_snapshot(project_id)
        handoff = self.generate_handoff(project_id)

        base = f"agent/memory/state/{project_id}"
        snapshot_path = f"{base}/snapshot.json"
        handoff_json_path = f"{base}/handoff.json"
        handoff_md_path = f"{base}/HANDOFF.md"

        exporter.write_file(snapshot_path, _stable_json_dumps(_jsonify_datetime({
            "schema_version": self._config.schema_version,
            "snapshot": _jsonify_datetime(asdict(snapshot)),
        })))
        exporter.write_file(handoff_json_path, handoff.to_json())
        exporter.write_file(handoff_md_path, _render_handoff_markdown(handoff))

        # Export individual directories as index JSONs (portable summaries)
        decisions = self._store.find_by_type(project_id, MemoryRecordType.ARCHITECTURE_DECISION)
        work_completed = self._store.find_by_type(project_id, MemoryRecordType.COMPLETED_WORK)
        issues = self._store.find_by_type(project_id, MemoryRecordType.KNOWN_ISSUE)

        exporter.write_file(
            f"{base}/decisions/index.json",
            _stable_json_dumps([_project_safe_entry(r) for r in decisions]),
        )
        exporter.write_file(
            f"{base}/work/index.json",
            _stable_json_dumps([_project_safe_entry(r) for r in work_completed]),
        )
        exporter.write_file(
            f"{base}/issues/index.json",
            _stable_json_dumps([_project_safe_entry(r) for r in issues]),
        )

        self._events.emit(
            "memory_export_completed",
            {"project_id": project_id, "timestamp": _dt_or_none(self._clock.now())},
        )

    # ------------- Search -------------
    def search(self, project_id: str, *, query: str = "", types: Optional[Sequence[MemoryRecordType]] = None, status: Optional[Sequence[str]] = None) -> Tuple[MemoryRecord, ...]:
        q = (query or "").strip().lower()
        allowed_types = set(types) if types else None
        status_set = {s.lower() for s in status} if status else None
        out: List[MemoryRecord] = []
        for r in self._store.list_records(project_id):
            if allowed_types and r.type not in allowed_types:
                continue
            # Filter by safe fields
            title = str(r.data.get("title", "")).lower()
            summary = str(r.data.get("summary", "")).lower()
            rid = r.record_id.lower()
            rstatus = str(r.data.get("status", "")).lower()
            if status_set and rstatus not in status_set:
                continue
            if q and (q not in title and q not in summary and q not in rid):
                continue
            out.append(r)
        return tuple(out)

    # ------------- Status helpers -------------
    def _compute_handoff_status(self, project_id: str, generated_at: datetime) -> HandoffStatus:
        # Determine if stale based on newer development records after generated_at
        newer = False
        for r in self._store.list_records(project_id):
            if r.created_at > generated_at and r.type in (
                MemoryRecordType.ARCHITECTURE_DECISION,
                MemoryRecordType.COMPLETED_WORK,
                MemoryRecordType.PENDING_WORK,
                MemoryRecordType.KNOWN_ISSUE,
                MemoryRecordType.DEPLOYMENT_EVENT,
                MemoryRecordType.AUTONOMOUS_RUN_SUMMARY,
                MemoryRecordType.VALIDATION_SUMMARY,
            ):
                newer = True
                break
        return HandoffStatus.STALE if newer else HandoffStatus.CURRENT

    def _validate_reference(self, project_id: str, record_id: str) -> None:
        rec = self._store.get_record(project_id, record_id)
        if rec is None:
            # Ensure not cross-project (best-effort by checking other projects not available in interface), we only know absence => invalid
            raise ValueError("Referenced record does not exist in project scope")

    def _creates_cycle(self, project_id: str, supersedes_id: str, new_id: str) -> bool:
        # Check chain upwards from supersedes_id does not contain new_id
        seen: set[str] = set()
        current = supersedes_id
        while current and current not in seen:
            seen.add(current)
            rec = self._store.get_record(project_id, current)
            if rec is None:
                break
            if rec.record_id == new_id:
                return True
            current = rec.supersedes or ""
        return False


# =============================
# Derived info helpers
# =============================


def _latest_value(records: Sequence[MemoryRecord], key: str) -> Optional[Any]:
    for r in reversed(records):
        if key in r.data:
            return r.data.get(key)
    return None


def _latest_policy(records: Sequence[MemoryRecord], *, key: str) -> Optional[Mapping[str, Any]]:
    for r in reversed(records):
        pol = r.data.get(key)
        if isinstance(pol, Mapping):
            return pol
    return None


def _project_safe_section(records: Sequence[MemoryRecord]) -> List[Mapping[str, Any]]:
    return [_project_safe_entry(r) for r in records]


def _project_safe_entry(r: MemoryRecord) -> Mapping[str, Any]:
    return {
        "record_id": r.record_id,
        "type": r.type.value,
        "created_at": _dt_or_none(r.created_at),
        "data": _redact(r.data, ()),  # already redacted; second pass harmless
    }


def _derive_provider_neutral_instructions() -> List[str]:
    return [
        "Use repository content as the source of truth for non-secret knowledge.",
        "Avoid storing or transmitting credentials or secrets in memory records.",
        "Do not repeat failed attempts listed in 'failed_attempts_to_avoid'.",
        "Follow accepted architecture decisions when making changes.",
        "Adhere to active security and operational constraints.",
        "Prefer provider-neutral tooling and formats where possible.",
    ]


def _derive_required_approvals(preferences: Sequence[MemoryRecord]) -> List[str]:
    pol = _latest_policy(preferences, key="approval_policy")
    if not pol:
        return []
    val = pol.get("required_approvals")
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []


def _derive_warnings(records: Sequence[MemoryRecord]) -> List[str]:
    warns: List[str] = []
    # Simple heuristics
    failed = [r for r in records if r.type == MemoryRecordType.FAILED_ATTEMPT]
    if len(failed) > 0:
        warns.append("There are failed attempts recorded. Do not repeat them.")
    blocked = [r for r in records if r.type == MemoryRecordType.PENDING_WORK and r.data.get("status") == WorkStatus.BLOCKED.value]
    if len(blocked) > 0:
        warns.append("Some work items are blocked and need attention or approval.")
    return warns


def _render_handoff_markdown(hb: HandoffBundle) -> str:
    # Deterministic, minimal markdown
    lines: List[str] = []
    lines.append(f"# Project Handoff for {hb.project_id}")
    lines.append("")
    lines.append(f"Schema Version: {hb.schema_version}")
    lines.append(f"Bundle ID: {hb.bundle_id}")
    lines.append(f"Generated At (UTC): {hb.generated_at.astimezone(timezone.utc).isoformat()}")
    lines.append(f"Status: {hb.status.value}")
    lines.append("")
    lines.append("## Project Summary")
    lines.append(json.dumps(_jsonify_datetime(hb.project_summary), sort_keys=True))
    lines.append("")
    lines.append("## Architecture Summary")
    lines.append(json.dumps(_jsonify_datetime(hb.architecture_summary), sort_keys=True))
    lines.append("")
    lines.append("## Accepted Architecture Decisions")
    lines.append(json.dumps(_jsonify_datetime(list(hb.accepted_architecture_decisions)), sort_keys=True))
    lines.append("")
    lines.append("## Active Constraints")
    lines.append(json.dumps(_jsonify_datetime(hb.active_constraints), sort_keys=True))
    lines.append("")
    lines.append("## Policies")
    lines.append(json.dumps(_jsonify_datetime({
        "development_policy": hb.development_policy,
        "security_policy_summary": hb.security_policy_summary,
        "deployment_policy_summary": hb.deployment_policy_summary,
        "portability_policy": hb.portability_policy,
    }), sort_keys=True))
    lines.append("")
    lines.append("## Work State")
    lines.append(json.dumps(_jsonify_datetime({
        "completed_work": list(hb.completed_work),
        "pending_work": list(hb.pending_work),
        "blocked_work": list(hb.blocked_work),
    }), sort_keys=True))
    lines.append("")
    lines.append("## Known Issues and Failed Attempts")
    lines.append(json.dumps(_jsonify_datetime({
        "known_issues": list(hb.known_issues),
        "failed_attempts_to_avoid": list(hb.failed_attempts_to_avoid),
    }), sort_keys=True))
    lines.append("")
    lines.append("## Latest Summaries")
    lines.append(json.dumps(_jsonify_datetime({
        "latest_validation_summary": hb.latest_validation_summary,
        "latest_deployment_summary": hb.latest_deployment_summary,
        "recent_autonomous_run_summaries": list(hb.recent_autonomous_run_summaries),
    }), sort_keys=True))
    lines.append("")
    lines.append("## Next Recommended Actions")
    lines.extend(f"- {a}" for a in hb.next_recommended_actions)
    lines.append("")
    lines.append("## Required Approvals")
    lines.extend(f"- {a}" for a in hb.required_approvals)
    lines.append("")
    lines.append("## Operating Instructions (Provider-Neutral)")
    lines.extend(f"- {i}" for i in hb.provider_neutral_operating_instructions)
    lines.append("")
    lines.append("## Record References")
    lines.extend(f"- {rid}" for rid in hb.record_references)
    lines.append("")
    lines.append("## Warnings")
    lines.extend(f"- {w}" for w in hb.warnings)
    lines.append("")
    return "\n".join(lines)


# =============================
# Builders and Status
# =============================


def build_project_memory_manager(config: ProjectMemoryConfig, dependencies: Optional[Mapping[str, Any]] = None) -> ProjectMemoryManager:
    deps = dependencies or {}
    store = deps.get("store") or InMemoryProjectMemoryStore()
    clock = deps.get("clock") or UtcClock()
    ids = deps.get("ids") or DeterministicIdGen()
    events = deps.get("events") or SafeEventEmitter()
    return ProjectMemoryManager(config=config, deps=_Deps(store=store, clock=clock, ids=ids, events=events))


def project_memory_status(manager: ProjectMemoryManager) -> Mapping[str, Any]:
    # Provide a deterministic status snapshot of memory and handoff
    # This function avoids locking across store calls to not cause deadlocks; tolerates minor race
    projects: Dict[str, Dict[str, int]] = {}
    # We do not have a way to list all projects from the store; derive from manager public methods isn't feasible without store access
    # So return stats for a requested manager only with store health and generic info
    health = manager._store.health()
    status: Dict[str, Any] = {"health": health, "schema_version": manager._config.schema_version}
    return status


# =============================
# End of module
# =============================
