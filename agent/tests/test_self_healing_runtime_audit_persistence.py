import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.repair.audit_store import (
    SelfHealingAuditStore,
)
from agent.repair.observability import (
    SelfHealingAuditRecord,
)
from agent.repair.runtime_audit import (
    AUDIT_CAPTURE_FAILED,
    AUDIT_PERSISTENCE_FAILED,
    RuntimeAuditCaptureResult,
    capture_self_healing_audit,
)


class RuntimeAuditPersistenceTests(unittest.TestCase):

    def mission_result(self):
        return {
            "status": "succeeded",
            "attempts": 1,
            "initial_validation": {
                "success": False,
                "error": None,
            },
            "history": [
                {
                    "attempt": 1,
                    "generation": {
                        "success": True,
                        "error": None,
                    },
                    "apply": {
                        "success": True,
                        "error": None,
                    },
                    "validation": {
                        "success": True,
                        "error": None,
                    },
                }
            ],
            "failures": [],
            "blocked_reasons": [],
        }

    def capture(self, store):
        return capture_self_healing_audit(
            mission_name="mission-a",
            repair_id="repair-a",
            mission_result=self.mission_result(),
            failure_category="unittest-failure",
            safe_failure_summary="safe summary",
            allowed_paths=("agent/a.py",),
            denied_paths=(),
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            store=store,
        )

    def test_successful_capture_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            store = SelfHealingAuditStore(
                Path(td) / "audit.jsonl"
            )

            result = self.capture(store)

            self.assertIsInstance(
                result,
                RuntimeAuditCaptureResult,
            )
            self.assertTrue(result.captured)
            self.assertIsNone(
                result.safe_error_code
            )
            self.assertIsInstance(
                result.record,
                SelfHealingAuditRecord,
            )

            stored = store.query()

            self.assertEqual(len(stored), 1)
            self.assertEqual(
                stored[0].repair_id,
                "repair-a",
            )
            self.assertEqual(
                stored[0].initial_failure_category,
                "unittest-failure",
            )
            self.assertEqual(
                stored[0].initial_safe_summary,
                "safe summary",
            )

    def test_translation_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as td:
            store = SelfHealingAuditStore(
                Path(td) / "audit.jsonl"
            )

            with patch(
                "agent.repair.runtime_audit."
                "build_audit_from_mission_result",
                side_effect=ValueError(
                    "raw-sensitive-diagnostic"
                ),
            ):
                result = self.capture(store)

            self.assertFalse(result.captured)
            self.assertIsNone(result.record)
            self.assertEqual(
                result.safe_error_code,
                AUDIT_CAPTURE_FAILED,
            )
            self.assertNotIn(
                "raw-sensitive-diagnostic",
                repr(result),
            )

    def test_persistence_failure_keeps_record(self):
        class FailingStore:
            def append(self, record):
                return False

        result = self.capture(FailingStore())

        self.assertTrue(result.captured)
        self.assertIsInstance(
            result.record,
            SelfHealingAuditRecord,
        )
        self.assertEqual(
            result.safe_error_code,
            AUDIT_PERSISTENCE_FAILED,
        )

    def test_persistence_exception_is_nonfatal(self):
        class ExplodingStore:
            def append(self, record):
                raise RuntimeError(
                    "raw-storage-error"
                )

        result = self.capture(ExplodingStore())

        self.assertTrue(result.captured)
        self.assertIsNotNone(result.record)
        self.assertEqual(
            result.safe_error_code,
            AUDIT_PERSISTENCE_FAILED,
        )
        self.assertNotIn(
            "raw-storage-error",
            repr(result),
        )

    def test_input_not_mutated(self):
        with tempfile.TemporaryDirectory() as td:
            store = SelfHealingAuditStore(
                Path(td) / "audit.jsonl"
            )

            result_data = self.mission_result()
            original = repr(result_data)

            capture_self_healing_audit(
                mission_name="m",
                repair_id="r",
                mission_result=result_data,
                failure_category="unit",
                safe_failure_summary="safe",
                allowed_paths=("agent/a.py",),
                denied_paths=("agent/x.py",),
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:01:00Z",
                store=store,
            )

            self.assertEqual(
                repr(result_data),
                original,
            )


if __name__ == "__main__":
    unittest.main()
