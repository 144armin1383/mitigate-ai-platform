from __future__ import annotations

import unittest

from agent.resilience.replacement_mission_bridge import (
    NativeReplacementMissionBridge,
)
from agent.technology.assimilation_mission_bridge import (
    NativeAssimilationMissionBridge,
    NativeAssimilationRequest,
)
from agent.technology.registry import (
    AssimilationState,
    EvaluationState,
    TechnologyKind,
    TechnologyRecord,
    TechnologyRegistry,
    TechnologyState,
)


class QueueCoordinator:
    def __init__(self):
        self.calls = []

    def enqueue(
        self,
        project_id,
        queue_reference,
        missions,
    ):
        call = {
            "project_id": project_id,
            "queue_reference": queue_reference,
            "missions": missions,
        }

        self.calls.append(call)

        return {
            "status": "queued",
            **call,
        }


class NativeAssimilationMissionBridgeTests(
    unittest.TestCase
):
    def setUp(self):
        self.registry = TechnologyRegistry()

        self.registry.register(
            TechnologyRecord(
                technology_id="ruflo",
                name="Ruflo",
                kind=TechnologyKind.ORCHESTRATOR,
                state=TechnologyState.EVALUATING,
                evaluation_state=EvaluationState.PASSED,
                assimilation_state=(
                    AssimilationState.CANDIDATE
                ),
                capabilities=[
                    "agent_orchestration",
                    "workflow_coordination",
                ],
            )
        )

        self.queue = QueueCoordinator()

        replacement_bridge = (
            NativeReplacementMissionBridge(
                queue_coordinator=self.queue,
                queue_reference="missions",
            )
        )

        self.bridge = (
            NativeAssimilationMissionBridge(
                registry=self.registry,
                replacement_bridge=replacement_bridge,
            )
        )

    def _request(
        self,
        **changes,
    ):
        values = {
            "project_id":
                "mitigate-ai-platform",
            "technology_id":
                "ruflo",
            "outcome":
                "assimilate_candidate",
            "capabilities": [
                "agent_orchestration",
            ],
            "reason":
                "Useful orchestration capability",
        }

        values.update(changes)

        return NativeAssimilationRequest(
            **values
        )

    def test_only_explicit_assimilation_outcome_allowed(
        self,
    ):
        with self.assertRaises(ValueError):
            self.bridge.create_missions(
                self._request(
                    outcome="watch"
                )
            )

    def test_evaluation_must_have_passed(
        self,
    ):
        self.registry.update(
            "ruflo",
            evaluation_state=(
                EvaluationState.FAILED
            ),
        )

        with self.assertRaises(ValueError):
            self.bridge.create_missions(
                self._request()
            )

    def test_unknown_capability_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            self.bridge.create_missions(
                self._request(
                    capabilities=[
                        "unknown_capability"
                    ]
                )
            )

    def test_external_runtime_dependency_rejected(
        self,
    ):
        self.registry.update(
            "ruflo",
            external_runtime_required=True,
        )

        with self.assertRaises(ValueError):
            self.bridge.create_missions(
                self._request()
            )

    def test_created_mission_is_native_only(
        self,
    ):
        missions = self.bridge.create_missions(
            self._request()
        )

        self.assertEqual(
            1,
            len(missions),
        )

        mission = missions[0]

        self.assertEqual(
            "native",
            mission["provider_id"],
        )

        resilience = mission[
            "payload"
        ]["resilience"]

        self.assertTrue(
            resilience["native_only"]
        )

        self.assertFalse(
            resilience[
                "external_runtime_dependency_allowed"
            ]
        )

        self.assertEqual(
            "ruflo",
            resilience[
                "source_context"
            ]["technology"],
        )

    def test_plan_updates_registry(
        self,
    ):
        missions = self.bridge.plan(
            self._request()
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            AssimilationState.PLANNED,
            record.assimilation_state,
        )

        self.assertEqual(
            TechnologyState.ASSIMILATING,
            record.state,
        )

        self.assertFalse(
            record.external_runtime_required
        )

        assimilation = record.metadata[
            "assimilation"
        ]

        self.assertEqual(
            [missions[0]["mission_id"]],
            assimilation["mission_ids"],
        )

        self.assertTrue(
            assimilation["native_only"]
        )

    def test_enqueue_uses_existing_replacement_bridge(
        self,
    ):
        results = self.bridge.enqueue(
            self._request()
        )

        self.assertEqual(
            1,
            len(results),
        )

        self.assertEqual(
            1,
            len(self.queue.calls),
        )

        mission = self.queue.calls[
            0
        ]["missions"][0]

        self.assertEqual(
            "native_capability_replacement",
            mission["task_type"],
        )

        self.assertEqual(
            AssimilationState.IN_PROGRESS,
            self.registry.get(
                "ruflo"
            ).assimilation_state,
        )

    def test_capability_order_is_deterministic(
        self,
    ):
        missions = self.bridge.create_missions(
            self._request(
                capabilities=[
                    "workflow_coordination",
                    "agent_orchestration",
                    "workflow_coordination",
                ]
            )
        )

        self.assertEqual(
            [
                "agent_orchestration",
                "workflow_coordination",
            ],
            [
                mission["step_id"]
                for mission in missions
            ],
        )

    def test_mark_native_available(
        self,
    ):
        self.bridge.mark_native_available(
            "ruflo",
            "agent_orchestration",
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            [
                "agent_orchestration"
            ],
            record.adopted_capabilities,
        )

        self.assertTrue(
            record.native_replacement_available
        )

        self.assertEqual(
            AssimilationState.NATIVE_AVAILABLE,
            record.assimilation_state,
        )

        self.assertFalse(
            record.external_runtime_required
        )

    def test_complete_requires_all_capabilities(
        self,
    ):
        self.bridge.mark_native_available(
            "ruflo",
            "agent_orchestration",
        )

        with self.assertRaises(ValueError):
            self.bridge.complete(
                "ruflo"
            )

    def test_complete_marks_native_replaced(
        self,
    ):
        self.bridge.mark_native_available(
            "ruflo",
            "agent_orchestration",
        )

        self.bridge.mark_native_available(
            "ruflo",
            "workflow_coordination",
        )

        self.bridge.complete(
            "ruflo"
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            AssimilationState.COMPLETE,
            record.assimilation_state,
        )

        self.assertEqual(
            TechnologyState.NATIVE_REPLACED,
            record.state,
        )

        self.assertTrue(
            record.native_replacement_available
        )

        self.assertFalse(
            record.external_runtime_required
        )


if __name__ == "__main__":
    unittest.main()
