from __future__ import annotations

import unittest

from agent.runtime.project_operation_policy import ProjectOperationPolicy


class ProjectOperationPolicyTests(unittest.TestCase):
    def test_routine_wordpress_feature_is_preclassified_without_prompt(self) -> None:
        decision = ProjectOperationPolicy.derive(
            task_type="deployment",
            objective=(
                "Create a professional WordPress recruitment form, create the "
                "required plugin-owned tables and private CV storage, publish "
                "it at /fourmnew, activate the plugin with WP-CLI, and verify "
                "the page health."
            ),
            context={"project_type": "wordpress"},
            scope_project_kind="wordpress",
        )

        self.assertFalse(decision.requires_explicit_authorization)
        self.assertEqual("wordpress", decision.project_kind)
        self.assertIn("wordpress.page_content", decision.routine_operations)
        self.assertIn("wordpress.plugin_owned_schema", decision.routine_operations)
        self.assertIn("wordpress.private_project_storage", decision.routine_operations)
        self.assertIn("wordpress.wp_cli_project_actions", decision.routine_operations)
        self.assertIn("project.deploy", decision.routine_operations)
        self.assertIn("project.healthcheck", decision.routine_operations)

    def test_prohibition_mentions_do_not_trigger_protected_block(self) -> None:
        decision = ProjectOperationPolicy.derive(
            task_type="wordpress",
            objective=(
                "Build the recruitment form. Do not modify Nginx, do not "
                "change systemd, and never modify WordPress core or the parent theme."
            ),
            context={"project_type": "wordpress"},
            scope_project_kind="wordpress",
        )

        self.assertFalse(decision.requires_explicit_authorization)
        self.assertEqual((), decision.protected_operations)

    def test_explicit_nginx_change_remains_protected(self) -> None:
        decision = ProjectOperationPolicy.derive(
            task_type="deployment",
            objective="Modify the Nginx server configuration to add a new route.",
            context={"project_type": "wordpress"},
            scope_project_kind="wordpress",
        )

        self.assertTrue(decision.requires_explicit_authorization)
        self.assertIn("host.nginx_global", decision.protected_operations)

    def test_explicit_systemd_change_remains_protected(self) -> None:
        decision = ProjectOperationPolicy.derive(
            task_type="deployment",
            objective="Restart and reconfigure systemd for the website service.",
            context={"project_type": "wordpress"},
            scope_project_kind="wordpress",
        )

        self.assertTrue(decision.requires_explicit_authorization)
        self.assertIn("host.systemd_global", decision.protected_operations)

    def test_destructive_database_request_remains_protected(self) -> None:
        decision = ProjectOperationPolicy.derive(
            task_type="database",
            objective="Drop table wp_users and rebuild it.",
            context={"project_type": "wordpress"},
            scope_project_kind="wordpress",
        )

        self.assertTrue(decision.requires_explicit_authorization)
        self.assertIn("database.destructive", decision.protected_operations)

    def test_mitigate_self_maintenance_does_not_get_wordpress_host_capabilities(self) -> None:
        decision = ProjectOperationPolicy.derive(
            task_type="deployment",
            objective="Improve MITIGATE Core runtime scope handling.",
            context={"project_type": "git"},
            scope_project_kind="mitigate-platform",
        )

        self.assertEqual("mitigate-platform", decision.project_kind)
        self.assertEqual(
            ("project.repo_write", "project.validate"),
            decision.routine_operations,
        )
        self.assertNotIn("project.deploy", decision.routine_operations)


if __name__ == "__main__":
    unittest.main()
