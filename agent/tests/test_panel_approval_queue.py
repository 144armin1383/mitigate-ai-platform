from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.web.panel_server_approval import _approval_queue_items


class PanelApprovalQueueTests(unittest.TestCase):
    def test_only_manual_review_blockers_are_returned_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            evidence = runtime / "failure-evidence"
            evidence.mkdir(parents=True)

            (runtime / "missions.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "next_seq": 4,
                        "missions": [
                            {
                                "id": "m-old",
                                "state": "blocked",
                                "created_seq": 1,
                                "attempts_done": 1,
                            },
                            {
                                "id": "m-completed",
                                "state": "completed",
                                "created_seq": 2,
                            },
                            {
                                "id": "m-new",
                                "state": "blocked",
                                "created_seq": 3,
                                "attempts_done": 0,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "m-old.json").write_text(
                json.dumps(
                    {
                        "reason": "manual_review_required",
                        "request_id": "request-old",
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "m-new.json").write_text(
                json.dumps(
                    {
                        "reason": "manual_review_required",
                        "request_id": "request-new",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                items = _approval_queue_items()

            self.assertEqual([item["mission_id"] for item in items], ["m-new", "m-old"])
            self.assertEqual(items[0]["request_id"], "request-new")
            self.assertEqual(items[0]["status"], "awaiting_approval")
            self.assertEqual(items[0]["reason"], "manual_review_required")

    def test_keyed_mission_mapping_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            evidence = runtime / "failure-evidence"
            evidence.mkdir(parents=True)

            (runtime / "missions.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "next_seq": 114,
                        "missions": {
                            "m1786738458692488": {
                                "attempts_done": 0,
                                "created_seq": 113,
                                "dependencies": [],
                                "max_retries": 2,
                                "priority": 8,
                                "state": "blocked",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "m1786738458692488.json").write_text(
                json.dumps(
                    {
                        "reason": "manual_review_required",
                        "request_id": "canvas-20260814T201418Z-f070a8",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                items = _approval_queue_items()

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["mission_id"], "m1786738458692488")
            self.assertEqual(
                items[0]["request_id"], "canvas-20260814T201418Z-f070a8"
            )
            self.assertEqual(items[0]["status"], "awaiting_approval")

    def test_direct_top_level_mission_mapping_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            evidence = runtime / "failure-evidence"
            evidence.mkdir(parents=True)

            (runtime / "missions.json").write_text(
                json.dumps(
                    {
                        "m-direct": {
                            "state": "blocked",
                            "created_seq": 9,
                            "attempts_done": 0,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "m-direct.json").write_text(
                json.dumps(
                    {
                        "reason": "manual_review_required",
                        "request_id": "request-direct",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                items = _approval_queue_items()

            self.assertEqual([item["mission_id"] for item in items], ["m-direct"])

    def test_non_manual_blocker_is_not_exposed_as_approval(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime"
            evidence = runtime / "failure-evidence"
            evidence.mkdir(parents=True)
            (runtime / "missions.json").write_text(
                json.dumps(
                    {
                        "missions": [
                            {"id": "m1", "state": "blocked", "created_seq": 1}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "m1.json").write_text(
                json.dumps({"reason": "runtime_produced_no_changes"}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MITIGATE_AI_DATA_ROOT": str(root)}):
                self.assertEqual(_approval_queue_items(), [])


if __name__ == "__main__":
    unittest.main()
