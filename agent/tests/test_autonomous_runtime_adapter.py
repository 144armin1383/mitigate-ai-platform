from __future__ import annotations

import unittest
from typing import Any, Dict

from agent.runtime.autonomous_runtime_adapter import (
    AutonomousRuntimeAdapter,
)


class FakeController:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls = 0

    def run(self, mission: Dict[str, Any]) -> Any:
        self.calls += 1
        return self.result


class AutonomousRuntimeAdapterTests(unittest.TestCase):
    def test_success_maps_to_success(self) -> None:
        controller = FakeController(
            {
                "final_status": "success",
                "attempts": 1,
            }
        )
        adapter = AutonomousRuntimeAdapter(controller)

        result = adapter.execute({"id": "m1"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_status"], "success")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(controller.calls, 1)

    def test_failed_maps_to_exhausted(self) -> None:
        controller = FakeController(
            {
                "final_status": "failed",
                "attempts": 3,
            }
        )
        adapter = AutonomousRuntimeAdapter(controller)

        result = adapter.execute({"id": "m2"})

        self.assertEqual(result["status"], "exhausted")
        self.assertEqual(result["attempts"], 3)

    def test_aborted_maps_to_blocked(self) -> None:
        controller = FakeController(
            {
                "final_status": "aborted",
                "attempts": 1,
            }
        )
        adapter = AutonomousRuntimeAdapter(controller)

        result = adapter.execute({"id": "m3"})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["final_status"], "aborted")

    def test_unknown_status_fails_closed(self) -> None:
        controller = FakeController(
            {
                "final_status": "mystery",
                "attempts": 1,
            }
        )
        adapter = AutonomousRuntimeAdapter(controller)

        result = adapter.execute({"id": "m4"})

        self.assertEqual(result["status"], "blocked")

    def test_invalid_report_fails_closed(self) -> None:
        controller = FakeController(None)
        adapter = AutonomousRuntimeAdapter(controller)

        result = adapter.execute({"id": "m5"})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["final_status"], "invalid_report")
        self.assertEqual(result["attempts"], 0)

    def test_invalid_attempt_count_is_sanitized(self) -> None:
        controller = FakeController(
            {
                "final_status": "success",
                "attempts": "invalid",
            }
        )
        adapter = AutonomousRuntimeAdapter(controller)

        result = adapter.execute({"id": "m6"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
