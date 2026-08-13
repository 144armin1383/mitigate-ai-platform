from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.operations.runtime_doctor import RuntimeDoctor


class _Doctor(RuntimeDoctor):
    def _git(self, *args: str):
        values = {
            ("branch", "--show-current"): "main",
            ("rev-parse", "HEAD"): "abc",
            ("rev-parse", "origin/main"): "abc",
            ("status", "--porcelain", "--untracked-files=all"): "",
        }
        return values.get(tuple(args))

    def _service(self, name: str):
        return "active"

    def _worker_execstart(self):
        return "python -m agent.runtime.runtime_consolidation_worker --queue-path queue.json"


class RuntimeDoctorTests(unittest.TestCase):
    def test_healthy_when_repository_services_and_pins_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            runtime = Path(td) / "runtime"
            (root / "agent" / "config").mkdir(parents=True)
            package_dir = runtime / "npm" / "node_modules" / "ruflo"
            package_dir.mkdir(parents=True)
            (package_dir / "package.json").write_text(
                json.dumps({"name": "ruflo", "version": "3.38.8"}),
                encoding="utf-8",
            )
            (root / "agent" / "config" / "external-runtimes.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "components": [
                            {
                                "name": "ruflo",
                                "repository": "ruvnet/ruflo",
                                "ecosystem": "npm",
                                "package": "ruflo",
                                "pinned_version": "3.38.8",
                                "role": "benchmark",
                                "required": False,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = _Doctor(repository_root=root, runtime_root=runtime).report()
            self.assertTrue(report["healthy"])
            self.assertTrue(report["checks"]["installed_versions_match_pins"])

    def test_version_drift_fails_health(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            runtime = Path(td) / "runtime"
            (root / "agent" / "config").mkdir(parents=True)
            package_dir = runtime / "npm" / "node_modules" / "openclaw"
            package_dir.mkdir(parents=True)
            (package_dir / "package.json").write_text(
                json.dumps({"name": "openclaw", "version": "2026.8.0"}),
                encoding="utf-8",
            )
            (root / "agent" / "config" / "external-runtimes.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "components": [
                            {
                                "name": "openclaw",
                                "repository": "openclaw/openclaw",
                                "ecosystem": "npm",
                                "package": "openclaw",
                                "pinned_version": "2026.7.1",
                                "role": "tools",
                                "required": False,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = _Doctor(repository_root=root, runtime_root=runtime).report()
            self.assertFalse(report["healthy"])
            self.assertFalse(report["checks"]["installed_versions_match_pins"])


if __name__ == "__main__":
    unittest.main()
