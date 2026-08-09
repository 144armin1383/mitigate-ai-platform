from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .audit_store import SelfHealingAuditStore
from .observability import SelfHealingAuditRecord


HEALTHY = "healthy"
DEGRADED = "degraded"
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SelfHealingOperationalStatus:
    status: str
    audit_path: str
    total_records: int
    succeeded: int
    exhausted: int
    blocked: int
    failed: int
    latest_mission_name: Optional[str]
    latest_repair_id: Optional[str]
    latest_final_state: Optional[str]
    latest_completed_at: Optional[str]
    reason: Optional[str]


def inspect_self_healing_operations(
    *,
    store: Optional[SelfHealingAuditStore] = None,
    audit_path: Optional[Path | str] = None,
    recent_limit: int = 100,
) -> SelfHealingOperationalStatus:
    """
    Inspect persisted Self-Healing audit state.

    This function is passive and read-only.  It has no repair, retry,
    generation, validation, Git, provider, or deployment authority.
    """

    if recent_limit <= 0:
        raise ValueError("recent_limit must be positive")

    if store is not None and audit_path is not None:
        raise ValueError("provide either store or audit_path, not both")

    audit_store = (
        store
        if store is not None
        else SelfHealingAuditStore(audit_path)
    )

    try:
        records = audit_store.query(
            limit=recent_limit,
            newest_first=True,
        )
    except (OSError, ValueError, TypeError):
        return SelfHealingOperationalStatus(
            status=UNAVAILABLE,
            audit_path=str(audit_store.path),
            total_records=0,
            succeeded=0,
            exhausted=0,
            blocked=0,
            failed=0,
            latest_mission_name=None,
            latest_repair_id=None,
            latest_final_state=None,
            latest_completed_at=None,
            reason="AUDIT_QUERY_FAILED",
        )

    if not records:
        return SelfHealingOperationalStatus(
            status=HEALTHY,
            audit_path=str(audit_store.path),
            total_records=0,
            succeeded=0,
            exhausted=0,
            blocked=0,
            failed=0,
            latest_mission_name=None,
            latest_repair_id=None,
            latest_final_state=None,
            latest_completed_at=None,
            reason=None,
        )

    counts = {
        "succeeded": 0,
        "exhausted": 0,
        "blocked": 0,
        "failed": 0,
    }

    for record in records:
        if record.final_state in counts:
            counts[record.final_state] += 1

    latest = records[0]

    degraded = (
        counts["exhausted"] > 0
        or counts["blocked"] > 0
        or counts["failed"] > 0
    )

    return SelfHealingOperationalStatus(
        status=DEGRADED if degraded else HEALTHY,
        audit_path=str(audit_store.path),
        total_records=len(records),
        succeeded=counts["succeeded"],
        exhausted=counts["exhausted"],
        blocked=counts["blocked"],
        failed=counts["failed"],
        latest_mission_name=latest.mission_name,
        latest_repair_id=latest.repair_id,
        latest_final_state=latest.final_state,
        latest_completed_at=latest.completed_at,
        reason="NON_SUCCESS_TERMINAL_STATE" if degraded else None,
    )


def recent_self_healing_failures(
    *,
    store: SelfHealingAuditStore,
    limit: int = 50,
) -> Tuple[SelfHealingAuditRecord, ...]:
    """
    Return recent non-success terminal audit records.

    Read-only helper; it never initiates or influences repair execution.
    """

    if limit <= 0:
        raise ValueError("limit must be positive")

    records = store.query(newest_first=True)

    failures = tuple(
        record
        for record in records
        if record.final_state in {
            "exhausted",
            "blocked",
            "failed",
        }
    )

    return failures[:limit]
