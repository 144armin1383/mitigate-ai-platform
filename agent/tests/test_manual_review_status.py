import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.runtime.manual_review_status import (
    normalize_mission_status,
    normalize_request_status,
)


class ManualReviewStatusTests(unittest.TestCase):
    def _write_evidence(self, root: Path, mission_id: str, reason: str) -> None:
        directory = root / "runtime" / "failure-evidence"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{mission_id}.json").write_text(
            json.dumps({"mission_id": mission_id, "reason": reason}),
            encoding="utf-8",
        )

    def test_manual_review_is_exposed_as_awaiting_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_evidence(root, "m-review-1", "manual_review_required")
            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                result = normalize_mission_status(
                    {"id": "m-review-1", "state": "blocked", "attempts_done": 0}
                )

        self.assertEqual(result["state"], "awaiting_approval")
        self.assertEqual(result["queue_state"], "blocked")
        self.assertEqual(result["status_reason"], "manual_review_required")
        self.assertEqual(result["requires_action"], "manual_review")

    def test_real_blocker_remains_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_evidence(root, "m-blocked-1", "runtime_produced_no_changes")
            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                result = normalize_mission_status(
                    {"id": "m-blocked-1", "state": "blocked"}
                )

        self.assertEqual(result["state"], "blocked")
        self.assertNotIn("queue_state", result)
        self.assertNotIn("requires_action", result)

    def test_request_status_reports_approval_gate_truthfully(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_evidence(root, "m-review-2", "manual_review_required")
            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                result = normalize_request_status(
                    {
                        "request_id": "req-review-2",
                        "status": "blocked",
                        "missions": [
                            {
                                "mission": {"id": "m-review-2", "state": "blocked"},
                                "execution": None,
                            }
                        ],
                    }
                )

        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(result["status_reason"], "manual_review_required")
        self.assertEqual(result["requires_action"], "manual_review")
        self.assertEqual(
            result["missions"][0]["mission"]["state"],
            "awaiting_approval",
        )


if __name__ == "__main__":
    unittest.main()
