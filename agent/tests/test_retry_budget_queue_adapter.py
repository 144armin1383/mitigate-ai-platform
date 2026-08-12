import copy
import unittest

from agent.resilience.retry_budget_queue_adapter import (
    RetryBudgetProjectionError,
    project_retry_budget,
)


class TestRetryBudgetQueueAdapter(unittest.TestCase):
    def test_zero_retries_grants_no_retry(self):
        mission = {"attempts_done": 0, "max_retries": 0, "state": "failed"}
        view = project_retry_budget(mission)
        self.assertEqual(view.retries_remaining, 0)
        self.assertTrue(view.exhausted)
        self.assertFalse(view.eligible)

    def test_one_retry_semantics(self):
        # Before retry
        mission = {"attempts_done": 0, "max_retries": 1, "state": "failed"}
        view = project_retry_budget(mission)
        self.assertEqual(view.retries_remaining, 1)
        self.assertFalse(view.exhausted)
        self.assertTrue(view.eligible)
        # After one retry consumed
        mission2 = {"attempts_done": 1, "max_retries": 1, "state": "failed"}
        view2 = project_retry_budget(mission2)
        self.assertEqual(view2.retries_remaining, 0)
        self.assertTrue(view2.exhausted)
        self.assertFalse(view2.eligible)

    def test_multiple_retries_deterministic(self):
        mission = {"attempts_done": 2, "max_retries": 5, "state": "failed"}
        v1 = project_retry_budget(mission)
        v2 = project_retry_budget(mission)
        self.assertEqual(v1.retries_remaining, 3)
        self.assertEqual(v2.retries_remaining, 3)
        self.assertEqual(v1, v2)
        self.assertTrue(v1.eligible)

    def test_exhaustion_when_attempts_exceed_budget(self):
        mission = {"attempts_done": 10, "max_retries": 3, "state": "failed"}
        view = project_retry_budget(mission)
        self.assertEqual(view.retries_remaining, 0)
        self.assertTrue(view.exhausted)
        self.assertFalse(view.eligible)

    def test_malformed_attempts_done_bool_rejected(self):
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": True, "max_retries": 3, "state": "failed"})
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": False, "max_retries": 3, "state": "failed"})

    def test_malformed_attempts_done_type_and_negative(self):
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": -1, "max_retries": 3, "state": "failed"})
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": 1.5, "max_retries": 3, "state": "failed"})
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": "2", "max_retries": 3, "state": "failed"})

    def test_malformed_max_retries_bool_rejected(self):
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": 0, "max_retries": True, "state": "failed"})
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": 0, "max_retries": False, "state": "failed"})

    def test_malformed_max_retries_type_and_negative(self):
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": 0, "max_retries": -5, "state": "failed"})
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": 0, "max_retries": 3.14, "state": "failed"})
        with self.assertRaises(RetryBudgetProjectionError):
            project_retry_budget({"attempts_done": 0, "max_retries": "4", "state": "failed"})

    def test_retrying_state_is_eligible_with_budget(self):
        mission = {"attempts_done": 0, "max_retries": 2, "status": "retrying"}
        view = project_retry_budget(mission)
        self.assertTrue(view.eligible)
        self.assertFalse(view.exhausted)
        self.assertEqual(view.retries_remaining, 2)

    def test_failed_state_is_eligible_with_budget(self):
        mission = {"attempts_done": 1, "max_retries": 3, "phase": "failed"}
        view = project_retry_budget(mission)
        self.assertTrue(view.eligible)
        self.assertFalse(view.exhausted)
        self.assertEqual(view.retries_remaining, 2)

    def test_completed_state_not_eligible_even_with_budget(self):
        mission = {"attempts_done": 0, "max_retries": 5, "state": "completed"}
        view = project_retry_budget(mission)
        self.assertFalse(view.eligible)
        self.assertFalse(view.exhausted)  # budget exists, but cannot be used
        self.assertEqual(view.retries_remaining, 5)

    def test_blocked_state_not_eligible_even_with_budget(self):
        mission = {"attempts_done": 0, "max_retries": 2, "state": "blocked"}
        view = project_retry_budget(mission)
        self.assertFalse(view.eligible)
        self.assertFalse(view.exhausted)
        self.assertEqual(view.retries_remaining, 2)

    def test_running_and_stale_running_not_eligible(self):
        running = {"attempts_done": 0, "max_retries": 2, "state": "running"}
        stale = {"attempts_done": 0, "max_retries": 2, "state": "stale-running"}
        r_view = project_retry_budget(running)
        s_view = project_retry_budget(stale)
        self.assertFalse(r_view.eligible)
        self.assertFalse(s_view.eligible)
        self.assertEqual(r_view.retries_remaining, 2)
        self.assertEqual(s_view.retries_remaining, 2)

    def test_legacy_record_defaults_fail_closed(self):
        # Missing fields default to 0/0 and are not eligible
        mission = {"state": "failed"}
        view = project_retry_budget(mission)
        self.assertEqual(view.attempts_done, 0)
        self.assertEqual(view.max_retries, 0)
        self.assertEqual(view.retries_remaining, 0)
        self.assertTrue(view.exhausted)
        self.assertFalse(view.eligible)

    def test_projection_is_side_effect_free_and_input_unchanged(self):
        mission = {"attempts_done": 1, "max_retries": 4, "status": "failed", "meta": {"a": 1}}
        before = copy.deepcopy(mission)
        view = project_retry_budget(mission)
        after = mission
        self.assertEqual(before, after)
        # Repeat to assert determinism and no hidden consumption
        view2 = project_retry_budget(mission)
        self.assertEqual(view, view2)

    def test_adapter_has_no_independent_consumption_authority(self):
        mission = {"attempts_done": 0, "max_retries": 1, "state": "failed"}
        view1 = project_retry_budget(mission)
        view2 = project_retry_budget(mission)
        self.assertEqual(view1.retries_remaining, 1)
        self.assertEqual(view2.retries_remaining, 1)
        self.assertEqual(mission["attempts_done"], 0)


if __name__ == "__main__":
    unittest.main()
