from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.repair.audit_store import SelfHealingAuditStore
from agent.repair.observability import (
    SelfHealingAuditRecord,
    get_schema_version,
)
from agent.repair.operational_hardening import (
    DEGRADED,
    HEALTHY,
    inspect_self_healing_operations,
    recent_self_healing_failures,
)


def make_record(
    repair_id: str,
    state: str,
    completed_at: str,
) -> SelfHealingAuditRecord:
    return SelfHealingAuditRecord(
        schema_version=get_schema_version(),
        mission_name="mission-alpha",
        repair_id=repair_id,
        initial_failure_category="unit",
        initial_safe_summary="safe failure",
        final_state=state,
        total_attempts=0,
        blocked_condition=None,
        attempts=(),
        started_at="2026-08-09T10:00:00Z",
        completed_at=completed_at,
    )


class TestSelfHealingOperationalHardening(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audit.jsonl"
        self.store = SelfHealingAuditStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_store_is_healthy(self) -> None:
        status = inspect_self_healing_operations(store=self.store)

        self.assertEqual(HEALTHY, status.status)
        self.assertEqual(0, status.total_records)
        self.assertIsNone(status.reason)

    def test_success_only_is_healthy(self) -> None:
        self.assertTrue(
            self.store.append(
                make_record(
                    "r1",
                    "succeeded",
                    "2026-08-09T10:01:00Z",
                )
            )
        )

        status = inspect_self_healing_operations(store=self.store)

        self.assertEqual(HEALTHY, status.status)
        self.assertEqual(1, status.succeeded)
        self.assertEqual(0, status.failed)

    def test_non_success_state_is_degraded(self) -> None:
        self.store.append(
            make_record(
                "r1",
                "succeeded",
                "2026-08-09T10:01:00Z",
            )
        )
        self.store.append(
            make_record(
                "r2",
                "exhausted",
                "2026-08-09T10:02:00Z",
            )
        )

        status = inspect_self_healing_operations(store=self.store)

        self.assertEqual(DEGRADED, status.status)
        self.assertEqual(2, status.total_records)
        self.assertEqual(1, status.succeeded)
        self.assertEqual(1, status.exhausted)
        self.assertEqual(
            "NON_SUCCESS_TERMINAL_STATE",
            status.reason,
        )

    def test_latest_record_is_reported(self) -> None:
        self.store.append(
            make_record(
                "older",
                "succeeded",
                "2026-08-09T10:01:00Z",
            )
        )
        self.store.append(
            make_record(
                "newer",
                "blocked",
                "2026-08-09T10:02:00Z",
            )
        )

        status = inspect_self_healing_operations(store=self.store)

        self.assertEqual("newer", status.latest_repair_id)
        self.assertEqual("blocked", status.latest_final_state)

    def test_recent_failures_excludes_success(self) -> None:
        self.store.append(
            make_record(
                "ok",
                "succeeded",
                "2026-08-09T10:01:00Z",
            )
        )
        self.store.append(
            make_record(
                "bad",
                "failed",
                "2026-08-09T10:02:00Z",
            )
        )

        records = recent_self_healing_failures(
            store=self.store,
        )

        self.assertEqual(1, len(records))
        self.assertEqual("bad", records[0].repair_id)

    def test_invalid_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            inspect_self_healing_operations(
                store=self.store,
                recent_limit=0,
            )

        with self.assertRaises(ValueError):
            recent_self_healing_failures(
                store=self.store,
                limit=0,
            )

    def test_store_and_path_are_mutually_exclusive(self) -> None:
        with self.assertRaises(ValueError):
            inspect_self_healing_operations(
                store=self.store,
                audit_path=self.path,
            )


if __name__ == "__main__":
    unittest.main()
