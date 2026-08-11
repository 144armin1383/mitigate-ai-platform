from __future__ import annotations

import unittest

from agent.integrations.ruflo_adapter import (
    RufloAdapter,
    RufloIntegrationConfig,
    RufloMode,
    RufloVersionPolicyError,
)


class RufloAdapterIndependenceTests(unittest.TestCase):
    def test_disabled_ruflo_always_uses_native_mode(self) -> None:
        adapter = RufloAdapter(
            RufloIntegrationConfig(
                enabled=False,
                certified_version="3.35.0",
                capabilities=("swarm",),
            )
        )

        health = adapter.health(
            available=True,
            installed_version="3.35.0",
            required_capability="swarm",
        )

        self.assertEqual(
            RufloMode.NATIVE,
            health.mode,
        )
        self.assertEqual(
            "ruflo_disabled",
            health.reason,
        )

    def test_missing_ruflo_falls_back_to_native(self) -> None:
        adapter = RufloAdapter(
            RufloIntegrationConfig(
                enabled=True,
                certified_version="3.35.0",
                capabilities=("swarm",),
            )
        )

        health = adapter.health(
            available=False,
            installed_version=None,
            required_capability="swarm",
        )

        self.assertEqual(
            RufloMode.NATIVE,
            health.mode,
        )
        self.assertEqual(
            "ruflo_unavailable",
            health.reason,
        )

    def test_uncertified_installed_version_uses_native(self) -> None:
        adapter = RufloAdapter(
            RufloIntegrationConfig(
                enabled=True,
                certified_version="3.35.0",
                capabilities=("memory",),
            )
        )

        health = adapter.health(
            available=True,
            installed_version="3.36.0",
            required_capability="memory",
        )

        self.assertEqual(
            RufloMode.NATIVE,
            health.mode,
        )
        self.assertFalse(health.certified)
        self.assertEqual(
            "ruflo_version_not_certified",
            health.reason,
        )

    def test_exact_certified_version_can_use_ruflo(self) -> None:
        adapter = RufloAdapter(
            RufloIntegrationConfig(
                enabled=True,
                certified_version="3.35.0",
                capabilities=("memory", "swarm"),
            )
        )

        health = adapter.health(
            available=True,
            installed_version="3.35.0",
            required_capability="swarm",
        )

        self.assertEqual(
            RufloMode.RUFLO,
            health.mode,
        )
        self.assertTrue(health.certified)
        self.assertEqual(
            "ruflo_certified",
            health.reason,
        )

    def test_disabled_capability_falls_back_to_native(self) -> None:
        adapter = RufloAdapter(
            RufloIntegrationConfig(
                enabled=True,
                certified_version="3.35.0",
                capabilities=("memory",),
            )
        )

        health = adapter.health(
            available=True,
            installed_version="3.35.0",
            required_capability="swarm",
        )

        self.assertEqual(
            RufloMode.NATIVE,
            health.mode,
        )
        self.assertEqual(
            "ruflo_capability_not_enabled",
            health.reason,
        )

    def test_floating_versions_are_rejected(self) -> None:
        unsafe_versions = (
            "latest",
            "^3.35.0",
            "~3.35.0",
            "3.36.0-beta.1",
            "3.36.0-rc.1",
            "*",
        )

        for version in unsafe_versions:
            with self.subTest(version=version):
                with self.assertRaises(
                    RufloVersionPolicyError
                ):
                    RufloIntegrationConfig(
                        enabled=True,
                        certified_version=version,
                    )

    def test_no_certified_version_never_activates_ruflo(self) -> None:
        adapter = RufloAdapter(
            RufloIntegrationConfig(
                enabled=True,
                certified_version=None,
                capabilities=("swarm",),
            )
        )

        health = adapter.health(
            available=True,
            installed_version="3.35.0",
            required_capability="swarm",
        )

        self.assertEqual(
            RufloMode.NATIVE,
            health.mode,
        )
        self.assertEqual(
            "no_certified_version",
            health.reason,
        )


if __name__ == "__main__":
    unittest.main()
