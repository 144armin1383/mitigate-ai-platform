from __future__ import annotations

import unittest
from datetime import datetime, timezone

from agent.technology.evaluation_mission_bridge import (
    TechnologyEvaluationMissionBridge,
    TechnologyEvaluationRequest,
)
from agent.technology.scoring import TechnologyScore
from agent.technology.watcher import TechnologyEvaluationCandidate


class FixedClock:
    def now(self):
        return datetime(
            2026,
            8,
            11,
            19,
            30,
            tzinfo=timezone.utc,
        )


class FakeCoordinator:
    def __init__(self):
        self.calls = []

    def enqueue(
        self,
        project_id,
        queue_reference,
        missions,
    ):
        self.calls.append(
            (
                project_id,
                queue_reference,
                missions,
            )
        )

        return {
            "accepted": True,
            "project_id": project_id,
            "mission_ids": [
                mission["mission_id"]
                for mission in missions
            ],
        }


class TechnologyEvaluationMissionBridgeTests(
    unittest.TestCase
):
    def _score(
        self,
        *,
        evaluation_candidate=True,
        total=90,
    ):
        return TechnologyScore(
            relevance=90,
            capability_novelty=80,
            architectural_compatibility=90,
            independence_potential=95,
            operational_value=85,
            security_risk_penalty=5,
            external_dependency_penalty=0,
            total=total,
            evaluation_candidate=evaluation_candidate,
        )

    def _candidate(
        self,
        *,
        version="1.2.3",
        evaluation_candidate=True,
        total=90,
    ):
        return TechnologyEvaluationCandidate(
            technology_id="ruflo",
            score=self._score(
                evaluation_candidate=evaluation_candidate,
                total=total,
            ),
            observed_version=version,
        )

    def _bridge(self):
        return TechnologyEvaluationMissionBridge(
            queue_coordinator=FakeCoordinator(),
            queue_reference="production",
            clock=FixedClock(),
        )

    def test_mission_uses_existing_pipeline_contract(self):
        mission = self._bridge().create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        required = {
            "mission_id",
            "project_id",
            "request_id",
            "conversation_id",
            "plan_id",
            "step_id",
            "title",
            "description",
            "task_type",
            "provider_id",
            "model_id",
            "dependencies",
            "priority",
            "payload",
            "status",
            "created_at",
        }

        self.assertEqual(
            set(mission),
            required,
        )

        self.assertEqual(
            mission["task_type"],
            "technology_evaluation",
        )

        self.assertEqual(
            mission["status"],
            "pending",
        )

    def test_external_runtime_is_prohibited(self):
        mission = self._bridge().create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        evaluation = mission[
            "payload"
        ]["technology_evaluation"]

        self.assertFalse(
            evaluation[
                "external_runtime_dependency_allowed"
            ]
        )

        self.assertFalse(
            evaluation[
                "installation_allowed"
            ]
        )

        self.assertFalse(
            evaluation[
                "activation_allowed"
            ]
        )

        self.assertFalse(
            evaluation[
                "runtime_adoption_allowed"
            ]
        )

    def test_allowed_recommendations_are_bounded(self):
        mission = self._bridge().create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        self.assertEqual(
            mission["payload"][
                "allowed_recommendations"
            ],
            [
                "reject",
                "watch",
                "sandbox",
                "assimilate_candidate",
            ],
        )

    def test_mission_id_is_deterministic(self):
        bridge = self._bridge()

        request = TechnologyEvaluationRequest(
            project_id="mitigate-ai-platform",
            candidate=self._candidate(),
        )

        first = bridge.create_mission(
            request
        )

        second = bridge.create_mission(
            request
        )

        self.assertEqual(
            first["mission_id"],
            second["mission_id"],
        )

    def test_version_changes_mission_id(self):
        bridge = self._bridge()

        first = bridge.create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(
                    version="1.2.3"
                ),
            )
        )

        second = bridge.create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(
                    version="1.2.4"
                ),
            )
        )

        self.assertNotEqual(
            first["mission_id"],
            second["mission_id"],
        )

    def test_score_changes_mission_id(self):
        bridge = self._bridge()

        first = bridge.create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(
                    total=90
                ),
            )
        )

        second = bridge.create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(
                    total=91
                ),
            )
        )

        self.assertNotEqual(
            first["mission_id"],
            second["mission_id"],
        )

    def test_enqueue_uses_existing_coordinator(self):
        coordinator = FakeCoordinator()

        bridge = TechnologyEvaluationMissionBridge(
            queue_coordinator=coordinator,
            queue_reference="production",
            clock=FixedClock(),
        )

        result = bridge.enqueue(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        self.assertTrue(
            result["accepted"]
        )

        self.assertEqual(
            len(coordinator.calls),
            1,
        )

        project_id, queue_ref, missions = (
            coordinator.calls[0]
        )

        self.assertEqual(
            project_id,
            "mitigate-ai-platform",
        )

        self.assertEqual(
            queue_ref,
            "production",
        )

        self.assertEqual(
            len(missions),
            1,
        )

    def test_non_candidate_is_rejected(self):
        candidate = self._candidate(
            evaluation_candidate=False,
            total=10,
        )

        with self.assertRaises(
            ValueError
        ):
            self._bridge().create_mission(
                TechnologyEvaluationRequest(
                    project_id="mitigate-ai-platform",
                    candidate=candidate,
                )
            )

    def test_provider_is_native(self):
        mission = self._bridge().create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        self.assertEqual(
            mission["provider_id"],
            "native",
        )

    def test_no_executable_payload_fields(self):
        mission = self._bridge().create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        forbidden = {
            "shell",
            "command",
            "cmd",
            "bash",
            "powershell",
            "subprocess",
            "executable",
            "script",
        }

        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(
                        key.lower(),
                        forbidden,
                    )
                    walk(item)

            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(
            mission["payload"]
        )

    def test_invalid_project_id_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            self._bridge().create_mission(
                TechnologyEvaluationRequest(
                    project_id="",
                    candidate=self._candidate(),
                )
            )

    def test_empty_reason_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            self._bridge().create_mission(
                TechnologyEvaluationRequest(
                    project_id="mitigate-ai-platform",
                    candidate=self._candidate(),
                    reason="",
                )
            )

    def test_evaluation_does_not_authorize_adoption(self):
        mission = self._bridge().create_mission(
            TechnologyEvaluationRequest(
                project_id="mitigate-ai-platform",
                candidate=self._candidate(),
            )
        )

        payload = mission["payload"]

        self.assertIn(
            "assimilate_candidate",
            payload["allowed_recommendations"],
        )

        self.assertIn(
            "create_runtime_dependency",
            payload["prohibited_actions"],
        )

        self.assertTrue(
            payload[
                "evaluation_requirements"
            ][
                "require_human_review_before_adoption"
            ]
        )


if __name__ == "__main__":
    unittest.main()
