from __future__ import annotations

import unittest

from agent.execution.provider_task_policy import decide_provider, provider_contract


class ProviderTaskPolicyTests(unittest.TestCase):
    def test_backend_and_technical_seo_prefer_openhands(self) -> None:
        backend = decide_provider("backend", "Fix an API bug and run tests")
        self.assertEqual(backend.preferred[0], "openhands")
        seo = decide_provider("seo", "Audit redirects, sitemap, robots and technical SEO")
        self.assertEqual(seo.preferred[0], "openhands")

    def test_frontend_wordpress_and_design_reference_prefer_openclaw(self) -> None:
        decision = decide_provider(
            "frontend",
            "Create a responsive WordPress recruitment page using the current UI and motionsites.ai as optional visual inspiration",
        )
        self.assertEqual(decision.preferred[0], "openclaw")
        self.assertTrue(decision.requirements.browser)

    def test_explicit_runtime_switch_is_respected(self) -> None:
        self.assertEqual(
            decide_provider("backend", "runtime=openclaw validate this through the browser").preferred,
            ("openclaw",),
        )
        self.assertEqual(
            decide_provider("frontend", "provider=openhands implement this page").preferred,
            ("openhands",),
        )

    def test_frontend_contract_is_host_agnostic_and_clarification_aware(self) -> None:
        text = " ".join(provider_contract("openclaw")).lower()
        self.assertIn("never hard-code", text)
        self.assertIn("clarification", text)
        self.assertIn("motionsites.ai", text)


if __name__ == "__main__":
    unittest.main()
