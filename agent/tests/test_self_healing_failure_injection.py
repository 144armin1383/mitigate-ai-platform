from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from agent.repair.audit_store import SelfHealingAuditStore
from agent.repair.observability import (
    SelfHealingAuditRecord,
    get_schema_version,
)
from agent.repair.operational_hardening import (
    HEALTHY,
    inspect_self_healing_operations,
)


def make_record(index: int) -> SelfHealingAuditRecord:
    return SelfHealingAuditRecord(
        schema_version=get_schema_version(),
        mission_name="concurrency-mission",
        repair_id=f"repair-{index}",
        initial_failure_category="unit",
        initial_safe_summary="safe",
        final_state="succeeded",
        total_attempts=0,
        blocked_condition=None,
        attempts=(),
        started_at="2026-08-09T11:00:00Z",
        completed_at="2026-08-09T11:01:00Z",
    )


class TestSelfHealingFailureInjection(unittest.TestCase):
    def test_concurrent_append_preserves_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            store = SelfHealingAuditStore(path)

            count = 20
            results = [False] * count

            def worker(index: int) -> None:
                results[index] = store.append(
                    make_record(index)
                )

            threads = [
                threading.Thread(
                    target=worker,
                    args=(index,),
                )
                for index in range(count)
            ]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join(timeout=5)

            self.assertTrue(all(results))

            records = store.query()

            self.assertEqual(count, len(records))
            self.assertEqual(
                count,
                len({r.repair_id for r in records}),
            )

    def test_malformed_jsonl_does_not_break_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            store = SelfHealingAuditStore(path)

            self.assertTrue(store.append(make_record(1)))

            with path.open("a", encoding="utf-8") as handle:
                handle.write("{malformed-json\n")

            records = store.query()

            self.assertEqual(1, len(records))
            self.assertEqual("repair-1", records[0].repair_id)

    def test_missing_store_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing" / "audit.jsonl"

            status = inspect_self_healing_operations(
                audit_path=path,
            )

            self.assertEqual(HEALTHY, status.status)
            self.assertEqual(0, status.total_records)

    def test_operational_inspection_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            store = SelfHealingAuditStore(path)

            store.append(make_record(1))

            before = path.read_bytes()

            inspect_self_healing_operations(store=store)

            after = path.read_bytes()

            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
