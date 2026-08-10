from __future__ import annotations

import unittest
from pathlib import Path


class RuntimeWorkerSystemdDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.service = (
            cls.repo_root
            / "agent"
            / "deploy"
            / "systemd"
            / "mitigate-ai-worker.service"
        )
        cls.content = cls.service.read_text(encoding="utf-8")

    def test_worker_service_exists(self):
        self.assertTrue(self.service.is_file())

    def test_worker_uses_background_worker_entrypoint(self):
        self.assertIn(
            "-m agent.runtime.background_worker",
            self.content,
        )

    def test_worker_has_production_queue_path(self):
        self.assertIn(
            "--queue-path /srv/mitigate/data/runtime/missions.json",
            self.content,
        )

    def test_worker_has_heartbeat_path(self):
        self.assertIn(
            "--heartbeat-path /srv/mitigate/data/runtime/worker.heartbeat",
            self.content,
        )

    def test_worker_restarts_on_failure(self):
        self.assertIn("Restart=on-failure", self.content)

    def test_worker_uses_sigterm(self):
        self.assertIn("KillSignal=SIGTERM", self.content)

    def test_worker_has_restricted_write_paths(self):
        self.assertIn(
            "ReadWritePaths=/srv/mitigate/data /var/log/mitigate-ai",
            self.content,
        )

    def test_worker_uses_runtime_environment(self):
        self.assertIn(
            "EnvironmentFile=/etc/mitigate-ai/runtime.env",
            self.content,
        )


if __name__ == "__main__":
    unittest.main()
