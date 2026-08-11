from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional


class RufloMode(str, Enum):
    """Resolved execution mode for an optional Ruflo capability."""

    NATIVE = "native"
    RUFLO = "ruflo"


class RufloVersionPolicyError(ValueError):
    """Raised when a Ruflo production version policy is unsafe."""


@dataclass(frozen=True)
class RufloIntegrationConfig:
    """
    Configuration boundary between MITIGATE AI and Ruflo.

    Ruflo is disabled by default. Production activation requires an exact,
    compatibility-certified version. Floating selectors such as ``latest``
    are intentionally rejected so an upstream release can never silently
    change production behaviour.
    """

    enabled: bool = False
    certified_version: Optional[str] = None
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        version = (
            str(self.certified_version).strip()
            if self.certified_version is not None
            else None
        )

        if version is not None:
            _validate_exact_version(version)
            object.__setattr__(
                self,
                "certified_version",
                version,
            )

        normalized = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in self.capabilities
                    if str(item).strip()
                }
            )
        )
        object.__setattr__(
            self,
            "capabilities",
            normalized,
        )


@dataclass(frozen=True)
class RufloHealth:
    enabled: bool
    available: bool
    certified: bool
    installed_version: Optional[str]
    certified_version: Optional[str]
    mode: RufloMode
    reason: str


class RufloAdapter:
    """
    Fail-safe optional adapter around Ruflo.

    The adapter does not install, upgrade, or execute Ruflo by itself. It only
    decides whether a pre-validated Ruflo runtime is eligible for use. If any
    prerequisite is missing or mismatched, MITIGATE AI remains in native mode.
    """

    def __init__(
        self,
        config: RufloIntegrationConfig,
    ) -> None:
        self._config = config

    @property
    def config(self) -> RufloIntegrationConfig:
        return self._config

    def supports(self, capability: str) -> bool:
        capability = str(capability or "").strip()
        return bool(
            capability
            and capability in self._config.capabilities
        )

    def resolve_mode(
        self,
        *,
        available: bool,
        installed_version: Optional[str],
        required_capability: Optional[str] = None,
    ) -> RufloMode:
        return self.health(
            available=available,
            installed_version=installed_version,
            required_capability=required_capability,
        ).mode

    def health(
        self,
        *,
        available: bool,
        installed_version: Optional[str],
        required_capability: Optional[str] = None,
    ) -> RufloHealth:
        version = (
            str(installed_version).strip()
            if installed_version is not None
            else None
        )

        if not self._config.enabled:
            return self._native_health(
                available=available,
                installed_version=version,
                reason="ruflo_disabled",
            )

        if not self._config.certified_version:
            return self._native_health(
                available=available,
                installed_version=version,
                reason="no_certified_version",
            )

        if not available:
            return self._native_health(
                available=False,
                installed_version=version,
                reason="ruflo_unavailable",
            )

        if not version:
            return self._native_health(
                available=True,
                installed_version=None,
                reason="ruflo_version_unknown",
            )

        if version != self._config.certified_version:
            return self._native_health(
                available=True,
                installed_version=version,
                reason="ruflo_version_not_certified",
            )

        capability = str(
            required_capability or ""
        ).strip()
        if capability and not self.supports(capability):
            return self._native_health(
                available=True,
                installed_version=version,
                reason="ruflo_capability_not_enabled",
            )

        return RufloHealth(
            enabled=True,
            available=True,
            certified=True,
            installed_version=version,
            certified_version=(
                self._config.certified_version
            ),
            mode=RufloMode.RUFLO,
            reason="ruflo_certified",
        )

    def _native_health(
        self,
        *,
        available: bool,
        installed_version: Optional[str],
        reason: str,
    ) -> RufloHealth:
        return RufloHealth(
            enabled=self._config.enabled,
            available=available,
            certified=False,
            installed_version=installed_version,
            certified_version=(
                self._config.certified_version
            ),
            mode=RufloMode.NATIVE,
            reason=reason,
        )


def _validate_exact_version(version: str) -> None:
    lowered = version.lower()
    forbidden = (
        "latest",
        "next",
        "alpha",
        "beta",
        "rc",
        "*",
        "^",
        "~",
        ">",
        "<",
        "=",
        " ",
    )

    if not version or any(
        token in lowered
        for token in forbidden
    ):
        raise RufloVersionPolicyError(
            "ruflo_version_must_be_exact_stable"
        )

    parts = version.split(".")
    if (
        len(parts) != 3
        or not all(part.isdigit() for part in parts)
    ):
        raise RufloVersionPolicyError(
            "ruflo_version_must_be_exact_stable"
        )


def normalize_capabilities(
    capabilities: Iterable[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(item).strip()
                for item in capabilities
                if str(item).strip()
            }
        )
    )


__all__ = [
    "RufloAdapter",
    "RufloHealth",
    "RufloIntegrationConfig",
    "RufloMode",
    "RufloVersionPolicyError",
    "normalize_capabilities",
]
