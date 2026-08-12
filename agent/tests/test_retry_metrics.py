import json
import unittest
from agent.observability.retry_metrics import RetryMetrics
from agent.resilience.retry_classification import RetryCategory


class TestRetryMetrics(unittest.TestCase):
    def test_deterministic_structured_event_generation(self) -> None:
        rm = RetryMetrics(time_provider=lambda: 1234.5)
        evt = rm.attempt_event(
            attempt=2,
            classification=RetryCategory.RETRYABLE,
            budget_remaining=3,
            backoff_seconds=1.25,
            jitter_seconds=1.5,
            circuit_state="closed",
            mission_id="mission-1",
            execution_id="exec-1",
            labels={"component": "worker"},
        )
        expected = {
            "type": "retry_attempt",
            "timestamp": 1234.5,
            "attempt": 2,
            "classification": "retryable",
            "budget_remaining": 3,
            "backoff_delay": 1.25,
            "jittered_delay": 1.5,
            "circuit_state": "closed",
            "mission_id": "mission-1",
            "execution_id": "exec-1",
            "labels": {"component": "worker"},
        }
        self.assertEqual(evt, expected)
        # serialization-safe
        _ = json.dumps(evt)

    def test_optional_fields_and_missing_values(self) -> None:
        rm = RetryMetrics(time_provider=lambda: 42.0)
        evt = rm.attempt_event(attempt=1, classification="non_retryable")
        self.assertEqual(evt["type"], "retry_attempt")
        self.assertEqual(evt["timestamp"], 42.0)
        self.assertEqual(evt["attempt"], 1)
        self.assertEqual(evt["classification"], "non_retryable")
        # optional fields present and None when not provided
        self.assertIn("budget_remaining", evt)
        self.assertIsNone(evt["budget_remaining"])
        self.assertIn("backoff_delay", evt)
        self.assertIsNone(evt["backoff_delay"])
        self.assertIn("jittered_delay", evt)
        self.assertIsNone(evt["jittered_delay"])
        self.assertIn("circuit_state", evt)
        self.assertIsNone(evt["circuit_state"])
        self.assertIn("mission_id", evt)
        self.assertIsNone(evt["mission_id"])
        self.assertIn("execution_id", evt)
        self.assertIsNone(evt["execution_id"])
        self.assertNotIn("labels", evt)  # labels omitted when not provided

    def test_identity_preservation_and_no_input_mutation(self) -> None:
        rm = RetryMetrics(time_provider=lambda: 1.0)
        labels = {"role": "runner"}
        evt = rm.attempt_event(attempt=3, classification="exhausted", labels=labels)
        labels["role"] = "changed"
        # event labels must not be mutated
        self.assertEqual(evt.get("labels"), {"role": "runner"})

    def test_no_secrets_in_labels(self) -> None:
        rm = RetryMetrics(time_provider=lambda: 1.0)
        with self.assertRaises(ValueError):
            rm.attempt_event(attempt=1, classification="retryable", labels={"api_token": "x"})

    def test_attempt_validation(self) -> None:
        rm = RetryMetrics(time_provider=lambda: 0.0)
        with self.assertRaises(TypeError):
            rm.attempt_event(attempt=True, classification="retryable")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            rm.attempt_event(attempt=0, classification="retryable")
        with self.assertRaises(ValueError):
            rm.attempt_event(attempt=1, classification="unknown")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
