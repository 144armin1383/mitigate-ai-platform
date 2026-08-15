from __future__ import annotations

import unittest

from agent.runtime.project_scope_resolver import ProjectScopeResolver


class ProjectScopeResolverTests(unittest.TestCase):
    def test_wordpress_deployment_is_scoped_to_wordpress_source(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="deployment",
            objective=(
                "Build a WordPress recruitment form and make it available "
                "at /fourmnew without changing unrelated infrastructure."
            ),
            context={"project_type": "git"},
        )

        self.assertEqual("wordpress", decision.project_kind)
        self.assertIn("wordpress", decision.allowed_paths)
        self.assertIn("docs", decision.allowed_paths)
        self.assertNotIn("agent", decision.allowed_paths)
        self.assertIn("agent", decision.denied_paths)

    def test_wordpress_project_type_derives_wordpress_scope(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="deployment",
            objective="Deploy the requested feature.",
            context={"project_type": "wordpress"},
        )

        self.assertEqual("wordpress", decision.project_kind)
        self.assertEqual(("wordpress", "docs"), decision.allowed_paths)

    def test_platform_self_maintenance_keeps_core_scope(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="deployment",
            objective=(
                "Improve MITIGATE Core project-aware scope derivation and "
                "update architecture documentation."
            ),
            context={"project_type": "git"},
        )

        self.assertEqual("mitigate-platform", decision.project_kind)
        self.assertEqual(("agent", "docs", ".github"), decision.allowed_paths)
        self.assertNotIn("agent", decision.denied_paths)

    def test_documentation_explicit_deliverable_remains_narrow(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="documentation",
            objective="Write the requested architecture assessment.",
            context={"project_type": "git"},
            deliverables=("docs/architecture/review.md",),
        )

        self.assertEqual(
            ("docs/architecture/review.md",),
            decision.allowed_paths,
        )

    def test_wordpress_ignores_unrelated_explicit_paths(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="deployment",
            objective="Create a WooCommerce feature.",
            context={"project_type": "git"},
            deliverables=(
                "agent/runtime/unsafe.py",
                "wordpress/mitigate-core/recruitment.php",
                "docs/recruitment.md",
            ),
        )

        self.assertIn("wordpress", decision.allowed_paths)
        self.assertIn("wordpress/mitigate-core/recruitment.php", decision.allowed_paths)
        self.assertIn("docs/recruitment.md", decision.allowed_paths)
        self.assertNotIn("agent/runtime/unsafe.py", decision.allowed_paths)
        self.assertIn("agent", decision.denied_paths)

    def test_absolute_url_or_host_paths_are_not_scope_grants(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="documentation",
            objective="Document the public target.",
            context={"project_type": "git"},
            deliverables=(
                "https://18.175.175.110/fourmnew",
                "/srv/mitigate/private/recruitment-cv",
            ),
        )

        self.assertEqual(("docs", "README.md"), decision.allowed_paths)

    def test_generic_behavior_remains_backward_compatible(self) -> None:
        decision = ProjectScopeResolver.derive(
            task_type="backend",
            objective="Implement a backend maintenance change.",
            context={"project_type": "git"},
        )

        self.assertEqual("generic", decision.project_kind)
        self.assertEqual(("agent",), decision.allowed_paths)


if __name__ == "__main__":
    unittest.main()
