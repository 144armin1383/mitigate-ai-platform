import unittest

from agent.resilience.retry_budget import RetryBudget


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += float(dt)


class TestRetryBudget(unittest.TestCase):
    def test_bounded_budget_consumption(self) -> None:
        clk = FakeClock(100.0)
        b = RetryBudget(max_retries=3, time_provider=clk)
        self.assertTrue(b.can_retry())
        self.assertEqual(b.remaining_retries, 3)
        self.assertTrue(b.consume())
        self.assertEqual(b.remaining_retries, 2)
        self.assertTrue(b.consume())
        self.assertEqual(b.remaining_retries, 1)
        self.assertTrue(b.consume())
        self.assertEqual(b.remaining_retries, 0)
        self.assertFalse(b.can_retry())
        self.assertFalse(b.consume())
        self.assertEqual(b.exhaustion_reason(), "attempts")

    def test_invalid_negative_values_and_bool_edges(self) -> None:
        with self.assertRaises(ValueError):
            RetryBudget(max_retries=-1)
        with self.assertRaises(TypeError):
            RetryBudget(max_retries=True)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            RetryBudget(deadline_seconds=True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            RetryBudget(deadline_seconds=-0.1)

    def test_unlimited_mode(self) -> None:
        clk = FakeClock(0.0)
        b = RetryBudget.unlimited()
        self.assertTrue(b.is_unlimited)
        # Without limits, can always retry; consumption increments for introspection
        for _ in range(100):
            self.assertTrue(b.can_retry())
            self.assertTrue(b.consume())
        self.assertIsNone(b.remaining_retries)
        self.assertIsNone(b.exhaustion_reason())

    def test_time_budget_only(self) -> None:
        clk = FakeClock(10.0)
        b = RetryBudget.with_time_budget(seconds=5.0, time_provider=clk)
        # up to deadline
        self.assertTrue(b.can_retry())
        self.assertTrue(b.consume())
        self.assertIsNone(b.remaining_retries)
        self.assertAlmostEqual(b.time_remaining(), 5.0)
        clk.advance(4.0)
        self.assertTrue(b.can_retry())
        clk.advance(1.0)
        # at deadline -> cannot retry
        self.assertEqual(b.time_remaining(), 0.0)
        self.assertFalse(b.can_retry())
        self.assertEqual(b.exhaustion_reason(), "deadline")

    def test_deterministic_remaining(self) -> None:
        clk = FakeClock(0.0)
        b = RetryBudget(max_retries=2, deadline_seconds=10.0, time_provider=clk)
        r1 = b.remaining_retries
        r2 = b.remaining_retries
        self.assertEqual(r1, r2)
        b.consume()
        self.assertEqual(b.remaining_retries, 1)
        clk.advance(20.0)
        # deadline exceeded -> cannot retry, remaining stays non-negative
        self.assertFalse(b.can_retry())
        self.assertEqual(b.remaining_retries, 1)
        self.assertEqual(b.exhaustion_reason(), "deadline")


if __name__ == "__main__":
    unittest.main()
