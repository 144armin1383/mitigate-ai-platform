from __future__ import annotations

import unittest

from agent.runtime.production_queue_coordinator_adapter import (
    ProductionQueueCoordinatorAdapter,
)


class FakeQueue:
    def __init__(self):
        self.items = []

    def enqueue(
        self,
        mission_id,
        priority,
        dependencies=None,
        *,
        max_retries=None,
    ):
        self.items.append(
            {
                "mission_id": mission_id,
                "priority": priority,
                "dependencies": dependencies,
                "max_retries": max_retries,
            }
        )


class ProductionQueueCoordinatorAdapterTests(
    unittest.TestCase
):
    def test_enqueue_uses_existing_queue(
        self,
    ):
        queue = FakeQueue()

        adapter = (
            ProductionQueueCoordinatorAdapter(
                queue=queue,
                project_id="mitigate-ai-platform",
                queue_reference="missions",
            )
        )

        result = adapter.enqueue(
            "mitigate-ai-platform",
            "missions",
            [
                {
                    "mission_id":
                        "native-replacement-1",
                    "task_type":
                        "native_capability_replacement",
                }
            ],
        )

        self.assertEqual(
            1,
            len(queue.items),
        )

        self.assertEqual(
            [
                "native-replacement-1"
            ],
            result["mission_ids"],
        )

    def test_project_mismatch_rejected(
        self,
    ):
        adapter = (
            ProductionQueueCoordinatorAdapter(
                queue=FakeQueue(),
                project_id="mitigate-ai-platform",
                queue_reference="missions",
            )
        )

        with self.assertRaises(
            ValueError
        ):
            adapter.enqueue(
                "other",
                "missions",
                [
                    {
                        "mission_id": "m1"
                    }
                ],
            )

    def test_queue_mismatch_rejected(
        self,
    ):
        adapter = (
            ProductionQueueCoordinatorAdapter(
                queue=FakeQueue(),
                project_id="mitigate-ai-platform",
                queue_reference="missions",
            )
        )

        with self.assertRaises(
            ValueError
        ):
            adapter.enqueue(
                "mitigate-ai-platform",
                "other",
                [
                    {
                        "mission_id": "m1"
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()


class RealMissionQueueContractTests(
    unittest.TestCase
):
    def test_adapter_matches_real_mission_queue_signature(
        self,
    ):
        import inspect

        from agent.runtime.mission_queue import (
            MissionQueue,
        )

        signature = inspect.signature(
            MissionQueue.enqueue
        )

        parameters = list(
            signature.parameters
        )

        self.assertEqual(
            [
                "self",
                "mission_id",
                "priority",
                "dependencies",
                "max_retries",
            ],
            parameters,
        )
