from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.web.external_runtime_probe import (
    probe_external_runtimes,
)


class ExternalRuntimeProbeTests(unittest.TestCase):
    def test_probe_reports_all_three_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            openhands_python = root / "venv" / "bin" / "python"
            openclaw = (
                root
                / "npm"
                / "node_modules"
                / ".bin"
                / "openclaw"
            )
            ruflo = (
                root
                / "npm"
                / "node_modules"
                / ".bin"
                / "ruflo"
            )

            for path in (
                openhands_python,
                openclaw,
                ruflo,
            ):
                path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                path.touch()

            responses = [
                {
                    "available": True,
                    "returncode": 0,
                    "output": "1.42.1",
                },
                {
                    "available": True,
                    "returncode": 0,
                    "output": "OpenClaw 2026.7.1-2",
                },
                {
                    "available": True,
                    "returncode": 0,
                    "output": "ruflo v3.38.9",
                },
            ]

            with mock.patch.dict(
                os.environ,
                {
                    "MITIGATE_EXTERNAL_RUNTIME_ROOT": str(root),
                    "OPENAI_API_KEY": "configured",
                },
                clear=False,
            ):
                with mock.patch(
                    "agent.web.external_runtime_probe._run",
                    side_effect=responses,
                ):
                    result = probe_external_runtimes()

            self.assertTrue(result["ok"])
            self.assertEqual(
                ["openhands", "openclaw", "ruflo"],
                [
                    item["provider"]
                    for item in result["runtimes"]
                ],
            )
            self.assertTrue(
                result["runtimes"][0]["llm_configured"]
            )


if __name__ == "__main__":
    unittest.main()
