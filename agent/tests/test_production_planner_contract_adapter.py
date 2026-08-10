import unittest

from agent.orchestrator.plan_validator_mission_builder import (
    PlanValidatorMissionBuilder,
)
from agent.runtime.production_planner_contract_adapter import (
    ProductionPlannerContractAdapter,
)


class ProductionPlannerContractAdapterTests(
    unittest.TestCase
):

    def setUp(self):
        self.adapter = (
            ProductionPlannerContractAdapter()
        )

        self.input = {
            "request_id": "req-100",
            "project_id": "mitigate",
            "conversation_id": "conv-100",
            "repository_root": (
                "/srv/mitigate/"
                "mitigate-ai-platform"
            ),
            "default_branch": "main",
            "project_type": "wordpress",
            "policy_profile": "default",
            "provider_id": "provider",
            "model_id": "model",
            "task_type": "wordpress",
            "user_message": (
                "Create a harmless "
                "production request smoke file"
            ),
            "upload_ids": [],
        }

    def test_returns_strict_plan_shape(self):
        plan = self.adapter.plan(
            self.input
        )

        self.assertEqual(
            set(plan),
            {
                "plan_id",
                "request_id",
                "project_id",
                "summary",
                "steps",
            },
        )

        self.assertEqual(
            plan["request_id"],
            "req-100",
        )

        self.assertEqual(
            plan["project_id"],
            "mitigate",
        )

        self.assertEqual(
            len(plan["steps"]),
            1,
        )

    def test_output_is_builder_compatible(self):
        plan = self.adapter.plan(
            self.input
        )

        approved = {
            "request_id": "req-100",
            "project_id": "mitigate",
            "conversation_id": "conv-100",
            "provider_id": "provider",
            "model_id": "model",
            "task_type": "wordpress",
            "created_at": (
                "2026-08-10T00:00:00Z"
            ),
        }

        builder = (
            PlanValidatorMissionBuilder()
        )

        validated = (
            builder.validate_plan(
                plan,
                approved,
            )
        )

        self.assertEqual(
            validated["plan_id"],
            plan["plan_id"],
        )

    def test_plan_is_deterministic(self):
        first = self.adapter.plan(
            self.input
        )

        second = self.adapter.plan(
            self.input
        )

        self.assertEqual(
            first,
            second,
        )

    def test_unknown_task_type_falls_back_general(
        self,
    ):
        data = dict(self.input)
        data["task_type"] = (
            "some-new-task"
        )

        plan = self.adapter.plan(
            data
        )

        self.assertEqual(
            plan["steps"][0]["task_type"],
            "general",
        )

    def test_invalid_request_id_rejected(self):
        data = dict(self.input)
        data["request_id"] = "../bad"

        with self.assertRaises(
            ValueError
        ):
            self.adapter.plan(data)

    def test_upload_ids_must_be_list(self):
        data = dict(self.input)
        data["upload_ids"] = "bad"

        with self.assertRaisesRegex(
            ValueError,
            "invalid_upload_ids",
        ):
            self.adapter.plan(data)


if __name__ == "__main__":
    unittest.main()

class ProductionPlannerDeliverablesContractTests(unittest.TestCase):
    def test_extracts_explicit_repository_file(self) -> None:
        message = (
            "Create a small documentation file at "
            "docs/runtime/FIRST_PRODUCTION_E2E.md and validate it."
        )

        self.assertEqual(
            ProductionPlannerContractAdapter._extract_deliverables(
                message
            ),
            [
                "docs/runtime/FIRST_PRODUCTION_E2E.md",
            ],
        )

    def test_deduplicates_explicit_repository_file(self) -> None:
        message = (
            "Create docs/runtime/FIRST_PRODUCTION_E2E.md and then "
            "validate docs/runtime/FIRST_PRODUCTION_E2E.md."
        )

        self.assertEqual(
            ProductionPlannerContractAdapter._extract_deliverables(
                message
            ),
            [
                "docs/runtime/FIRST_PRODUCTION_E2E.md",
            ],
        )

    def test_ignores_absolute_path(self) -> None:
        message = (
            "Inspect /srv/mitigate/private.txt before continuing."
        )

        self.assertEqual(
            ProductionPlannerContractAdapter._extract_deliverables(
                message
            ),
            [],
        )
