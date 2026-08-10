import tempfile
import unittest
from pathlib import Path

from agent.runtime.production_runtime_api import (
    ProductionRuntimeFacade,
    build_production_runtime,
)


class FakeRequestFlow:
    def __init__(self):
        self.requests = []

    def submit(self, request):
        self.requests.append(
            dict(request)
        )

        return {
            "accepted": True,
            "request_id": (
                request["request_id"]
            ),
        }

    def latest_events(self, limit):
        return []


class ProductionRuntimeAPITests(
    unittest.TestCase
):

    def test_facade_requires_start(
        self,
    ):
        flow = FakeRequestFlow()

        runtime = (
            ProductionRuntimeFacade(
                flow
            )
        )

        result = runtime.submit_request(
            {
                "request_id": "req-1",
            }
        )

        self.assertFalse(
            result["accepted"]
        )

        self.assertEqual(
            result["blocked_reason"],
            "runtime_not_running",
        )

    def test_facade_forwards_request(
        self,
    ):
        flow = FakeRequestFlow()

        runtime = (
            ProductionRuntimeFacade(
                flow
            )
        )

        runtime.start()

        result = runtime.submit_request(
            {
                "request_id": "req-1",
            }
        )

        self.assertTrue(
            result["accepted"]
        )

        self.assertEqual(
            flow.requests,
            [
                {
                    "request_id": (
                        "req-1"
                    ),
                }
            ],
        )

    def test_runtime_builds_production_composition(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            runtime = build_production_runtime(
                project_id="mitigate",
                queue_path=(
                    root
                    / "data"
                    / "missions.json"
                ),
                repository_root=root,
            )

            runtime.start()

            status = runtime.runtime_status()

            self.assertEqual(
                status["state"],
                "running",
            )

            self.assertTrue(
                status[
                    "application_ready"
                ]
            )

    def test_real_production_request_reaches_queue(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue_path = (
                root
                / "data"
                / "missions.json"
            )

            runtime = build_production_runtime(
                project_id="mitigate",
                queue_path=queue_path,
                repository_root=root,
            )

            runtime.start()

            result = runtime.submit_request(
                {
                    "request_id": (
                        "req-production-e2e-1"
                    ),
                    "project_id": "mitigate",
                    "conversation_id": (
                        "conv-production-e2e-1"
                    ),
                    "user_message": (
                        "Create a production "
                        "request contract "
                        "smoke mission."
                    ),
                    "upload_ids": [],
                    "requested_task_type": (
                        "testing"
                    ),
                    "created_at": (
                        "2026-08-10T12:00:00+00:00"
                    ),
                }
            )

            self.assertTrue(
                result["accepted"],
                result,
            )

            self.assertEqual(
                result["project_id"],
                "mitigate",
            )

            self.assertEqual(
                len(result["mission_ids"]),
                1,
            )

            mission_id = (
                result["mission_ids"][0]
            )

            self.assertTrue(
                queue_path.exists()
            )

            definition_path = (
                root
                / "agent"
                / "missions"
                / f"{mission_id}.md"
            )

            self.assertTrue(
                definition_path.exists()
            )

    def test_status_alias_matches_runtime_status(self):
        flow = FakeRequestFlow()

        runtime = ProductionRuntimeFacade(flow)
        runtime.start()

        self.assertEqual(
            runtime.status(),
            runtime.runtime_status(),
        )

        self.assertEqual(
            runtime.status()["state"],
            "running",
        )

        self.assertTrue(
            runtime.status()["application_ready"]
        )

    def test_runtime_status_stops_cleanly(
        self,
    ):
        flow = FakeRequestFlow()

        runtime = (
            ProductionRuntimeFacade(
                flow
            )
        )

        runtime.start()
        runtime.stop()

        status = runtime.runtime_status()

        self.assertEqual(
            status["state"],
            "stopped",
        )


if __name__ == "__main__":
    unittest.main()
