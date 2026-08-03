import os
import re
import unittest
from pathlib import Path


class TestRuntimeSystemdDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Repository root: .../agent/tests -> parents[2] = repo root
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.deploy_dir = cls.repo_root / "agent" / "deploy" / "systemd"
        cls.service_path = cls.deploy_dir / "mitigate-ai-runtime.service"
        cls.env_example_path = cls.deploy_dir / "mitigate-ai-runtime.env.example"
        cls.install_script_path = cls.deploy_dir / "install.sh"
        cls.uninstall_script_path = cls.deploy_dir / "uninstall.sh"
        cls.healthcheck_script_path = cls.deploy_dir / "healthcheck.sh"
        cls.readme_path = cls.deploy_dir / "README.md"

    def read_text(self, path: Path) -> str:
        with path.open("r", encoding="utf-8") as f:
            return f.read()

    def test_all_deliverables_exist(self):
        for p in [
            self.service_path,
            self.env_example_path,
            self.install_script_path,
            self.uninstall_script_path,
            self.healthcheck_script_path,
            self.readme_path,
        ]:
            self.assertTrue(p.is_file(), f"Missing required file: {p}")

    def test_service_exec_and_env(self):
        content = self.read_text(self.service_path)
        # Uses the expected Python interpreter and module entrypoint
        self.assertIn(
            "ExecStart=/srv/mitigate/mitigate-ai-platform/agent/.venv/bin/python -m agent.api.runtime_private_api",
            content,
        )
        # Loads environment file
        self.assertIn("EnvironmentFile=/etc/mitigate-ai/runtime.env", content)
        # Runs as ubuntu
        self.assertIn("User=ubuntu", content)
        self.assertIn("Group=ubuntu", content)
        # Restart policy and graceful shutdown
        self.assertIn("Restart=on-failure", content)
        self.assertIn("RestartSec=5s", content)
        self.assertIn("KillSignal=SIGTERM", content)
        self.assertIn("TimeoutStopSec=30s", content)

    def test_service_hardening_directives(self):
        content = self.read_text(self.service_path)
        required = [
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "ProtectKernelTunables=true",
            "ProtectKernelModules=true",
            "ProtectKernelLogs=true",
            "ProtectControlGroups=true",
            "RestrictSUIDSGID=true",
            "LockPersonality=true",
            "MemoryDenyWriteExecute=true",
            "RestrictRealtime=true",
            "RestrictNamespaces=true",
            "SystemCallArchitectures=native",
            "UMask=0077",
        ]
        for line in required:
            with self.subTest(line=line):
                self.assertIn(line, content)

    def test_service_contains_no_secrets(self):
        content = self.read_text(self.service_path)
        self.assertNotIn("MITIGATE_AI_API_TOKEN", content)
        self.assertNotIn("TOKEN=", content)

    def test_env_example_placeholders_only_and_required_vars(self):
        content = self.read_text(self.env_example_path)
        # Ensure all required variables are present
        required_vars = [
            "MITIGATE_AI_HOST",
            "MITIGATE_AI_PORT",
            "MITIGATE_AI_DATA_ROOT",
            "MITIGATE_AI_REPOSITORY_ROOT",
            "MITIGATE_AI_DEFAULT_PROJECT_ID",
            "MITIGATE_AI_ENVIRONMENT_NAME",
            "MITIGATE_AI_AUTH_TOKEN_ENV",
            "MITIGATE_AI_API_TOKEN",
        ]
        for var in required_vars:
            with self.subTest(var=var):
                self.assertRegex(content, re.compile(rf"^{var}=.*", re.MULTILINE))
        # Placeholders only: require angle brackets for secret and config values
        lines = {
            k: v for k, v in (
                (m.group(1), m.group(2))
                for m in re.finditer(r"^(MITIGATE_AI_[A-Z0-9_]+)=(.*)$", content, re.MULTILINE)
            )
        }
        for var, val in lines.items():
            with self.subTest(var=var):
                self.assertIn("<", val)
                self.assertIn(">", val)
        # Ensure explicit secret placeholder marker is present for token
        self.assertRegex(
            content,
            re.compile(r"^MITIGATE_AI_API_TOKEN=<[A-Z0-9_\-]+>", re.MULTILINE),
        )

    def test_install_script_strict_and_root_and_preservation(self):
        content = self.read_text(self.install_script_path)
        # Strict mode
        self.assertIn("set -euo pipefail", content)
        # Requires root
        self.assertRegex(content, re.compile(r"EUID.*-ne 0"))
        # Literal path preservation check (compatibility contract)
        self.assertIn("if [[ -f /etc/mitigate-ai/runtime.env ]]", content)
        # Supports enable/start flags
        self.assertIn("--enable", content)
        self.assertIn("--start", content)
        self.assertIn("systemctl enable mitigate-ai-runtime", content)
        self.assertIn("systemctl start mitigate-ai-runtime", content)

    def test_uninstall_script_behavior_flags(self):
        content = self.read_text(self.uninstall_script_path)
        # Strict mode
        self.assertIn("set -euo pipefail", content)
        # Requires root
        self.assertRegex(content, re.compile(r"EUID.*-ne 0"))
        # Stop/disable commands referenced
        self.assertIn("systemctl stop mitigate-ai-runtime", content)
        self.assertIn("systemctl disable mitigate-ai-runtime", content)
        # Destructive environment removal only with explicit flag
        self.assertIn("--purge-env", content)
        # Default behavior preserves env file by messaging
        self.assertIn("Preserved ${ENV_REAL_PATH}", content)

    def test_healthcheck_localhost_timeouts_and_no_token_print(self):
        content = self.read_text(self.healthcheck_script_path)
        # Localhost-only
        self.assertIn("http://127.0.0.1", content)
        # Bounded timeouts
        self.assertIn("--connect-timeout", content)
        self.assertIn("--max-time", content)
        # Does not print tokens
        self.assertNotRegex(content, re.compile(r"echo\s+\$\{?TOKEN\}?"))
        self.assertNotRegex(content, re.compile(r"printf.*\$\{?TOKEN\}?"))

    def test_readme_contains_required_operational_procedures(self):
        content = self.read_text(self.readme_path)
        required_keywords = [
            "Prerequisites",
            "Generated Files",
            "Secure Environment File",
            "Token Generation Guidance",
            "Installation",
            "Validation",
            "Enable/Start",
            "Service Status",
            "Liveness and Readiness Checks",
            "journal",
            "Restart",
            "Stop",
            "Disable",
            "Uninstall",
            "Rollback",
            "Updating After Git Deployment",
            "Security Model",
            "Localhost-only",
            "Nginx",
            "Troubleshooting",
        ]
        for kw in required_keywords:
            with self.subTest(keyword=kw):
                self.assertIn(kw, content)


if __name__ == "__main__":
    unittest.main()
