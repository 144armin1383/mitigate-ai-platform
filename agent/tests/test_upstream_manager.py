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


if __name__ == "__main__":
    unittest.main()
