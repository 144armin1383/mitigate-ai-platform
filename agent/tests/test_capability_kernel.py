from __future__ import annotations

import unittest

from agent.resilience.capability_kernel import (
    CapabilityGapDetector,
    CapabilityRegistry,
    CircuitBreaker,
    FallbackRouter,
    ProviderKind,
    ProviderState,
    ReplacementMissionFactory,
)


class FakeProvider:

    def __init__(
        self,
        provider_id,
        provider_kind,
        capabilities,
        *,
        result=None,
        fail=False,
    ):
        self._provider_id = provider_id
        self._provider_kind = provider_kind
        self._capabilities = tuple(
            capabilities
        )
        self.result = result
        self.fail = fail

    @property
    def provider_id(self):
        return self._provider_id

    @property
    def provider_kind(self):
        return self._provider_kind

    def capabilities(self):
        return self._capabilities

    def execute(
        self,
        capability_id,
        payload,
    ):
        if self.fail:
            raise RuntimeError(
                "provider_failed"
            )

        return self.result


class CapabilityKernelTests(
    unittest.TestCase
):

    def test_native_provider_is_preferred(
        self,
    ):
        registry = CapabilityRegistry()

        external = FakeProvider(
            "external",
            ProviderKind.EXTERNAL,
            ("review",),
            result="external",
        )

        native = FakeProvider(
            "native",
            ProviderKind.NATIVE,
            ("review",),
            result="native",
        )

        registry.register(
            external,
            priority=1,
        )

        registry.register(
            native,
            priority=100,
        )

        router = FallbackRouter(
            registry,
            CircuitBreaker(registry),
        )

        result = router.execute(
            "review",
            {},
        )

        self.assertEqual(
            result["provider_id"],
            "native",
        )

        self.assertEqual(
            result["result"],
            "native",
        )

    def test_external_failure_never_breaks_native(
        self,
    ):
        registry = CapabilityRegistry()

        native = FakeProvider(
            "native",
            ProviderKind.NATIVE,
            ("memory",),
            result="native-memory",
        )

        external = FakeProvider(
            "external",
            ProviderKind.EXTERNAL,
            ("memory",),
            fail=True,
        )

        registry.register(native)
        registry.register(external)

        router = FallbackRouter(
            registry,
            CircuitBreaker(registry),
        )

        result = router.execute(
            "memory",
            {},
        )

        self.assertEqual(
            result["provider_id"],
            "native",
        )

    def test_failing_external_provider_is_isolated(
        self,
    ):
        registry = CapabilityRegistry()

        provider = FakeProvider(
            "external",
            ProviderKind.EXTERNAL,
            ("swarm",),
            fail=True,
        )

        registry.register(provider)

        breaker = CircuitBreaker(
            registry,
            failure_threshold=2,
        )

        breaker.record_failure(
            "external",
            "one",
        )

        self.assertEqual(
            registry.health(
                "external"
            ).state,
            ProviderState.DEGRADED,
        )

        breaker.record_failure(
            "external",
            "two",
        )

        self.assertEqual(
            registry.health(
                "external"
            ).state,
            ProviderState.ISOLATED,
        )

    def test_gap_detector_detects_missing_native(
        self,
    ):
        registry = CapabilityRegistry()

        registry.register(
            FakeProvider(
                "external",
                ProviderKind.EXTERNAL,
                ("consensus",),
            )
        )

        gap = CapabilityGapDetector(
            registry
        ).detect(
            "consensus"
        )

        self.assertIsNotNone(gap)

        self.assertEqual(
            gap.capability_id,
            "consensus",
        )

        self.assertFalse(
            gap.native_provider_available
        )

    def test_gap_detector_ignores_native_capability(
        self,
    ):
        registry = CapabilityRegistry()

        registry.register(
            FakeProvider(
                "native",
                ProviderKind.NATIVE,
                ("consensus",),
            )
        )

        gap = CapabilityGapDetector(
            registry
        ).detect(
            "consensus"
        )

        self.assertIsNone(gap)

    def test_replacement_mission_is_native_only(
        self,
    ):
        registry = CapabilityRegistry()

        registry.register(
            FakeProvider(
                "external",
                ProviderKind.EXTERNAL,
                ("swarm",),
            )
        )

        gap = CapabilityGapDetector(
            registry
        ).detect(
            "swarm"
        )

        mission = (
            ReplacementMissionFactory()
            .build(gap)
        )

        self.assertEqual(
            mission.mission_type,
            "native_capability_replacement",
        )

        self.assertIn(
            "must_not_require_external_provider",
            mission.constraints,
        )


if __name__ == "__main__":
    unittest.main()
