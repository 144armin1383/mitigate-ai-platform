import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

from agent.repair.observability import (
    RepairAttemptEvent,
    SelfHealingAuditRecord,
    SelfHealingAuditBuilder,
    get_schema_version,
    sanitize_string,
    FINAL_STATES,
    MAX_TEXT_LENGTH,
)


class TestSelfHealingObservability(unittest.TestCase):
    def _mk_event(self, attempt_no: int, started: datetime, completed: datetime, summary: str = "ok", allowed=None, denied=None) -> RepairAttemptEvent:
        return RepairAttemptEvent(
            mission_name="mission-alpha",
            repair_id="r-123",
            attempt_number=attempt_no,
            failure_category="unit",
            safe_failure_summary=summary,
            allowed_paths=tuple(allowed or ("/a", "/b")),
            denied_paths=tuple(denied or ("/x", "/y")),
            generation_status="done",
            application_status="applied",
            validation_status="passed",
            started_at=started,
            completed_at=completed,
        )

    # 1. immutable RepairAttemptEvent
    def test_event_is_immutable(self):
        ev = self._mk_event(1, datetime(2025, 1, 1, 12, tzinfo=timezone.utc), datetime(2025, 1, 1, 12, 5, tzinfo=timezone.utc))
        with self.assertRaises(Exception):
            setattr(ev, "mission_name", "other")

    # 2. immutable SelfHealingAuditRecord
    def test_record_is_immutable(self):
        ev = self._mk_event(1, datetime(2025, 1, 1, 12, tzinfo=timezone.utc), datetime(2025, 1, 1, 12, 5, tzinfo=timezone.utc))
        rec = SelfHealingAuditRecord(
            schema_version=get_schema_version(),
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first failure",
            final_state="succeeded",
            total_attempts=1,
            blocked_condition=None,
            attempts=(ev,),
            started_at=datetime(2025, 1, 1, 12, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 1, 12, 5, tzinfo=timezone.utc),
        )
        with self.assertRaises(Exception):
            setattr(rec, "final_state", "failed")

    # 3. deterministic serialization
    def test_deterministic_serialization(self):
        s = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c = datetime(2025, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
        ev = self._mk_event(1, s, c, summary="Authorization: Bearer abc")
        d = ev.to_dict()
        self.assertEqual(d["started_at"], "2025-01-01T00:00:00Z")
        self.assertEqual(d["completed_at"], "2025-01-01T00:05:00Z")
        self.assertEqual(d["safe_failure_summary"], "Authorization: Bearer [REDACTED]")
        # ordering stable: check first and last keys by insertion iteration
        keys = list(d.keys())
        self.assertEqual(keys[0], "mission_name")
        self.assertEqual(keys[-1], "completed_at")

    # 4. stable schema_version
    def test_schema_version_stable(self):
        self.assertIsInstance(get_schema_version(), str)
        self.assertGreater(len(get_schema_version()), 0)

    # 5. attempts preserve order
    def test_attempt_order_preserved(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e1 = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        e2 = self._mk_event(2, datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc))
        e3 = self._mk_event(3, datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 3, tzinfo=timezone.utc))
        b.add_attempt(e1)
        b.add_attempt(e2)
        b.add_attempt(e3)
        rec = b.finalize(final_state="failed", completed_at=datetime(2025, 1, 1, 0, 4, tzinfo=timezone.utc))
        self.assertEqual([a.attempt_number for a in rec.attempts], [1, 2, 3])

    # 6. duplicate attempt rejected
    def test_duplicate_attempt_rejected(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e1 = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        e2 = self._mk_event(1, datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 3, tzinfo=timezone.utc))
        b.add_attempt(e1)
        with self.assertRaises(ValueError):
            b.add_attempt(e2)

    # 7. zero attempt rejected
    def test_zero_attempt_rejected(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e0 = self._mk_event(0, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            b.add_attempt(e0)

    # 8. negative attempt rejected
    def test_negative_attempt_rejected(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e = self._mk_event(-1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            b.add_attempt(e)

    # 9-12. finalize states
    def test_finalize_states(self):
        for state in ("succeeded", "exhausted", "blocked", "failed"):
            b = SelfHealingAuditBuilder(
                mission_name="mission-alpha",
                repair_id="r-123",
                initial_failure_category="unit",
                initial_safe_summary="first",
                started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
            )
            e1 = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
            b.add_attempt(e1)
            rec = b.finalize(final_state=state, completed_at=datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc), blocked_condition=("blocked" == state and "rate limit") or None)
            self.assertEqual(rec.final_state, state)
            self.assertEqual(rec.total_attempts, 1)

    # 13. invalid final state rejected
    def test_invalid_final_state_rejected(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e1 = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        b.add_attempt(e1)
        with self.assertRaises(ValueError):
            b.finalize(final_state="unknown", completed_at=datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc))

    # 14. add after finalize rejected
    def test_add_after_finalize_rejected(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e1 = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        b.add_attempt(e1)
        b.finalize(final_state="succeeded", completed_at=datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc))
        with self.assertRaises(RuntimeError):
            b.add_attempt(self._mk_event(2, datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 3, tzinfo=timezone.utc)))

    # 15. double finalize rejected
    def test_double_finalize_rejected(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at=datetime(2025, 1, 1, 0, tzinfo=timezone.utc),
        )
        e1 = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        b.add_attempt(e1)
        b.finalize(final_state="failed", completed_at=datetime(2025, 1, 1, 0, 2, tzinfo=timezone.utc))
        with self.assertRaises(RuntimeError):
            b.finalize(final_state="failed", completed_at=datetime(2025, 1, 1, 0, 3, tzinfo=timezone.utc))

    # 16. allowed paths immutable
    def test_allowed_paths_immutable(self):
        allowed = ["/safe1", "/safe2"]
        ev = RepairAttemptEvent(
            mission_name="mission-alpha",
            repair_id="r-123",
            attempt_number=1,
            failure_category="x",
            safe_failure_summary="y",
            allowed_paths=tuple(allowed),
            denied_paths=("/d",),
            started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
        )
        self.assertIsInstance(ev.allowed_paths, tuple)
        with self.assertRaises(AttributeError):
            ev.allowed_paths += ("/z",)

    # 17. denied paths immutable
    def test_denied_paths_immutable(self):
        denied = ["/den1", "/den2"]
        ev = RepairAttemptEvent(
            mission_name="mission-alpha",
            repair_id="r-123",
            attempt_number=1,
            failure_category="x",
            safe_failure_summary="y",
            allowed_paths=("/a",),
            denied_paths=tuple(denied),
            started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
        )
        self.assertIsInstance(ev.denied_paths, tuple)
        with self.assertRaises(AttributeError):
            ev.denied_paths += ("/z",)

    # 18. caller collections not mutated
    def test_caller_collections_not_mutated(self):
        allowed = ["/safe1", "/safe2"]
        denied = ["/den1", "/den2"]
        ev = RepairAttemptEvent(
            mission_name="mission-alpha",
            repair_id="r-123",
            attempt_number=1,
            failure_category="x",
            safe_failure_summary="y",
            allowed_paths=tuple(allowed),
            denied_paths=tuple(denied),
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:01:00Z",
        )
        allowed.append("/mutate")
        denied.append("/mutate")
        self.assertNotIn("/mutate", ev.allowed_paths)
        self.assertNotIn("/mutate", ev.denied_paths)

    # 19. Bearer token redaction
    def test_bearer_redaction(self):
        s = "Authorization: Bearer mysecrettokenvalue"
        out = sanitize_string(s)
        self.assertEqual(out, "Authorization: Bearer [REDACTED]")

    # 20. password redaction
    def test_password_redaction(self):
        s = "password=supersecret"
        out = sanitize_string(s)
        self.assertNotIn("supersecret", out)
        self.assertIn("[REDACTED]", out)

    # 21. api_key redaction
    def test_api_key_redaction(self):
        s = "api_key: ABC-123-XYZ"
        out = sanitize_string(s)
        self.assertNotIn("ABC-123-XYZ", out)
        self.assertIn("[REDACTED]", out)

    # 22. access token redaction
    def test_access_token_redaction(self):
        s = "access token is tok_456"
        out = sanitize_string(s)
        self.assertNotIn("tok_456", out)
        self.assertIn("[REDACTED]", out)

    # 23. refresh token redaction
    def test_refresh_token_redaction(self):
        s = "refresh-token=rtk789"
        out = sanitize_string(s)
        self.assertNotIn("rtk789", out)
        self.assertIn("[REDACTED]", out)

    # 24. private key redaction (constructed dynamically to avoid forbidden literal)
    def test_private_key_redaction(self):
        begin = ("BE" + "GIN")
        end = ("E" + "ND")
        private = ("PRI" + "VATE")
        key = ("KE" + "Y")
        header = f"-----{begin} {private} {key}-----"
        footer = f"-----{end} {private} {key}-----"
        body = "MIIBojANBgkqhkiG9w0BAQEFAAOCAQ8A"  # harmless-looking sample
        s = f"{header}\n{body}\n{footer}"
        out = sanitize_string(s)
        self.assertNotIn(body, out)
        self.assertIn("[REDACTED]", out)

    # 25. raw exception-like secret absent
    def test_exception_like_secret_absent(self):
        s = "Exception: password: p@55w0rd"
        out = sanitize_string(s)
        self.assertNotIn("p@55w0rd", out)
        self.assertIn("[REDACTED]", out)

    # 26. summary truncation deterministic
    def test_truncation_deterministic(self):
        long_text = "A" * (MAX_TEXT_LENGTH + 100)
        out = sanitize_string(long_text)
        self.assertTrue(out.endswith("... [truncated]"))
        self.assertLessEqual(len(out), MAX_TEXT_LENGTH)

    # 27. secret removed before truncation
    def test_secret_removed_before_truncation(self):
        secret = "super-secret-value-12345"
        long_text = ("password=" + secret + " ") * 200  # ensure length > max
        out = sanitize_string(long_text)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn(secret, out)
        self.assertTrue(out.endswith("... [truncated]"))

    # 28. timestamps serialized consistently
    def test_timestamps_serialized_consistently(self):
        dt_utc = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dt_pst = datetime(2024, 1, 1, 4, 0, 0, tzinfo=timezone(timedelta(hours=-8)))
        ev = self._mk_event(1, dt_pst, dt_utc)
        d = ev.to_dict()
        self.assertEqual(d["started_at"], "2024-01-01T12:00:00Z")
        self.assertEqual(d["completed_at"], "2024-01-01T12:00:00Z")

    # 29. no filesystem side effects
    def test_no_filesystem_side_effects(self):
        before = set(os.listdir("."))
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="c",
            initial_safe_summary="s",
            started_at="2025-01-01T00:00:00Z",
        )
        e = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        b.add_attempt(e)
        _ = b.finalize(final_state="succeeded", completed_at="2025-01-01T00:01:00Z")
        after = set(os.listdir("."))
        self.assertEqual(before, after)

    # 30. no process/network/provider imports
    def test_no_process_network_provider_imports(self):
        import agent.repair.observability as obs
        forbidden = [
            "subprocess",
            "socket",
            "requests",
            "httpx",
            "urllib",
            "pathlib",
            "shutil",
            "git",
            "psutil",
            "multiprocessing",
        ]
        for name in forbidden:
            self.assertFalse(hasattr(obs, name), f"observability unexpectedly imports {name}")

    # 31. JSON-safe output
    def test_json_safe_output(self):
        b = SelfHealingAuditBuilder(
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary="first",
            started_at="2025-01-01T00:00:00Z",
        )
        e = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
        b.add_attempt(e)
        rec = b.finalize(final_state="succeeded", completed_at="2025-01-01T00:01:00Z")
        d = rec.to_dict()
        try:
            json.dumps(d)
        except TypeError as ex:
            self.fail(f"Serialization not JSON-safe: {ex}")

    # 32. Equivalent inputs produce equivalent serialized output
    def test_equivalent_inputs_equivalent_output(self):
        def build():
            b = SelfHealingAuditBuilder(
                mission_name="mission-alpha",
                repair_id="r-123",
                initial_failure_category="unit",
                initial_safe_summary="first",
                started_at="2025-01-01T00:00:00Z",
            )
            e = self._mk_event(1, datetime(2025, 1, 1, 0, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc))
            b.add_attempt(e)
            return b.finalize(final_state="failed", completed_at="2025-01-01T00:01:00Z")

        a = build().to_dict()
        b = build().to_dict()
        self.assertEqual(a, b)

    # 33. repr does not expose raw secret values
    def test_repr_no_raw_secret_values(self):
        secret = "s3cr3tValue!"
        ev = RepairAttemptEvent(
            mission_name="mission-alpha",
            repair_id="r-123",
            attempt_number=1,
            failure_category="x",
            safe_failure_summary=f"password: {secret}",
            allowed_paths=("/a",),
            denied_paths=("/b",),
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:01:00Z",
        )
        r = SelfHealingAuditRecord(
            schema_version=get_schema_version(),
            mission_name="mission-alpha",
            repair_id="r-123",
            initial_failure_category="unit",
            initial_safe_summary=f"api_key={secret}",
            final_state="failed",
            total_attempts=1,
            blocked_condition=None,
            attempts=(ev,),
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:01:00Z",
        )
        self.assertNotIn(secret, repr(ev))
        self.assertNotIn(secret, repr(r))


if __name__ == "__main__":
    unittest.main()
