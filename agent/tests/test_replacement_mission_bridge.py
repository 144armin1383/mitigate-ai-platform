from __future__ import annotations

import unittest

from agent.resilience.replacement_mission_bridge import (
    NativeReplacementMissionBridge,
    NativeReplacementRequest,
)


class FakeCoordinator:
    def __init__(self) -> None:
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
                m["mission_id"]
                for m in missions
            ],
        }


class NativeReplacementMissionBridgeTests(
    unittest.TestCase
):

    def _bridge(self):
        coordinator = FakeCoordinator()

        bridge = NativeReplacementMissionBridge(
            queue_coordinator=coordinator,
            queue_reference="production",
        )

        return bridge, coordinator

    def _request(self):
        return NativeReplacementRequest(
            capability="multi_agent_consensus",
            project_id="mitigate-ai-platform",
            reason="native capability gap detected",
            source_provider="external",
            source_technology="ruflo",
        )

    def test_replacement_is_native_only(self):
        bridge, _ = self._bridge()

        mission = bridge.create_mission(
            self._request()
        )

        self.assertEqual(
            mission["provider_id"],
            "native",
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

    def test_external_technology_is_reference_only(self):
        bridge, _ = self._bridge()

        mission = bridge.create_mission(
            self._request()
        )

        context = mission[
            "payload"
        ]["resilience"]["source_context"]

        self.assertEqual(
            context["technology"],
            "ruflo",
        )

        self.assertEqual(
            mission["provider_id"],
            "native",
        )

    def test_mission_uses_existing_pipeline_contract(self):
        bridge, _ = self._bridge()

        mission = bridge.create_mission(
            self._request()
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
            mission["status"],
            "pending",
        )

    def test_enqueue_uses_existing_coordinator(self):
        bridge, coordinator = self._bridge()

        result = bridge.enqueue(
            self._request()
        )

        self.assertTrue(
            result["accepted"]
        )

        self.assertEqual(
            len(coordinator.calls),
            1,
        )

        project_id, queue_reference, missions = (
            coordinator.calls[0]
        )

        self.assertEqual(
            project_id,
            "mitigate-ai-platform",
        )

        self.assertEqual(
            queue_reference,
            "production",
        )

        self.assertEqual(
            len(missions),
            1,
        )

    def test_mission_id_is_deterministic(self):
        bridge, _ = self._bridge()

        first = bridge.create_mission(
            self._request()
        )

        second = bridge.create_mission(
            self._request()
        )

        self.assertEqual(
            first["mission_id"],
            second["mission_id"],
        )

    def test_different_capability_changes_id(self):
        bridge, _ = self._bridge()

        first = bridge.create_mission(
            self._request()
        )

        second = bridge.create_mission(
            NativeReplacementRequest(
                capability="technology_discovery",
                project_id="mitigate-ai-platform",
                reason="native capability gap detected",
                source_provider="external",
                source_technology="ruflo",
            )
        )

        self.assertNotEqual(
            first["mission_id"],
            second["mission_id"],
        )

    def test_validation_rejects_empty_capability(self):
        bridge, _ = self._bridge()

        with self.assertRaises(ValueError):
            bridge.create_mission(
                NativeReplacementRequest(
                    capability="",
                    project_id="mitigate-ai-platform",
                    reason="gap",
                )
            )

    def test_requirements_preserve_core(self):
        bridge, _ = self._bridge()

        mission = bridge.create_mission(
            self._request()
        )

        requirements = mission[
            "payload"
        ]["implementation_requirements"]

        self.assertTrue(
            requirements["preserve_existing_core"]
        )

        self.assertTrue(
            requirements[
                "require_provider_independence"
            ]
        )

        self.assertTrue(
            requirements[
                "require_regression_tests"
            ]
        )


if __name__ == "__main__":
    unittest.main()
