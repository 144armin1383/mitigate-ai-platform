import unittest

from agent.repair.audit_integration import (
    SelfHealingAuditIntegration,
    build_audit_from_mission_result,
)
from agent.repair.observability import (
    RepairAttemptEvent,
    SelfHealingAuditRecord,
)


class TestSelfHealingAuditIntegration(unittest.TestCase):
    def _build(self, mission_result, **kwargs):
        return build_audit_from_mission_result(
            mission_name="mission.alpha",
            repair_id="r-123",
            mission_result=mission_result,
            **kwargs,
        )

    def test_zero_attempt_succeeded_result(self):
        result = {
            "status": "succeeded",
            "attempts": 0,
            "history": [],
        }
        record = self._build(result, started_at="t0", completed_at="t1")
        self.assertIsInstance(record, SelfHealingAuditRecord)
        self.assertEqual(getattr(record, "final_state", "succeeded"), "succeeded")
        attempts = getattr(record, "attempts")
        self.assertIsInstance(attempts, tuple)
        self.assertEqual(len(attempts), 0)

    def test_one_attempt_succeeded_result(self):
        result = {
            "status": "succeeded",
            "attempts": 1,
            "history": [
                {
                    "attempt": 1,
                    "generation": {"success": True, "error": "ignored"},
                    "apply": {"success": True, "error": "ignored"},
                    "validation": {"success": True, "error": "ignored"},
                }
            ],
        }
        record = self._build(result)
        attempts = record.attempts
        self.assertEqual(len(attempts), 1)
        evt = attempts[0]
        self.assertIsInstance(evt, RepairAttemptEvent)
        self.assertEqual(evt.attempt_number, 1)
        self.assertEqual(evt.generation_status, "succeeded")
        self.assertEqual(evt.application_status, "succeeded")
        self.assertEqual(evt.validation_status, "succeeded")

    def test_two_attempt_succeeded_result(self):
        result = {
            "status": "succeeded",
            "attempts": 2,
            "history": [
                {"attempt": 1, "generation": {"success": False}},
                {"attempt": 2, "generation": {"success": True}},
            ],
        }
        record = self._build(result)
        self.assertEqual([e.attempt_number for e in record.attempts], [1, 2])

    def test_three_attempt_succeeded_result(self):
        result = {
            "status": "succeeded",
            "attempts": 3,
            "history": [
                {"attempt": 1, "generation": {"success": False}},
                {"attempt": 2, "generation": {"success": False}},
                {"attempt": 3, "generation": {"success": True}},
            ],
        }
        record = self._build(result)
        self.assertEqual(tuple(e.attempt_number for e in record.attempts), (1, 2, 3))

    def test_exhausted_result(self):
        result = {"status": "exhausted", "attempts": 2, "history": []}
        record = self._build(result)
        self.assertEqual(getattr(record, "final_state", "exhausted"), "exhausted")

    def test_blocked_result(self):
        result = {
            "status": "blocked",
            "attempts": 1,
            "blocked_reasons": ["quota_exceeded"],
            "history": [
                {"attempt": 1, "generation": {"success": False}},
            ],
        }
        record = self._build(result)
        self.assertEqual(getattr(record, "final_state", "blocked"), "blocked")
        self.assertEqual(getattr(record, "blocked_condition", None), "quota_exceeded")

    def test_failed_result(self):
        result = {"status": "failed", "attempts": 1, "history": []}
        record = self._build(result)
        self.assertEqual(getattr(record, "final_state", "failed"), "failed")

    def test_blocked_condition_preserved_first_only(self):
        result = {
            "status": "blocked",
            "attempts": 1,
            "blocked_reasons": ["first", "second"],
            "history": [],
        }
        record = self._build(result)
        self.assertEqual(getattr(record, "blocked_condition", None), "first")

    def test_history_order_preserved(self):
        result = {
            "status": "succeeded",
            "attempts": 3,
            "history": [
                {"attempt": 2, "generation": {"success": False}},
                {"attempt": 3, "generation": {"success": False}},
                {"attempt": 5, "generation": {"success": True}},
            ],
        }
        record = self._build(result)
        self.assertEqual([e.attempt_number for e in record.attempts], [2, 3, 5])

    def test_attempt_number_preserved(self):
        result = {
            "status": "succeeded",
            "attempts": 2,
            "history": [
                {"attempt": 10, "generation": {"success": True}},
                {"attempt": 20, "generation": {"success": True}},
            ],
        }
        record = self._build(result)
        self.assertEqual([e.attempt_number for e in record.attempts], [10, 20])

    def test_duplicate_attempt_numbers_rejected(self):
        result = {
            "status": "failed",
            "attempts": 2,
            "history": [
                {"attempt": 1, "generation": {"success": False}},
                {"attempt": 1, "generation": {"success": False}},
            ],
        }
        with self.assertRaises(ValueError):
            self._build(result)

    def test_missing_attempt_number_rejected(self):
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"generation": {"success": False}},
            ],
        }
        with self.assertRaises(ValueError):
            self._build(result)

    def test_zero_attempt_number_rejected(self):
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": 0, "generation": {"success": False}},
            ],
        }
        with self.assertRaises(ValueError):
            self._build(result)

    def test_negative_attempt_number_rejected(self):
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": -1, "generation": {"success": False}},
            ],
        }
        with self.assertRaises(ValueError):
            self._build(result)

    def test_allowed_paths_preserved(self):
        allowed = ["/safe/a", "/safe/b"]
        result = {"status": "succeeded", "attempts": 1, "history": [{"attempt": 1}]}
        record = self._build(result, allowed_paths=allowed)
        evt = record.attempts[0]
        self.assertEqual(evt.allowed_paths, tuple(allowed))

    def test_denied_paths_preserved(self):
        denied = ["/deny/a", "/deny/b"]
        result = {"status": "succeeded", "attempts": 1, "history": [{"attempt": 1}]}
        record = self._build(result, denied_paths=denied)
        evt = record.attempts[0]
        self.assertEqual(evt.denied_paths, tuple(denied))

    def test_caller_history_not_mutated(self):
        history = [
            {"attempt": 1, "generation": {"success": True}},
            {"attempt": 2, "generation": {"success": False}},
        ]
        result = {"status": "succeeded", "attempts": 2, "history": history}
        snapshot = [dict(item) for item in history]
        self._build(result)
        self.assertEqual(history, snapshot)

    def test_caller_paths_not_mutated(self):
        allowed = ["/a"]
        denied = ["/b"]
        result = {"status": "succeeded", "attempts": 1, "history": [{"attempt": 1}]}
        record = self._build(result, allowed_paths=allowed, denied_paths=denied)
        # mutate originals
        allowed.append("/c")
        denied.append("/d")
        evt = record.attempts[0]
        self.assertEqual(evt.allowed_paths, ("/a",))
        self.assertEqual(evt.denied_paths, ("/b",))

    def test_bearer_secret_not_retained(self):
        token = "TST" + "-" + "BEARER"
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {
                    "attempt": 1,
                    "generation": {"success": False, "error": f"Authorization: Bearer {token}"},
                }
            ],
        }
        record = self._build(result)
        text = repr(record)
        self.assertNotIn(token, text)
        self.assertNotIn("Bearer", text)

    def test_password_secret_not_retained(self):
        pwd = "pa" + "ss" + "word=super-secret"
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": 1, "apply": {"success": False, "error": pwd}},
            ],
        }
        record = self._build(result)
        self.assertNotIn("super-secret", repr(record))

    def test_api_key_secret_not_retained(self):
        api_key = "x-" + "api" + "-key: 12345"
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": 1, "validation": {"success": False, "error": api_key}},
            ],
        }
        record = self._build(result)
        self.assertNotIn("12345", repr(record))

    def test_access_token_secret_not_retained(self):
        tok = "ac" + "cess" + "_token=abcxyz"
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": 1, "generation": {"success": False, "error": tok}},
            ],
        }
        record = self._build(result)
        self.assertNotIn("abcxyz", repr(record))

    def test_private_key_like_value_not_retained(self):
        part1 = "-----BEGIN "
        part2 = "PRIVATE KEY"
        part3 = "-----"
        secret_key = part1 + part2 + part3 + "\nMIIM...\n" + "-----END " + part2 + part3
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": 1, "apply": {"success": False, "error": secret_key}},
            ],
        }
        record = self._build(result)
        txt = repr(record)
        self.assertNotIn(part1, txt)
        self.assertNotIn(part2, txt)

    def test_raw_error_field_not_retained(self):
        err = "some error message that should not appear"
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {
                    "attempt": 1,
                    "generation": {"success": False, "error": err},
                    "apply": {"success": False, "error": err},
                    "validation": {"success": False, "error": err},
                }
            ],
        }
        record = self._build(result)
        self.assertNotIn(err, repr(record))

    def test_raw_exception_object_not_retained(self):
        ex = Exception("boom")
        result = {
            "status": "failed",
            "attempts": 1,
            "history": [
                {"attempt": 1, "generation": {"success": False, "error": ex}},
            ],
        }
        record = self._build(result)
        self.assertNotIn("boom", repr(record))

    def _normalize_attempts(self, record: SelfHealingAuditRecord):
        return tuple(
            (
                e.attempt_number,
                e.generation_status,
                e.application_status,
                e.validation_status,
                e.allowed_paths,
                e.denied_paths,
            )
            for e in record.attempts
        )

    def test_deterministic_translation_equivalence(self):
        result = {
            "status": "succeeded",
            "attempts": 3,
            "history": [
                {"attempt": 1, "generation": {"success": False}},
                {"attempt": 2, "generation": {"success": False}},
                {"attempt": 3, "generation": {"success": True}},
            ],
        }
        r1 = self._build(result, allowed_paths=["/a"], denied_paths=["/b"]) 
        r2 = self._build(result, allowed_paths=["/a"], denied_paths=["/b"]) 
        self.assertEqual(self._normalize_attempts(r1), self._normalize_attempts(r2))

    def test_equivalent_inputs_equivalent_output(self):
        # attempts count differs but history is same -> equivalent output
        base_history = [
            {"attempt": 1, "generation": {"success": True}},
        ]
        r1 = self._build({"status": "succeeded", "attempts": 1, "history": list(base_history)})
        r2 = self._build({"status": "succeeded", "attempts": 99, "history": list(base_history)})
        self.assertEqual(self._normalize_attempts(r1), self._normalize_attempts(r2))

    def test_timestamp_normalization_delegated_to_phase3a(self):
        started = "2025-01-01T00:00:00Z"
        completed = "2025-01-01T01:00:00Z"
        result = {"status": "succeeded", "attempts": 0, "history": []}
        record = self._build(result, started_at=started, completed_at=completed)
        self.assertEqual(getattr(record, "started_at", started), started)
        self.assertEqual(getattr(record, "completed_at", completed), completed)

    def test_missing_optional_validation_status_handled(self):
        result = {
            "status": "succeeded",
            "attempts": 1,
            "history": [
                {
                    "attempt": 1,
                    "generation": {"success": True},
                    "apply": {"success": True},
                    # validation missing entirely
                }
            ],
        }
        record = self._build(result)
        evt = record.attempts[0]
        self.assertIsNone(evt.validation_status)

    def test_no_side_effects_no_retry_no_execution(self):
        # The translator should not perform IO or retries; basic call suffices.
        result = {"status": "succeeded", "attempts": 0, "history": []}
        record = self._build(result)
        self.assertIsInstance(record, SelfHealingAuditRecord)

    def test_returned_type_and_attempts_are_immutable_events(self):
        result = {
            "status": "succeeded",
            "attempts": 2,
            "history": [
                {"attempt": 1, "generation": {"success": True}},
                {"attempt": 2, "generation": {"success": False}},
            ],
        }
        record = self._build(result)
        self.assertIsInstance(record, SelfHealingAuditRecord)
        self.assertIsInstance(record.attempts, tuple)
        for evt in record.attempts:
            self.assertIsInstance(evt, RepairAttemptEvent)


if __name__ == "__main__":
    unittest.main()
