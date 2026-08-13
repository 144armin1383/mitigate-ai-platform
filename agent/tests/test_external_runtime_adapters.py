from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.execution.openclaw_adapter import OpenClawRuntimeAdapter
from agent.execution.ruflo_adapter import RufloRuntimeAdapter
from agent.execution.runtime_adapter import ExecutionRequest, RuntimeStatus


def request(**metadata):
    return ExecutionRequest(
        request_id="r1",
        mission_id="m1",
        objective="bounded capability task",
        repository_root="/repo",
        base_revision="abc123",
        metadata=metadata,
    )


class ExternalRuntimeAdapterTests(unittest.TestCase):
    def test_openclaw_is_explicit_capability_only(self) -> None:
        adapter = OpenClawRuntimeAdapter(runner=lambda **_: None)
        result = adapter.execute(request())
        self.assertEqual(RuntimeStatus.blocked, result.status)
        self.assertEqual("openclaw_requires_explicit_capability_task", result.reason)

    def test_openclaw_injected_runner_normalizes_success(self) -> None:
        adapter = OpenClawRuntimeAdapter(
            runner=lambda **_: SimpleNamespace(session_id="oc-1")
        )
        result = adapter.execute(request(openclaw_capability_task=True))
        self.assertEqual(RuntimeStatus.succeeded, result.status)
        self.assertEqual("oc-1", result.evidence.provider_run_id)

    def test_ruflo_is_benchmark_gated(self) -> None:
        adapter = RufloRuntimeAdapter(runner=lambda **_: None)
        result = adapter.execute(request())
        self.assertEqual(RuntimeStatus.blocked, result.status)
        self.assertEqual("ruflo_is_benchmark_gated", result.reason)

    def test_ruflo_benchmark_runner_can_succeed(self) -> None:
        adapter = RufloRuntimeAdapter(
            runner=lambda **_: SimpleNamespace(session_id="rf-1")
        )
        result = adapter.execute(request(benchmark_mode=True))
        self.assertEqual(RuntimeStatus.succeeded, result.status)
        self.assertEqual("rf-1", result.evidence.provider_run_id)

    def test_adapters_remain_optional(self) -> None:
        self.assertTrue(OpenClawRuntimeAdapter(runner=lambda **_: None).healthcheck()["available"])
        self.assertTrue(RufloRuntimeAdapter(runner=lambda **_: None).healthcheck()["available"])


if __name__ == "__main__":
    unittest.main()
