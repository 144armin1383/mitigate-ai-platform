from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import ExecutionEvidence, ExecutionResult, RuntimeStatus
from agent.runtime.runtime_consolidation_controller import (
    AUTO_ROUTE_DENIED_PATHS,
    RuntimeConsolidationController,
)


class RuntimeConsolidationControllerTests(unittest.TestCase):
    def test_context_parser_reads_explicit_runtime_execution_block(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "agent" / "missions").mkdir(parents=True)
            mission_id = "example"
            (root / "agent" / "missions" / f"{mission_id}.md").write_text(
                "# Example\n\n## Context\n\n```json\n{\"runtime_execution\": {\"enabled\": true}}\n```\n",
                encoding="utf-8",
            )
            controller = object.__new__(RuntimeConsolidationController)
            controller.agent_root = root / "agent"
            context, _content = controller._mission_context(mission_id)
            self.assertTrue(context["runtime_execution"]["enabled"])

    def test_capability_mapping_is_fail_closed_by_default(self) -> None:
        caps = RuntimeConsolidationController._capabilities({"coding": True, "tests": True})
        self.assertTrue(caps.coding)
        self.assertTrue(caps.tests)
        self.assertFalse(caps.browser)
        self.assertFalse(caps.multi_agent)

    def test_ordinary_backend_mission_auto_routes_to_openhands(self) -> None:
        content = (
            "# Example\n\n"
            "Task Type: backend\n\n"
            "## Objective\n\nFix the bounded application bug.\n"
        )
        context = {
            "objective": "Fix the bounded application bug.",
            "deliverables": ["src/example.py", "tests/test_example.py"],
            "acceptance_criteria": ["tests pass"],
        }

        execution = RuntimeConsolidationController._automatic_runtime_execution(
            content=content,
            context=context,
        )

        self.assertIsNotNone(execution)
        assert execution is not None
        self.assertTrue(execution["enabled"])
        self.assertEqual(["openhands"], execution["preferred"])
        self.assertTrue(execution["require"]["isolated_workspace"])
        self.assertTrue(execution["metadata"]["automatic_runtime_routing"])

    def test_auto_route_requires_non_empty_deliverable_allowlist(self) -> None:
        execution = RuntimeConsolidationController._automatic_runtime_execution(
            content="Task Type: backend\n\n## Objective\n\nFix it.\n",
            context={"objective": "Fix it.", "deliverables": []},
        )
        self.assertIsNone(execution)

    def test_auto_route_rejects_core_maintenance_marker(self) -> None:
        execution = RuntimeConsolidationController._automatic_runtime_execution(
            content=(
                "Task Type: backend\n\n"
                "CORE_MAINTENANCE_APPROVED\n\n"
                "## Objective\n\nChange runtime core.\n"
            ),
            context={
                "objective": "Change runtime core.",
                "deliverables": ["agent/runtime/example.py"],
            },
        )
        self.assertIsNone(execution)

    def test_testing_task_type_is_approved_for_openhands_auto_route(self) -> None:
        execution = RuntimeConsolidationController._automatic_runtime_execution(
            content="Task Type: testing\n\n## Objective\n\nRun bounded tests.\n",
            context={
                "objective": "Run bounded tests.",
                "deliverables": ["tests/test_example.py"],
            },
        )

        self.assertIsNotNone(execution)
        assert execution is not None
        self.assertEqual(["openhands"], execution["preferred"])

    def test_auto_route_rejects_unapproved_task_type(self) -> None:
        execution = RuntimeConsolidationController._automatic_runtime_execution(
            content="Task Type: deployment\n\n## Objective\n\nDeploy.\n",
            context={"objective": "Deploy.", "deliverables": ["deploy/service.sh"]},
        )
        self.assertIsNone(execution)

    def test_auto_route_adds_platform_denied_paths(self) -> None:
        execution = RuntimeConsolidationController._automatic_runtime_execution(
            content="Task Type: maintenance\n\n## Objective\n\nMaintain app.\n",
            context={
                "objective": "Maintain app.",
                "deliverables": ["wordpress/martfury-child/functions.php"],
                "denied_paths": ["secrets"],
            },
        )
        self.assertIsNotNone(execution)
        assert execution is not None
        denied = tuple(execution["denied_paths"])
        for path in AUTO_ROUTE_DENIED_PATHS:
            self.assertIn(path, denied)
        self.assertIn("secrets", denied)

    def test_execution_request_merges_runtime_and_context_denied_paths(self) -> None:
        controller = object.__new__(RuntimeConsolidationController)
        controller.repository_root = Path("/tmp/example")
        controller.timeout_seconds = 1800

        request = controller._execution_request(
            "example",
            "## Objective\n\nFix it.\n",
            {
                "deliverables": ["src/example.py"],
                "denied_paths": ["context-denied"],
            },
            {
                "denied_paths": ["runtime-denied"],
                "metadata": {"automatic_runtime_routing": True},
            },
        )

        self.assertEqual(
            ("runtime-denied", "context-denied"),
            request.denied_paths,
        )
        self.assertTrue(request.metadata["automatic_runtime_routing"])

    def test_success_normalization_preserves_branch_evidence(self) -> None:
        result = ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider="openhands",
            evidence=ExecutionEvidence(
                changed_files=("agent/example.py",),
                branch="agent/runtime-example",
                commit_sha="abc123",
            ),
        )
        payload = RuntimeConsolidationController._normalize_result(result)
        self.assertEqual("success", payload["status"])
        self.assertEqual("agent/runtime-example", payload["branch"])
        self.assertEqual("abc123", payload["git_commit"])

    def test_retryable_runtime_failure_maps_to_worker_retry(self) -> None:
        result = ExecutionResult(
            status=RuntimeStatus.failed,
            provider="openhands",
            retryable=True,
            reason="temporary",
        )
        payload = RuntimeConsolidationController._normalize_result(result)
        self.assertEqual("retry", payload["status"])


if __name__ == "__main__":
    unittest.main()
