from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.execution.upstream_manager import UpstreamRuntimeManager


class UpstreamRuntimeManagerTests(unittest.TestCase):
    def _manifest(self, data):
        td = tempfile.TemporaryDirectory()
        path = Path(td.name) / "manifest.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return td, path

    def test_loads_component_metadata(self) -> None:
        td, path = self._manifest(
            {
                "schema_version": 1,
                "components": [
                    {
                        "name": "openhands",
                        "repository": "OpenHands/software-agent-sdk",
                        "ecosystem": "python",
                        "package": "openhands-sdk",
                        "pinned_version": "1.24.0",
                        "role": "executor",
                        "required": False,
                    }
                ],
            }
        )
        self.addCleanup(td.cleanup)
        manager = UpstreamRuntimeManager(path)
        components = manager.components()
        self.assertEqual(1, len(components))
        self.assertEqual("openhands", components[0].name)
        self.assertFalse(components[0].required)

    def test_rejects_unknown_schema(self) -> None:
        td, path = self._manifest({"schema_version": 999, "components": []})
        self.addCleanup(td.cleanup)
        with self.assertRaises(ValueError):
            UpstreamRuntimeManager(path).manifest()

    def test_reads_npm_version_from_isolated_package_json_without_registry(self) -> None:
        td, path = self._manifest(
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
        )
        self.addCleanup(td.cleanup)
        runtime_root = Path(td.name) / "runtime"
        package_dir = runtime_root / "npm" / "node_modules" / "ruflo"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            json.dumps({"name": "ruflo", "version": "3.38.8"}),
            encoding="utf-8",
        )
        manager = UpstreamRuntimeManager(path, runtime_root=runtime_root)
        self.assertEqual("3.38.8", manager.installed_versions()["ruflo"])
        summary = manager.compatibility_summary()
        self.assertTrue(summary["all_installed_match"])
        self.assertEqual(str(runtime_root), summary["runtime_root"])

    def test_reports_local_npm_version_mismatch(self) -> None:
        td, path = self._manifest(
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
                        "required": True,
                    }
                ],
            }
        )
        self.addCleanup(td.cleanup)
        runtime_root = Path(td.name) / "runtime"
        package_dir = runtime_root / "npm" / "node_modules" / "openclaw"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            json.dumps({"name": "openclaw", "version": "2026.8.0"}),
            encoding="utf-8",
        )
        summary = UpstreamRuntimeManager(path, runtime_root=runtime_root).compatibility_summary()
        self.assertFalse(summary["required_ok"])
        self.assertFalse(summary["all_installed_match"])
        self.assertFalse(summary["components"][0]["matches_pin"])


if __name__ == "__main__":
    unittest.main()
