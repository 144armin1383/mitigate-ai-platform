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
