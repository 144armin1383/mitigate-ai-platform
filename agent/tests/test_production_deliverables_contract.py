from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]

if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import ai.mission_runner as mr

from agent.runtime.production_planner_contract_adapter import (
    ProductionPlannerContractAdapter,
)
from agent.runtime.production_request_queue_adapter import (
    ProductionRequestQueueAdapter,
)


class ProductionDeliverablesContractTests(unittest.TestCase):

    def planner_input(self) -> dict:
        return {
            "request_id": "req-e2e-deliverables",
            "project_id": "mitigate",
            "conversation_id": "conv-e2e-deliverables",
            "repository_root": (
                "/srv/mitigate/mitigate-ai-platform"
            ),
            "default_branch": "main",
            "project_type": "wordpress",
            "policy_profile": "default",
            "provider_id": "production",
            "model_id": "production",
            "task_type": "documentation",
            "user_message": (
                "Create a small documentation file at "
                "docs/runtime/FIRST_PRODUCTION_E2E.md "
                "and keep the change limited to that file."
            ),
            "upload_ids": [],
        }

    def test_planner_extracts_repository_deliverable(self) -> None:
        planner = ProductionPlannerContractAdapter()

        plan = planner.plan(
            self.planner_input()
        )

        payload = plan["steps"][0]["payload"]

        self.assertEqual(
            payload["deliverables"],
            [
                "docs/runtime/FIRST_PRODUCTION_E2E.md",
            ],
        )

    def test_queue_renders_deliverables_section(self) -> None:
        planner = ProductionPlannerContractAdapter()

        plan = planner.plan(
            self.planner_input()
        )

        step = plan["steps"][0]

        mission = {
            "mission_id": "mission-deliverables",
            "project_id": "mitigate",
            "request_id": "req-e2e-deliverables",
            "conversation_id": "conv-e2e-deliverables",
            "plan_id": plan["plan_id"],
            "step_id": step["step_id"],
            "title": step["title"],
            "description": step["description"],
            "task_type": step["task_type"],
            "provider_id": "production",
            "model_id": "production",
            "dependencies": [],
            "priority": step["priority"],
            "payload": step["payload"],
            "status": "pending",
            "created_at": "2026-08-10T00:00:00Z",
        }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            adapter = ProductionRequestQueueAdapter(
                project_id="mitigate",
                queue_path=root / "data" / "missions.json",
                repository_root=root,
            )

            adapter.enqueue_batch(
                [mission]
            )

            definition = (
                root
                / "agent"
                / "missions"
                / "mission-deliverables.md"
            )

            text = definition.read_text(
                encoding="utf-8"
            )

            self.assertIn(
                "## Deliverables",
                text,
            )

            self.assertIn(
                "- docs/runtime/FIRST_PRODUCTION_E2E.md",
                text,
            )

            self.assertIn(
                "- docs/runtime/FIRST_PRODUCTION_E2E.md\n",
                text,
            )

            self.assertNotIn(
                "FIRST_PRODUCTION_E2E.md\\\\n",
                text,
            )

    def test_runner_extracts_docs_deliverable(self) -> None:
        mission = """
# Production smoke

## Deliverables

- docs/runtime/FIRST_PRODUCTION_E2E.md

## Context

{}
"""

        self.assertEqual(
            mr.extract_deliverables(
                mission
            ),
            {
                "docs/runtime/FIRST_PRODUCTION_E2E.md",
            },
        )

    def test_runner_extracts_wordpress_deliverable(self) -> None:
        mission = """
# WordPress change

## Deliverables

- wordpress/martfury-child/functions.php

## Context

{}
"""

        self.assertEqual(
            mr.extract_deliverables(
                mission
            ),
            {
                "wordpress/martfury-child/functions.php",
            },
        )

    def test_runner_rejects_git_internal_path(self) -> None:
        mission = """
# Unsafe

## Deliverables

- .git/config

## Context

{}
"""

        with self.assertRaisesRegex(
            mr.MissionError,
            "Unsafe deliverable path",
        ):
            mr.extract_deliverables(
                mission
            )


if __name__ == "__main__":
    unittest.main()
