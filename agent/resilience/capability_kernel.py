from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ProviderKind(str, Enum):
    NATIVE = "native"
    EXTERNAL = "external"


class ProviderState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    ISOLATED = "isolated"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    provider_id: str
    provider_kind: ProviderKind
    priority: int = 100


@dataclass
class CapabilityHealth:
    provider_id: str
    state: ProviderState = ProviderState.HEALTHY
    consecutive_failures: int = 0
    last_error: str | None = None


class CapabilityProvider(Protocol):
    @property
    def provider_id(self) -> str:
        ...

    @property
    def provider_kind(self) -> ProviderKind:
        ...

    def capabilities(
        self,
    ) -> tuple[str, ...]:
        ...

    def execute(
        self,
        capability_id: str,
        payload: dict[str, Any],
    ) -> Any:
        ...


@dataclass
class RegisteredProvider:
    provider: CapabilityProvider
    priority: int
    health: CapabilityHealth


class CapabilityRegistry:
    """
    Provider-neutral capability registry.

    Native MITIGATE providers and optional external providers
    are registered behind the same contract. No external provider
    is required for the registry to function.
    """

    def __init__(self) -> None:
        self._providers: dict[
            str,
            RegisteredProvider,
        ] = {}

    def register(
        self,
        provider: CapabilityProvider,
        *,
        priority: int = 100,
    ) -> None:
        provider_id = str(
            provider.provider_id
        ).strip()

        if not provider_id:
            raise ValueError(
                "invalid_provider_id"
            )

        if provider_id in self._providers:
            raise ValueError(
                "provider_already_registered"
            )

        self._providers[provider_id] = (
            RegisteredProvider(
                provider=provider,
                priority=int(priority),
                health=CapabilityHealth(
                    provider_id=provider_id,
                ),
            )
        )

    def get(
        self,
        provider_id: str,
    ) -> RegisteredProvider:
        try:
            return self._providers[
                provider_id
            ]
        except KeyError as exc:
            raise KeyError(
                "provider_not_found"
            ) from exc

    def providers_for(
        self,
        capability_id: str,
    ) -> list[RegisteredProvider]:
        result = []

        for registered in (
            self._providers.values()
        ):
            if capability_id not in (
                registered.provider
                .capabilities()
            ):
                continue

            if registered.health.state in {
                ProviderState.UNAVAILABLE,
                ProviderState.ISOLATED,
            }:
                continue

            result.append(registered)

        result.sort(
            key=lambda item: (
                0
                if item.provider.provider_kind
                == ProviderKind.NATIVE
                else 1,
                item.priority,
                item.provider.provider_id,
            )
        )

        return result

    def health(
        self,
        provider_id: str,
    ) -> CapabilityHealth:
        return self.get(
            provider_id
        ).health


class CircuitBreaker:
    """
    Isolates failing providers without affecting the MITIGATE core.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        failure_threshold: int = 3,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError(
                "invalid_failure_threshold"
            )

        self._registry = registry
        self._failure_threshold = (
            failure_threshold
        )

    def record_success(
        self,
        provider_id: str,
    ) -> None:
        health = self._registry.health(
            provider_id
        )
        health.consecutive_failures = 0
        health.last_error = None

        if (
            health.state
            != ProviderState.ISOLATED
        ):
            health.state = (
                ProviderState.HEALTHY
            )

    def record_failure(
        self,
        provider_id: str,
        error: str,
    ) -> None:
        health = self._registry.health(
            provider_id
        )

        health.consecutive_failures += 1
        health.last_error = str(
            error
        )[:500]

        if (
            health.consecutive_failures
            >= self._failure_threshold
        ):
            health.state = (
                ProviderState.ISOLATED
            )
        else:
            health.state = (
                ProviderState.DEGRADED
            )

    def isolate(
        self,
        provider_id: str,
        reason: str,
    ) -> None:
        health = self._registry.health(
            provider_id
        )
        health.state = (
            ProviderState.ISOLATED
        )
        health.last_error = str(
            reason
        )[:500]


@dataclass(frozen=True)
class CapabilityGap:
    capability_id: str
    external_provider_id: str | None
    native_provider_available: bool
    reason: str


class CapabilityGapDetector:
    def __init__(
        self,
        registry: CapabilityRegistry,
    ) -> None:
        self._registry = registry

    def detect(
        self,
        capability_id: str,
    ) -> CapabilityGap | None:
        providers = (
            self._registry
            .providers_for(
                capability_id
            )
        )

        native_available = any(
            item.provider.provider_kind
            == ProviderKind.NATIVE
            for item in providers
        )

        external = next(
            (
                item
                for item in providers
                if (
                    item.provider
                    .provider_kind
                    == ProviderKind.EXTERNAL
                )
            ),
            None,
        )

        if native_available:
            return None

        return CapabilityGap(
            capability_id=capability_id,
            external_provider_id=(
                external.provider.provider_id
                if external
                else None
            ),
            native_provider_available=False,
            reason=(
                "native_capability_missing"
            ),
        )


@dataclass(frozen=True)
class ReplacementMission:
    mission_type: str
    capability_id: str
    goal: str
    source_provider_id: str | None
    constraints: tuple[str, ...]


class ReplacementMissionFactory:
    """
    Produces a development mission for building a native MITIGATE
    replacement for a missing external capability.

    It does not execute or merge anything itself.
    """

    def build(
        self,
        gap: CapabilityGap,
    ) -> ReplacementMission:
        return ReplacementMission(
            mission_type=(
                "native_capability_replacement"
            ),
            capability_id=(
                gap.capability_id
            ),
            source_provider_id=(
                gap.external_provider_id
            ),
            goal=(
                "Implement a MITIGATE-native "
                f"replacement for capability "
                f"'{gap.capability_id}'"
            ),
            constraints=(
                "must_not_require_external_provider",
                "must_preserve_existing_core_contracts",
                "must_add_regression_tests",
                "must_support_safe_fallback",
                "must_be_portable_via_github",
            ),
        )


class FallbackRouter:
    """
    Routes capability execution with native-first resilience.

    External providers may be used only when no healthy native provider
    can satisfy the capability.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        self._registry = registry
        self._breaker = circuit_breaker

    def execute(
        self,
        capability_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        providers = (
            self._registry
            .providers_for(
                capability_id
            )
        )

        if not providers:
            raise RuntimeError(
                "capability_unavailable"
            )

        errors: list[str] = []

        for item in providers:
            provider = item.provider

            try:
                result = provider.execute(
                    capability_id,
                    payload,
                )

                self._breaker.record_success(
                    provider.provider_id
                )

                return {
                    "provider_id":
                        provider.provider_id,
                    "provider_kind":
                        provider.provider_kind.value,
                    "fallback_used":
                        provider.provider_kind
                        != ProviderKind.NATIVE,
                    "result": result,
                }

            except Exception as exc:
                self._breaker.record_failure(
                    provider.provider_id,
                    str(exc),
                )

                errors.append(
                    f"{provider.provider_id}:"
                    f"{str(exc)[:200]}"
                )

        raise RuntimeError(
            "capability_execution_failed: "
            + " | ".join(errors)
        )


__all__ = [
    "CapabilityDescriptor",
    "CapabilityGap",
    "CapabilityGapDetector",
    "CapabilityHealth",
    "CapabilityProvider",
    "CapabilityRegistry",
    "CircuitBreaker",
    "FallbackRouter",
    "ProviderKind",
    "ProviderState",
    "ReplacementMission",
    "ReplacementMissionFactory",
]
