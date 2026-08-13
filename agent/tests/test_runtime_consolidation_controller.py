from __future__ import annotations

import unittest

from agent.runtime.runtime_consolidation_controller import RuntimeConsolidationController
from agent.runtime.task_scope_workspace_controller import TaskScopeWorkspaceController


class RuntimeConsolidationControllerTests(unittest.TestCase):
    def test_stable_controller_uses_task_scoped_workspace_controller(self) -> None:
        self.assertTrue(
            issubclass(RuntimeConsolidationController, TaskScopeWorkspaceController)
        )

    def test_backend_without_explicit_deliverables_gets_agent_scope(self) -> None:
        text = (
            "Task Type: backend\n\n"
            "## Objective\n\nFix the bug.\n\n"
            "## Context\n\n```json\n{\"deliverables\": []}\n```\n"
        )
        context = RuntimeConsolidationController._context(text)
        self.assertEqual(context["deliverables"], ["agent"])

    def test_documentation_without_explicit_deliverables_gets_docs_scope(self) -> None:
        text = (
            "Task Type: documentation\n\n"
            "## Objective\n\nWrite the assessment.\n\n"
            "## Context\n\n```json\n{\"deliverables\": []}\n```\n"
        )
        context = RuntimeConsolidationController._context(text)
        self.assertEqual(context["deliverables"], ["docs"])

    def test_explicit_deliverables_are_preserved(self) -> None:
        text = (
            "Task Type: backend\n\n"
            "## Context\n\n```json\n"
            "{\"deliverables\": [\"agent/runtime/example.py\"]}\n"
            "```\n"
        )
        context = RuntimeConsolidationController._context(text)
        self.assertEqual(
            context["deliverables"],
            ["agent/runtime/example.py"],
        )


if __name__ == "__main__":
    unittest.main()
