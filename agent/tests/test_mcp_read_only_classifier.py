from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.runtime.runtime_mcp_server import (
    _effective_task_type,
    _explicit_read_only_inspection,
    _manual_review_decision_history,
)


class MCPReadOnlyClassifierTests(unittest.TestCase):
    def test_canvas_negated_modify_constraint_is_inspection(self) -> None:
        message = (
            "NEW governed MITIGATE mission. Task: Perform a read-only inspection "
            "of the MITIGATE repository. Confirm that it is a Git checkout and "
            "briefly report its purpose. Constraints: Use MITIGATE Core governed "
            "execution. Do not edit the Agent Canvas conversation workspace directly. "
            "Do not directly inspect or modify the canonical MITIGATE checkout from "
            "Agent Canvas. Production runtime must operate in a MITIGATE-governed "
            "disposable workspace where applicable. Do not modify any files."
        )
        self.assertTrue(_explicit_read_only_inspection(message))
        self.assertEqual("inspection", _effective_task_type(message, "backend"))

    def test_real_write_intent_stays_backend(self) -> None:
        message = (
            "Perform a read-only inspection first, then implement the fix. "
            "Do not modify any files during the inspection phase."
        )
        self.assertFalse(_explicit_read_only_inspection(message))
        self.assertEqual("backend", _effective_task_type(message, "backend"))

    def test_manual_review_history_is_machine_readable_and_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            directory = root / "runtime" / "approvals"
            directory.mkdir(parents=True)
            history = directory / "decision-history.jsonl"
            history.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "record_type": "manual_review_decision",
                                "mission_id": "m1",
                                "decision": "approved",
                            }
                        ),
                        json.dumps(
                            {
                                "record_type": "manual_review_decision",
                                "mission_id": "m2",
                                "decision": "rejected",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"MITIGATE_AI_DATA_ROOT": str(root)}):
                result = _manual_review_decision_history(10)
            self.assertEqual(2, result["count"])
            self.assertEqual("m2", result["items"][0]["mission_id"])
            self.assertEqual("rejected", result["items"][0]["decision"])


if __name__ == "__main__":
    unittest.main()
