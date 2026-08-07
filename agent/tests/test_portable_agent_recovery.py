from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.bootstrap.portable_bootstrap import (
    REQUIRED_REPO_DIRS,
    resolve_repo_root,
    validate_required_directories,
)
from agent.bootstrap.restore_manager import RestoreManager


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_DIR = REPO_ROOT / "agent" / "bootstrap"


class RepositoryStructureTests(unittest.TestCase):
    def test_required_repository_directories_exist(self):
        for rel in REQUIRED_REPO_DIRS:
            path = REPO_ROOT / rel
            self.assertTrue(path.is_dir(), f"Missing required directory: {rel}")

    def test_real_repository_validates(self):
        result = validate_required_directories(REPO_ROOT)
        self.assertEqual(result, REPO_ROOT.resolve())

    def test_missing_required_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in REQUIRED_REPO_DIRS:
                (root / rel).mkdir(parents=True, exist_ok=True)

            missing = root / "agent" / "memory"
            missing.rmdir()

            with self.assertRaises(FileNotFoundError):
                validate_required_directories(root)

    def test_repo_root_resolution_is_absolute(self):
        root = resolve_repo_root(REPO_ROOT)
        self.assertTrue(root.is_absolute())
        self.assertEqual(root, REPO_ROOT.resolve())


class EnvironmentTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = BOOTSTRAP_DIR / "env.example"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.values = {}

        for raw in cls.text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cls.values[key.strip()] = value.strip().strip('"').strip("'")

    def test_env_example_exists(self):
        self.assertTrue(self.path.is_file())

    def test_required_environment_fields(self):
        required_groups = {
            "environment": ("ENVIRONMENT", "ENV_NAME", "ENV"),
            "project": ("PROJECT_ID", "PROJECT"),
            "repository_root": ("REPOSITORY_ROOT", "MITIGATE_REPO_ROOT"),
            "data_root": ("DATA_ROOT", "AGENT_DATA_ROOT"),
            "memory_root": ("MEMORY_ROOT", "AGENT_MEMORY_ROOT"),
            "provider": ("PROVIDER",),
            "provider_base_url": ("PROVIDER_BASE_URL",),
            "provider_model": ("PROVIDER_MODEL",),
            "site_adapter": ("SITE_ADAPTER", "ADAPTER"),
            "runtime_host": ("RUNTIME_HOST", "BIND_HOST"),
            "runtime_port": ("RUNTIME_PORT", "BIND_PORT"),
        }

        missing = []
        for name, aliases in required_groups.items():
            if not any(alias in self.values for alias in aliases):
                missing.append(name)

        self.assertFalse(missing, f"Missing env concepts: {missing}")

    def test_sensitive_values_are_placeholders(self):
        sensitive_keys = [
            key for key in self.values
            if any(part in key.upper() for part in ("API_KEY", "TOKEN"))
        ]

        for key in sensitive_keys:
            value = self.values[key]
            self.assertTrue(
                value.startswith("<") and value.endswith(">"),
                f"{key} must use a placeholder",
            )

    def test_external_configuration_is_documented(self):
        text = self.text.lower()
        self.assertIn("external", text)
        self.assertIn("git", text)
        self.assertIn("placeholder", text)


class ProjectTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = BOOTSTRAP_DIR / "project.example.json"
        cls.data = json.loads(cls.path.read_text(encoding="utf-8"))
        cls.text = cls.path.read_text(encoding="utf-8").lower()

    def test_project_template_exists_and_is_json(self):
        self.assertTrue(self.path.is_file())
        self.assertIsInstance(self.data, dict)

    def test_required_project_fields(self):
        required = {
            "project_id",
            "project_name",
            "repository",
            "default_branch",
            "site_type",
            "cms_type",
            "adapter",
            "canonical_url",
            "allowed_paths",
            "denied_paths",
            "environment",
            "seo_enabled",
            "performance_monitoring_enabled",
            "availability_monitoring_enabled",
            "security_monitoring_enabled",
            "accessibility_monitoring_enabled",
            "ecommerce_enabled",
            "autonomous_low_risk_fixes",
            "autonomous_medium_risk_fixes",
            "memory_enabled",
            "metadata",
        }

        missing = sorted(required - set(self.data))
        self.assertFalse(missing, f"Missing project fields: {missing}")

    def test_adapter_is_configurable_string(self):
        self.assertIsInstance(self.data.get("adapter"), str)

    def test_supported_site_types(self):
        for name in (
            "wordpress",
            "lovable",
            "react",
            "nextjs",
            "static",
            "php",
            "generic_git",
            "custom",
        ):
            self.assertIn(name, self.text)


class BootstrapScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = BOOTSTRAP_DIR / "bootstrap.sh"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.lowered = cls.text.lower()

    def test_bootstrap_script_exists(self):
        self.assertTrue(self.path.is_file())

    def test_bash_strict_mode(self):
        self.assertIn("set -Eeuo pipefail", self.text)

    def test_repository_root_is_resolved_from_script(self):
        self.assertIn("dirname", self.lowered)
        self.assertIn("$0", self.text)
        self.assertIn("REPO_ROOT", self.text)

    def test_python_is_validated(self):
        self.assertIn("python", self.lowered)
        self.assertIn("command -v", self.text)

    def test_no_system_or_network_activation(self):
        forbidden = (
            "systemctl enable",
            "systemctl start",
            "iptables ",
            "ufw ",
            "nginx -s",
            "curl |",
            "wget |",
        )
        for marker in forbidden:
            self.assertNotIn(marker, self.lowered)


class RestoreManagerTests(unittest.TestCase):
    def test_safe_payload_validates(self):
        manager = RestoreManager(REPO_ROOT)

        payload = {
            "project_id": "example-project",
            "memory": {
                "decision": "Use portable adapters",
                "next_action": "Continue validation",
            },
            "files": {
                "memory/handoff.json": {
                    "status": "ready",
                    "provider": "external",
                }
            },
        }

        result = manager.validate_restore_payload(payload)
        self.assertTrue(result["ok"])

    def test_sensitive_payload_is_rejected(self):
        manager = RestoreManager(REPO_ROOT)

        payload = {
            "project_id": "example-project",
            "password": "<PROTECTED_VALUE>",
        }

        result = manager.validate_restore_payload(payload)
        self.assertFalse(result["ok"])
        self.assertTrue(result["sensitive_keys_detected"])

    def test_validation_only_restore_writes_nothing(self):
        manager = RestoreManager(REPO_ROOT)

        payload = {
            "files": {
                "memory/state.json": {"status": "ready"}
            }
        }

        with tempfile.TemporaryDirectory() as td:
            target = Path(td)

            result = manager.apply_restore(
                payload,
                target,
                validation_only=True,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(list(target.iterdir()), [])

    def test_path_traversal_is_not_restored(self):
        manager = RestoreManager(REPO_ROOT)

        payload = {
            "files": {
                "../outside.json": {"status": "blocked"}
            }
        }

        with tempfile.TemporaryDirectory() as td:
            target = Path(td)

            result = manager.apply_restore(payload, target)

            self.assertTrue(result["ok"])
            self.assertFalse((target.parent / "outside.json").exists())


class RecoveryDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (BOOTSTRAP_DIR / "README.md").read_text(
            encoding="utf-8"
        ).lower()

    def test_core_recovery_topics_are_documented(self):
        required = (
            "source of truth",
            "clean server",
            "external secret",
            "provider setup",
            "site adapter",
            "memory",
            "health",
            "systemd",
            "server migration",
            "provider migration",
            "rollback",
            "security model",
        )

        missing = [topic for topic in required if topic not in self.text]
        self.assertFalse(missing, f"Missing README topics: {missing}")


if __name__ == "__main__":
    unittest.main()
