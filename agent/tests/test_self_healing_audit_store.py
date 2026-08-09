import json
import tempfile
import unittest
from pathlib import Path

from agent.repair.audit_store import (
    SelfHealingAuditStore,
)
from agent.repair.observability import (
    RepairAttemptEvent,
    SelfHealingAuditRecord,
    get_schema_version,
)


class SelfHealingAuditStoreTests(unittest.TestCase):

    def make_record(
        self,
        *,
        mission="mission-a",
        repair="repair-1",
        state="succeeded",
        attempts=1,
        started="2026-01-01T10:00:00Z",
    ):
        events = tuple(
            RepairAttemptEvent(
                mission_name=mission,
                repair_id=repair,
                attempt_number=i + 1,
                failure_category="unit",
                safe_failure_summary="safe",
                allowed_paths=("agent/a.py",),
                denied_paths=("agent/core/",),
                generation_status="succeeded",
                application_status="succeeded",
                validation_status="succeeded",
                started_at=started,
                completed_at="2026-01-01T10:01:00Z",
            )
            for i in range(attempts)
        )

        return SelfHealingAuditRecord(
            schema_version=get_schema_version(),
            mission_name=mission,
            repair_id=repair,
            initial_failure_category="unit",
            initial_safe_summary="safe",
            final_state=state,
            total_attempts=attempts,
            blocked_condition=None,
            attempts=events,
            started_at=started,
            completed_at="2026-01-01T10:02:00Z",
        )

    def test_append_and_reconstruct(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            store = SelfHealingAuditStore(path)

            record = self.make_record()

            self.assertTrue(store.append(record))

            result = store.query()

            self.assertEqual(len(result), 1)
            self.assertIsInstance(
                result[0],
                SelfHealingAuditRecord,
            )
            self.assertIsInstance(
                result[0].attempts[0],
                RepairAttemptEvent,
            )
            self.assertEqual(
                result[0].to_dict(),
                record.to_dict(),
            )

    def test_multiple_append_and_filters(self):
        with tempfile.TemporaryDirectory() as td:
            store = SelfHealingAuditStore(
                Path(td) / "audit.jsonl"
            )

            store.append(
                self.make_record(
                    mission="alpha",
                    repair="r1",
                    state="succeeded",
                    attempts=1,
                    started="2026-01-01T10:00:00Z",
                )
            )
            store.append(
                self.make_record(
                    mission="beta",
                    repair="r2",
                    state="blocked",
                    attempts=2,
                    started="2026-01-02T10:00:00Z",
                )
            )
            store.append(
                self.make_record(
                    mission="alpha",
                    repair="r3",
                    state="exhausted",
                    attempts=3,
                    started="2026-01-03T10:00:00Z",
                )
            )

            self.assertEqual(
                len(store.query(mission_name="alpha")),
                2,
            )
            self.assertEqual(
                len(store.query(repair_id="r2")),
                1,
            )
            self.assertEqual(
                len(store.query(final_state="blocked")),
                1,
            )
            self.assertEqual(
                len(store.query(min_attempts=2)),
                2,
            )
            self.assertEqual(
                len(store.query(max_attempts=1)),
                1,
            )

    def test_time_filter_order_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            store = SelfHealingAuditStore(
                Path(td) / "audit.jsonl"
            )

            for i in range(3):
                store.append(
                    self.make_record(
                        repair=f"r{i}",
                        started=(
                            f"2026-01-0{i + 1}"
                            "T10:00:00Z"
                        ),
                    )
                )

            result = store.query(
                started_at_from="2026-01-02T00:00:00Z",
                newest_first=True,
                limit=1,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(
                result[0].repair_id,
                "r2",
            )

    def test_malformed_and_unknown_schema_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            store = SelfHealingAuditStore(path)

            store.append(self.make_record())

            with path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write("{broken\n")
                handle.write(
                    json.dumps(
                        {
                            "schema_version": "999",
                            "mission_name": "bad",
                        }
                    )
                    + "\n"
                )

            result = store.query()

            self.assertEqual(len(result), 1)
            self.assertEqual(
                result[0].mission_name,
                "mission-a",
            )

    def test_failed_append_does_not_destroy_prior_data(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            good_path = root / "audit.jsonl"
            good = SelfHealingAuditStore(good_path)

            self.assertTrue(
                good.append(self.make_record())
            )

            bad_parent = root / "not-a-directory"
            bad_parent.write_text(
                "x",
                encoding="utf-8",
            )

            bad = SelfHealingAuditStore(
                bad_parent / "audit.jsonl"
            )

            self.assertFalse(
                bad.append(self.make_record())
            )

            self.assertEqual(
                len(good.query()),
                1,
            )

    def test_store_rejects_raw_dictionary(self):
        with tempfile.TemporaryDirectory() as td:
            store = SelfHealingAuditStore(
                Path(td) / "audit.jsonl"
            )

            self.assertFalse(
                store.append({"secret": "raw"})
            )

    def test_secret_content_is_sanitized_before_storage(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            store = SelfHealingAuditStore(path)

            secret = "top-secret-value"

            start = (
                "-----"
                + ("BE" + "GIN")
                + " "
                + ("PRI" + "VATE")
                + " "
                + ("KE" + "Y")
                + "-----"
            )

            end = (
                "-----"
                + ("E" + "ND")
                + " "
                + ("PRI" + "VATE")
                + " "
                + ("KE" + "Y")
                + "-----"
            )

            record = SelfHealingAuditRecord(
                schema_version=get_schema_version(),
                mission_name="m",
                repair_id="r",
                initial_failure_category="unit",
                initial_safe_summary=(
                    "Authorization: Bearer "
                    + secret
                    + " password="
                    + secret
                    + "\n"
                    + start
                    + "\n"
                    + secret
                    + "\n"
                    + end
                ),
                final_state="succeeded",
                total_attempts=0,
                blocked_condition=None,
                attempts=(),
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:00:01Z",
            )

            self.assertTrue(store.append(record))

            raw = path.read_text(
                encoding="utf-8"
            )

            self.assertNotIn(secret, raw)
            self.assertIn("[REDACTED]", raw)


if __name__ == "__main__":
    unittest.main()
