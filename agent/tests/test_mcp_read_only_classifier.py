from __future__ import annotations

import unittest

from agent.runtime.runtime_mcp_server import (
    _effective_task_type,
    _explicit_read_only_inspection,
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


if __name__ == "__main__":
    unittest.main()
