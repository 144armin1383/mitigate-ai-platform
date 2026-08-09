from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .audit_integration import (
    build_audit_from_mission_result,
)
from .audit_store import SelfHealingAuditStore
from .observability import SelfHealingAuditRecord


AUDIT_CAPTURE_FAILED = "AUDIT_CAPTURE_FAILED"
AUDIT_PERSISTENCE_FAILED = "AUDIT_PERSISTENCE_FAILED"


@dataclass(frozen=True)
class RuntimeAuditCaptureResult:
    captured: bool
    record: Optional[SelfHealingAuditRecord]
    safe_error_code: Optional[str]


def capture_self_healing_audit(
    *,
    mission_name: str,
    repair_id: str,
    mission_result: dict[str, Any],
    failure_category: str,
    safe_failure_summary: str,
    allowed_paths: Sequence[str],
    denied_paths: Sequence[str],
    started_at: Any,
    completed_at: Any,
    store: Optional[SelfHealingAuditStore] = None,
) -> RuntimeAuditCaptureResult:

    try:
        record = build_audit_from_mission_result(
            mission_name=mission_name,
            repair_id=repair_id,
            mission_result=mission_result,
            initial_failure_category=failure_category,
            initial_safe_summary=safe_failure_summary,
            allowed_paths=tuple(allowed_paths),
            denied_paths=tuple(denied_paths),
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception:
        return RuntimeAuditCaptureResult(
            captured=False,
            record=None,
            safe_error_code=AUDIT_CAPTURE_FAILED,
        )

    try:
        audit_store = (
            store
            if store is not None
            else SelfHealingAuditStore()
        )

        persisted = audit_store.append(record)

    except Exception:
        persisted = False

    if not persisted:
        return RuntimeAuditCaptureResult(
            captured=True,
            record=record,
            safe_error_code=AUDIT_PERSISTENCE_FAILED,
        )

    return RuntimeAuditCaptureResult(
        captured=True,
        record=record,
        safe_error_code=None,
    )
