from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import ExecutionEvidence, ExecutionResult, RuntimeStatus
from agent.runtime.runtime_consolidation_controller import RuntimeConsolidationController


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
