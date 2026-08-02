from __future__ import annotations

import unittest

from agent.ai.retry_engine import (
    FailureCategory,
    FailureContext,
    FinalStatus,
    RetryConfiguration,
    RetryEngine,
)


class TestRetryEngine(unittest.TestCase):
    def test_success_on_first_attempt(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Build reliable component")
        engine.record_success("All green")
        report = engine.build_report().to_dict()
        self.assertEqual(report["status"], "succeeded")
        self.assertEqual(report["attempts_used"], 1)
        self.assertEqual(report["attempts_remaining"], cfg.max_attempts - 1)
        self.assertTrue(report["attempts"][0]["succeeded"]) 

    def test_success_after_one_retry(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Build reliable component")

        ctx = FailureContext(
            category=FailureCategory.COMPILATION,
            summary="SyntaxError: invalid syntax",
            error_output="E   SyntaxError: invalid syntax at line 1",
        )
        d1 = engine.record_failure(ctx)
        self.assertTrue(d1.retryable)
        self.assertFalse(d1.blocked)
        self.assertIsNotNone(d1.instructions)

        engine.record_success("Fixed")
        report = engine.build_report().to_dict()
        self.assertEqual(report["status"], "succeeded")
        self.assertEqual(report["attempts_used"], 2)
        self.assertEqual(report["attempts_remaining"], cfg.max_attempts - 2)

    def test_max_attempt_exhaustion(self) -> None:
        cfg = RetryConfiguration(max_attempts=2)
        engine = RetryEngine(cfg, mission_requirements="Mission: Retry until done")

        d1 = engine.record_failure(FailureContext(
            category=FailureCategory.COMPILATION,
            summary="NameError: name X is not defined",
            error_output="Traceback... NameError: name X is not defined",
        ))
        self.assertTrue(d1.retryable)
        self.assertEqual(engine.attempts_remaining, 1)

        d2 = engine.record_failure(FailureContext(
            category=FailureCategory.TESTING,
            summary="2 tests failed",
            test_failures=["test_a", "test_b"],
            error_output="FAILED tests/test_a.py::test_a - AssertionError: expected 1 == 2",
        ))
        self.assertFalse(d2.retryable)
        self.assertIn("Maximum retry attempts exhausted", d2.reason)
        report = engine.build_report().to_dict()
        self.assertEqual(report["status"], "exhausted")
        self.assertEqual(report["attempts_used"], 2)
        self.assertEqual(report["attempts_remaining"], 0)

    def test_security_failures_never_retried(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Secure operations")
        d = engine.record_failure(FailureContext(
            category=FailureCategory.POLICY,
            summary="Security policy violated: unsafe content",
            policy_violation=True,
        ))
        self.assertFalse(d.retryable)
        self.assertTrue(d.blocked)
        report = engine.build_report().to_dict()
        self.assertEqual(report["status"], "blocked")

    def test_provider_auth_billing_failures_never_retried(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Provider stability")
        d = engine.record_failure(FailureContext(
            category=FailureCategory.PROVIDER,
            summary="401 Unauthorized",
            provider_auth_error=True,
        ))
        self.assertFalse(d.retryable)
        self.assertTrue(d.blocked)
        report = engine.build_report().to_dict()
        self.assertEqual(report["status"], "blocked")

    def test_unittest_failures_are_retryable(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Tests pass")
        d = engine.record_failure(FailureContext(
            category=FailureCategory.TESTING,
            summary="1 failed, 1 error",
            test_failures=["test_feature_x"],
            error_output="FAILED test_feature_x - AssertionError: expected True is False",
        ))
        self.assertTrue(d.retryable)
        self.assertFalse(d.blocked)

    def test_compilation_failures_are_retryable(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Build module")
        d = engine.record_failure(FailureContext(
            category=FailureCategory.COMPILATION,
            summary="ImportError: cannot import name Y",
            error_output="ImportError: cannot import name Y from module Z",
        ))
        self.assertTrue(d.retryable)

    def test_secret_redaction(self) -> None:
        cfg = RetryConfiguration(safe_error_bytes=256)
        engine = RetryEngine(cfg, mission_requirements="Mission: Redact secrets")
        error_text = (
            "Connecting with API_KEY=abcdef123456\n"
            "Authorization: Bearer very.secret.jwt.token\n"
            "token=tok_12345_normal\n"
            "All done.\n"
        )
        engine.record_failure(FailureContext(
            category=FailureCategory.TESTING,
            summary="Secret present in logs",
            error_output=error_text,
        ))
        attempt = engine.attempts[0]
        snippet = attempt.error_output_snippet or ""
        self.assertIn("[REDACTED]", snippet)
        self.assertNotIn("abcdef123456", snippet)
        self.assertNotIn("very.secret.jwt.token", snippet)
        self.assertNotIn("tok_12345_normal", snippet)

    def test_error_output_truncation(self) -> None:
        cfg = RetryConfiguration(safe_error_bytes=50)
        engine = RetryEngine(cfg, mission_requirements="Mission: Truncate logs safely")
        long_error = (
            "Authorization: Bearer this.is.a.very.long.token.value.should.be.redacted "
            "A" * 200
        )
        engine.record_failure(FailureContext(
            category=FailureCategory.TESTING,
            summary="Long error output",
            error_output=long_error,
        ))
        attempt = engine.attempts[0]
        snippet = attempt.error_output_snippet or ""
        # Must not exceed byte limit
        self.assertLessEqual(len(snippet.encode("utf-8")), 50)
        # Ensure redaction occurred before truncation
        self.assertIn("[REDACTED]", snippet)
        # Must be valid UTF-8 (decode without errors)
        snippet.encode("utf-8").decode("utf-8")

    def test_deterministic_report_serialization(self) -> None:
        cfg = RetryConfiguration()
        engine = RetryEngine(cfg, mission_requirements="Mission: Determinism")
        engine.record_failure(FailureContext(
            category=FailureCategory.PARSING,
            summary="Invalid JSON output",
            error_output="Expecting property name enclosed in double quotes: line 1 column 2",
            invalid_ai_output=True,
        ))
        d1 = engine.build_report().to_dict()
        d2 = engine.build_report().to_dict()
        self.assertEqual(d1, d2)

    def test_configured_max_attempts_enforced(self) -> None:
        cfg = RetryConfiguration(max_attempts=1)
        engine = RetryEngine(cfg, mission_requirements="Mission: Enforce attempts")
        d = engine.record_failure(FailureContext(
            category=FailureCategory.COMPILATION,
            summary="Compile error",
            error_output="SyntaxError",
        ))
        self.assertFalse(d.retryable)
        self.assertIn("Maximum retry attempts exhausted", d.reason)

    def test_positive_safe_error_bytes_validation(self) -> None:
        with self.assertRaises(ValueError):
            RetryConfiguration(safe_error_bytes=0)
        with self.assertRaises(ValueError):
            RetryConfiguration(safe_error_bytes=-1)
        # Small positive value should be accepted
        cfg = RetryConfiguration(safe_error_bytes=50)
        self.assertEqual(cfg.safe_error_bytes, 50)


if __name__ == "__main__":
    unittest.main()
