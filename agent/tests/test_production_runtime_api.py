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


class FakeStatusQueue:
    def __init__(self):
        self.items = {
            "m-status-1": {
                "id": "m-status-1",
                "priority": 8,
                "dependencies": [],
                "state": "completed",
                "created_seq": 1,
                "attempts_done": 0,
                "max_retries": 0,
            }
        }

    def get(self, mission_id):
        if mission_id not in self.items:
            raise KeyError(mission_id)

        return dict(
            self.items[mission_id]
        )

    def list(self):
        return [
            dict(item)
            for item in self.items.values()
        ]


class FakeStatusReporter:
    def __init__(self):
        self.report = {
            "execution_id": "exec-status-1",
            "project_id": "mitigate",
            "request_id": "req-status-1",
            "mission_id": "m-status-1",
            "status": "completed",
            "success": True,
            "task_type": "documentation",
            "changed_files": [
                "docs/runtime/STATUS_API.md"
            ],
            "git_branch": (
                "agent/mission-m-status-1"
            ),
            "git_commit": "a" * 40,
            "validation_status": "validated",
            "metadata": {
                "risk_level": "low",
                "merge_recommendation": "approve",
                "merged_to_main": True,
            },
        }

    def get_report(self, execution_id):
        if execution_id != "exec-status-1":
            raise RuntimeError(
                "Report not found for execution_id"
            )

        return dict(self.report)

    def find_by_request_id(self, request_id):
        if request_id != "req-status-1":
            return []

        return [
            dict(self.report)
        ]


class ProductionRuntimeStatusContractTests(
    unittest.TestCase
):

    def build_runtime(self):
        return ProductionRuntimeFacade(
            FakeRequestFlow(),
            queue=FakeStatusQueue(),
            execution_reporter=FakeStatusReporter(),
        )

    def test_get_mission_returns_persisted_state(self):
        runtime = self.build_runtime()

        result = runtime.get_mission(
            "m-status-1"
        )

        self.assertEqual(
            result["id"],
            "m-status-1",
        )

        self.assertEqual(
            result["state"],
            "completed",
        )

    def test_get_mission_not_found(self):
        runtime = self.build_runtime()

        with self.assertRaisesRegex(
            KeyError,
            "mission_not_found",
        ):
            runtime.get_mission(
                "missing-mission"
            )

    def test_get_execution_returns_report(self):
        runtime = self.build_runtime()

        result = runtime.get_execution(
            "exec-status-1"
        )

        self.assertEqual(
            result["execution_id"],
            "exec-status-1",
        )

        self.assertEqual(
            result["request_id"],
            "req-status-1",
        )

    def test_get_execution_not_found(self):
        runtime = self.build_runtime()

        with self.assertRaisesRegex(
            KeyError,
            "execution_not_found",
        ):
            runtime.get_execution(
                "missing-execution"
            )

    def test_request_status_aggregates_mission_and_execution(
        self,
    ):
        runtime = self.build_runtime()

        result = runtime.get_request_status(
            "req-status-1"
        )

        self.assertEqual(
            result["request_id"],
            "req-status-1",
        )

        self.assertEqual(
            result["status"],
            "completed",
        )

        self.assertEqual(
            len(result["missions"]),
            1,
        )

        item = result["missions"][0]

        self.assertEqual(
            item["mission"]["id"],
            "m-status-1",
        )

        self.assertEqual(
            item["execution"]["execution_id"],
            "exec-status-1",
        )

        self.assertEqual(
            item["execution"]["git_commit"],
            "a" * 40,
        )

    def test_request_status_not_found(self):
        runtime = self.build_runtime()

        with self.assertRaisesRegex(
            KeyError,
            "request_not_found",
        ):
            runtime.get_request_status(
                "missing-request"
            )


if __name__ == "__main__":
    unittest.main()
