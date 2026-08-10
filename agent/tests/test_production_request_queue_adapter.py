import tempfile
import unittest
from pathlib import Path

from agent.runtime.mission_queue import MissionQueue
from agent.runtime.production_request_queue_adapter import (
    ProductionRequestQueueAdapter,
)


class ProductionRequestQueueAdapterTests(unittest.TestCase):

    def build_adapter(self, root: Path):
        return ProductionRequestQueueAdapter(
            project_id="mitigate",
            queue_path=root / "data" / "missions.json",
            repository_root=root,
        )

    def mission(
        self,
        mission_id="request_smoke",
        dependencies=None,
        project_id="mitigate",
    ):
        return {
            "mission_id": mission_id,
            "project_id": project_id,
            "request_id": "req-1",
            "conversation_id": "conv-1",
            "plan_id": "plan-1",
            "step_id": "step-1",
            "title": "Request smoke",
            "description": "Create a harmless request-ingress smoke artifact.",
            "task_type": "general",
            "provider_id": "provider",
            "model_id": "model",
            "dependencies": dependencies or [],
            "priority": 10,
            "payload": {
                "requested_change": "safe smoke test",
            },
            "status": "pending",
            "created_at": "2026-08-10T00:00:00Z",
        }

    def test_materializes_definition_before_enqueue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self.build_adapter(root)

            result = adapter.enqueue_batch(
                [self.mission()]
            )

            self.assertEqual(result, ["request_smoke"])

            definition = (
                root
                / "agent"
                / "missions"
                / "request_smoke.md"
            )

            self.assertTrue(definition.exists())

            queue = MissionQueue(
                str(root / "data" / "missions.json")
            )

            listed = queue.list()

            self.assertEqual(
                [item["id"] for item in listed],
                ["request_smoke"],
            )

    def test_rejects_cross_project_mission(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self.build_adapter(root)

            with self.assertRaisesRegex(
                ValueError,
                "cross_project_reference",
            ):
                adapter.enqueue_batch(
                    [
                        self.mission(
                            project_id="other-project",
                        )
                    ]
                )

    def test_rejects_forbidden_command_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self.build_adapter(root)

            mission = self.mission()
            mission["payload"] = {
                "command": "rm -rf /",
            }

            with self.assertRaisesRegex(
                ValueError,
                "forbidden_payload_key",
            ):
                adapter.enqueue_batch([mission])

    def test_dependency_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self.build_adapter(root)

            first = self.mission(
                mission_id="first",
            )
            second = self.mission(
                mission_id="second",
                dependencies=["first"],
            )

            adapter.enqueue_batch(
                [first, second]
            )

            queue = MissionQueue(
                str(root / "data" / "missions.json")
            )

            listed = {
                item["id"]: item
                for item in queue.list()
            }

            self.assertEqual(
                listed["second"]["dependencies"],
                ["first"],
            )

    def test_existing_definition_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self.build_adapter(root)

            definition = (
                root
                / "agent"
                / "missions"
                / "request_smoke.md"
            )
            definition.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            definition.write_text(
                "existing",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "mission_definition_exists",
            ):
                adapter.enqueue_batch(
                    [self.mission()]
                )

            self.assertEqual(
                definition.read_text(
                    encoding="utf-8",
                ),
                "existing",
            )


if __name__ == "__main__":
    unittest.main()
