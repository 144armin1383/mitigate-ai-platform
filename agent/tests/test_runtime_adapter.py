from __future__ import annotations

import unittest

from agent.execution.runtime_adapter import (
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)


class FakeAdapter:
    def __init__(self, name: str, capabilities: RuntimeCapabilities, available: bool = True) -> None:
        self._name = name
        self._capabilities = capabilities
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    def healthcheck(self):
        return {"available": self._available}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(status=RuntimeStatus.succeeded, provider=self.name)

    def cancel(self, provider_run_id: str) -> bool:
        return True


class RuntimeAdapterTests(unittest.TestCase):
    def test_registry_prefers_requested_healthy_provider(self) -> None:
        openhands = FakeAdapter(
            "openhands",
            RuntimeCapabilities(coding=True, terminal=True, tests=True, isolated_workspace=True),
        )
        fallback = FakeAdapter(
            "fallback",
            RuntimeCapabilities(coding=True, terminal=True, tests=True, isolated_workspace=True),
        )

        registry = RuntimeRegistry([fallback, openhands])
        selected = registry.choose(
            require=RuntimeCapabilities(coding=True, tests=True, isolated_workspace=True),
            preferred=("openhands",),
        )

        self.assertEqual("openhands", selected.name)

    def test_registry_skips_unhealthy_provider(self) -> None:
        unhealthy = FakeAdapter(
            "openhands",
            RuntimeCapabilities(coding=True, tests=True),
            available=False,
        )
        healthy = FakeAdapter(
            "fallback",
            RuntimeCapabilities(coding=True, tests=True),
        )

        registry = RuntimeRegistry([unhealthy, healthy])
        selected = registry.choose(require=RuntimeCapabilities(coding=True, tests=True))

        self.assertEqual("fallback", selected.name)

    def test_registry_rejects_missing_capability(self) -> None:
        registry = RuntimeRegistry(
            [FakeAdapter("openhands", RuntimeCapabilities(coding=True))]
        )

        with self.assertRaises(LookupError):
            registry.choose(require=RuntimeCapabilities(coding=True, browser=True))

    def test_duplicate_provider_name_is_rejected(self) -> None:
        adapter = FakeAdapter("openhands", RuntimeCapabilities(coding=True))
        registry = RuntimeRegistry([adapter])

        with self.assertRaises(ValueError):
            registry.register(adapter)

    def test_execution_request_keeps_mitigate_owned_boundaries(self) -> None:
        request = ExecutionRequest(
            request_id="request-1",
            mission_id="mission-1",
            objective="Perform a safe code change",
            repository_root="/workspace/project",
            base_revision="abc123",
            allowed_paths=("agent/",),
            denied_paths=("secrets/",),
            acceptance_criteria=("tests pass",),
        )

        self.assertEqual(("agent/",), request.allowed_paths)
        self.assertEqual(("secrets/",), request.denied_paths)
        self.assertEqual(("tests pass",), request.acceptance_criteria)


if __name__ == "__main__":
    unittest.main()
