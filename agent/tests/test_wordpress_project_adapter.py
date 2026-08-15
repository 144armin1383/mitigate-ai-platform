from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.projects.project_adapter import ProjectDeploymentRequest
from agent.projects.wordpress_project_adapter import WordPressProjectAdapter


class _Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        del kwargs
        self.calls.append(list(argv))
        if "list" in argv and "--field=ID" in argv:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")


class WordPressProjectAdapterTests(unittest.TestCase):
    def _fixture(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        repo = root / "repo"
        wp = root / "wordpress"
        (repo / "wordpress" / "mitigate-recruitment").mkdir(parents=True)
        (repo / "wordpress" / "mitigate-recruitment" / "plugin.php").write_text(
            "<?php // plugin\n", encoding="utf-8"
        )
        (wp / "wp-content" / "plugins").mkdir(parents=True)
        (wp / "wp-content" / "themes").mkdir(parents=True)
        return td, repo, wp

    def _request(self, repo: Path) -> ProjectDeploymentRequest:
        return ProjectDeploymentRequest(
            project_id="mitigate-ai-platform",
            repository_root=str(repo),
            revision="abc123",
            changed_files=(
                "wordpress/mitigate-recruitment/plugin.php",
                "wordpress/mitigate-deploy.json",
            ),
            routine_operations=(
                "project.deploy",
                "wordpress.plugin_activate",
                "wordpress.page_content",
                "project.healthcheck",
            ),
        )

    def test_deploys_plugin_and_applies_bounded_manifest(self) -> None:
        td, repo, wp = self._fixture()
        with td:
            manifest = {
                "version": 1,
                "actions": [
                    {"type": "activate_plugin", "plugin": "mitigate-recruitment"},
                    {
                        "type": "ensure_page",
                        "slug": "fourmnew",
                        "title": "Careers",
                        "content": "[mitigate_recruitment_form]",
                    },
                    {"type": "health_path", "path": "/fourmnew"},
                ],
            }
            (repo / "wordpress" / "mitigate-deploy.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            runner = _Runner()
            adapter = WordPressProjectAdapter(
                wordpress_root=wp,
                wp_binary="wp",
                health_base_url="https://example.test",
                runner=runner,
                urlopen=lambda url, timeout: SimpleNamespace(status=200),
            )
            result = adapter.deploy(self._request(repo))

            self.assertTrue(result.success, result)
            self.assertTrue(
                (wp / "wp-content" / "plugins" / "mitigate-recruitment" / "plugin.php").is_file()
            )
            self.assertIn("deploy_plugin:mitigate-recruitment", result.actions)
            self.assertIn("activate_plugin:mitigate-recruitment", result.actions)
            self.assertIn("create_page:fourmnew", result.actions)
            self.assertEqual("https://example.test/fourmnew", result.health_url)
            self.assertTrue(result.health_ok)
            flattened = [item for call in runner.calls for item in call]
            self.assertNotIn("sh", flattened)
            self.assertNotIn("bash", flattened)
            self.assertNotIn("eval", flattened)

    def test_manifest_rejects_command_or_sql_fields(self) -> None:
        td, repo, wp = self._fixture()
        with td:
            (repo / "wordpress" / "mitigate-deploy.json").write_text(
                json.dumps({
                    "version": 1,
                    "actions": [
                        {"type": "ensure_page", "slug": "fourmnew", "title": "x", "command": "rm -rf /"}
                    ],
                }),
                encoding="utf-8",
            )
            adapter = WordPressProjectAdapter(wordpress_root=wp, runner=_Runner())
            result = adapter.deploy(self._request(repo))
            self.assertFalse(result.success)
            self.assertTrue(any("RuntimeError" in item for item in result.diagnostics))

    def test_deploy_requires_routine_deploy_capability(self) -> None:
        td, repo, wp = self._fixture()
        with td:
            adapter = WordPressProjectAdapter(wordpress_root=wp, runner=_Runner())
            request = ProjectDeploymentRequest(
                project_id="p",
                repository_root=str(repo),
                revision="abc",
                changed_files=("wordpress/mitigate-recruitment/plugin.php",),
                routine_operations=("project.repo_write",),
            )
            result = adapter.deploy(request)
            self.assertFalse(result.success)
            self.assertIn("project_deploy_not_authorized", result.diagnostics)

    def test_child_theme_maps_only_to_themes_directory(self) -> None:
        td, repo, wp = self._fixture()
        with td:
            (repo / "wordpress" / "martfury-child").mkdir()
            (repo / "wordpress" / "martfury-child" / "style.css").write_text(
                "/* child */\n", encoding="utf-8"
            )
            adapter = WordPressProjectAdapter(wordpress_root=wp, runner=_Runner())
            request = ProjectDeploymentRequest(
                project_id="p",
                repository_root=str(repo),
                revision="abc",
                changed_files=("wordpress/martfury-child/style.css",),
                routine_operations=("project.deploy",),
            )
            result = adapter.deploy(request)
            self.assertTrue(result.success)
            self.assertTrue((wp / "wp-content" / "themes" / "martfury-child" / "style.css").is_file())
            self.assertFalse((wp / "wp-content" / "plugins" / "martfury-child").exists())


if __name__ == "__main__":
    unittest.main()
