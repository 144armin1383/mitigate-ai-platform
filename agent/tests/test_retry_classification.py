import unittest
import asyncio
from agent.resilience.retry_classification import (
    RetryCategory,
    RetryClassifier,
    ClassificationResult,
)


class TestRetryClassification(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = RetryClassifier()

    def test_all_supported_categories(self) -> None:
        # exhausted dominates
        r = self.classifier.classify(RuntimeError("X"), exhausted=True)
        self.assertEqual(r.category, RetryCategory.EXHAUSTED)
        self.assertEqual(r.to_dict()["classification"], "exhausted")

        # cancelled via flag
        r = self.classifier.classify(RuntimeError("X"), cancelled=True)
        self.assertEqual(r.category, RetryCategory.CANCELLED)

        # cancelled via exception type
        r = self.classifier.classify(asyncio.CancelledError())
        self.assertEqual(r.category, RetryCategory.CANCELLED)

        # deadline via flag
        r = self.classifier.classify(RuntimeError("X"), deadline_exceeded=True)
        self.assertEqual(r.category, RetryCategory.DEADLINE_EXCEEDED)

        # deadline via exception type
        r = self.classifier.classify(TimeoutError())
        self.assertEqual(r.category, RetryCategory.DEADLINE_EXCEEDED)

        # retryable via hint
        r = self.classifier.classify(RuntimeError("X"), retryable_hint=True)
        self.assertEqual(r.category, RetryCategory.RETRYABLE)

        # non-retryable via hint
        r = self.classifier.classify(RuntimeError("X"), retryable_hint=False)
        self.assertEqual(r.category, RetryCategory.NON_RETRYABLE)

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            self.classifier.classify(None)

    def test_deterministic_classification(self) -> None:
        e = RuntimeError("boom")
        r1 = self.classifier.classify(e, retryable_hint=False, reason="x", metadata={"k": "v"})
        r2 = self.classifier.classify(e, retryable_hint=False, reason="x", metadata={"k": "v"})
        self.assertEqual(r1.category, r2.category)
        self.assertEqual(r1.to_dict(), r2.to_dict())

    def test_provider_neutral_metadata(self) -> None:
        r = self.classifier.classify(RuntimeError("x"), retryable_hint=True, metadata={"code": 123, "info": None})
        d = r.to_dict()
        self.assertIn("metadata", d)
        self.assertEqual(d["metadata"], {"code": "123", "info": ""})

    def test_cancellation_deadline_distinction(self) -> None:
        r1 = self.classifier.classify(asyncio.CancelledError())
        r2 = self.classifier.classify(TimeoutError())
        self.assertEqual(r1.category, RetryCategory.CANCELLED)
        self.assertEqual(r2.category, RetryCategory.DEADLINE_EXCEEDED)

    def test_retryable_nonretryable_distinction(self) -> None:
        r1 = self.classifier.classify(RuntimeError("x"), retryable_hint=True)
        r2 = self.classifier.classify(RuntimeError("x"), retryable_hint=False)
        self.assertEqual(r1.category, RetryCategory.RETRYABLE)
        self.assertEqual(r2.category, RetryCategory.NON_RETRYABLE)


if __name__ == "__main__":
    unittest.main()
