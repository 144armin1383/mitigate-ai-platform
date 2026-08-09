from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Optional, Tuple

import fcntl

from .observability import (
    RepairAttemptEvent,
    SelfHealingAuditRecord,
    get_schema_version,
    normalize_timestamp,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_PATH = (
    REPOSITORY_ROOT
    / "tmp_self_healing_audit"
    / "self_healing_audit.jsonl"
)


class SelfHealingAuditStore:
    """
    Local append-only JSONL store for sanitized Self-Healing audit records.

    This store has no repair or execution authority.
    """

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self._path = Path(path) if path is not None else DEFAULT_AUDIT_PATH

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: SelfHealingAuditRecord) -> bool:
        if not isinstance(record, SelfHealingAuditRecord):
            return False

        try:
            payload = json.dumps(
                record.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            encoded = (payload + "\n").encode("utf-8")

            self._path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            fd = os.open(
                self._path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )

            try:
                fcntl.flock(fd, fcntl.LOCK_EX)

                offset = 0
                while offset < len(encoded):
                    written = os.write(fd, encoded[offset:])
                    if written <= 0:
                        raise OSError("audit append failed")
                    offset += written

                os.fsync(fd)
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)

            return True

        except (OSError, ValueError, TypeError):
            return False

    def query(
        self,
        *,
        mission_name: Optional[str] = None,
        repair_id: Optional[str] = None,
        final_state: Optional[str] = None,
        started_at_from: Optional[str] = None,
        started_at_to: Optional[str] = None,
        min_attempts: Optional[int] = None,
        max_attempts: Optional[int] = None,
        limit: Optional[int] = None,
        newest_first: bool = False,
    ) -> Tuple[SelfHealingAuditRecord, ...]:

        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")

        if not self._path.exists():
            return ()

        lower = (
            normalize_timestamp(started_at_from)
            if started_at_from is not None
            else None
        )
        upper = (
            normalize_timestamp(started_at_to)
            if started_at_to is not None
            else None
        )

        records = []

        try:
            with self._path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                for line in handle:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        record = _record_from_dict(data)
                    except (
                        json.JSONDecodeError,
                        TypeError,
                        ValueError,
                        KeyError,
                    ):
                        continue

                    if record is None:
                        continue

                    if (
                        mission_name is not None
                        and record.mission_name != mission_name
                    ):
                        continue

                    if (
                        repair_id is not None
                        and record.repair_id != repair_id
                    ):
                        continue

                    if (
                        final_state is not None
                        and record.final_state != final_state
                    ):
                        continue

                    started = record.started_at or ""

                    if lower is not None and started < lower:
                        continue

                    if upper is not None and started > upper:
                        continue

                    if (
                        min_attempts is not None
                        and record.total_attempts < min_attempts
                    ):
                        continue

                    if (
                        max_attempts is not None
                        and record.total_attempts > max_attempts
                    ):
                        continue

                    records.append(record)

        except OSError:
            return ()

        records.sort(
            key=lambda item: (
                item.started_at or "",
                item.completed_at or "",
                item.mission_name,
                item.repair_id,
            ),
            reverse=newest_first,
        )

        if limit is not None:
            records = records[:limit]

        return tuple(records)


def _record_from_dict(
    data: object,
) -> Optional[SelfHealingAuditRecord]:

    if not isinstance(data, dict):
        return None

    if data.get("schema_version") != get_schema_version():
        return None

    raw_attempts = data.get("attempts")

    if not isinstance(raw_attempts, list):
        return None

    attempts = []

    for raw in raw_attempts:
        if not isinstance(raw, dict):
            return None

        attempts.append(
            RepairAttemptEvent(
                mission_name=raw["mission_name"],
                repair_id=raw["repair_id"],
                attempt_number=raw["attempt_number"],
                failure_category=raw.get(
                    "failure_category"
                ),
                safe_failure_summary=raw.get(
                    "safe_failure_summary"
                ),
                allowed_paths=tuple(
                    raw.get("allowed_paths") or ()
                ),
                denied_paths=tuple(
                    raw.get("denied_paths") or ()
                ),
                generation_status=raw.get(
                    "generation_status"
                ),
                application_status=raw.get(
                    "application_status"
                ),
                validation_status=raw.get(
                    "validation_status"
                ),
                started_at=raw.get("started_at"),
                completed_at=raw.get("completed_at"),
            )
        )

    return SelfHealingAuditRecord(
        schema_version=data["schema_version"],
        mission_name=data["mission_name"],
        repair_id=data["repair_id"],
        initial_failure_category=data.get(
            "initial_failure_category"
        ),
        initial_safe_summary=data.get(
            "initial_safe_summary"
        ),
        final_state=data["final_state"],
        total_attempts=data["total_attempts"],
        blocked_condition=data.get(
            "blocked_condition"
        ),
        attempts=tuple(attempts),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
    )
