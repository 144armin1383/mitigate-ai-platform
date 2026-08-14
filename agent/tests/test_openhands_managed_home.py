from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.execution.external_openhands_runner import ExternalOpenHandsRunner


class OpenHandsManagedHomeTests(unittest.TestCase):
    def test_subprocess_uses_managed_writable_home(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            runner_script = repo / "agent" / "execution" / "openhands_subprocess_runner.py"
            venv = root / "venv"
            python_path = venv / "bin" / "python"
            site_packages = venv / "lib" / "python3.12" / "site-packages"
            state_root = root / "managed-home"

            runner_script.parent.mkdir(parents=True)
            runner_script.write_text("# runner\n", encoding="utf-8")
            python_path.parent.mkdir(parents=True)
            python_path.write_text("#!/bin/sh\n", encoding="utf-8")
            python_path.chmod(0o700)
            site_packages.mkdir(parents=True)

            with patch.dict(
                os.environ,
                {
                    "MITIGATE_OPENHANDS_HOME": str(state_root),
                    "HOME": "/home/ubuntu",
                },
                clear=False,
            ):
                runner = ExternalOpenHandsRunner(
                    repository_root=repo,
                    python_path=python_path,
                )
                env = runner._subprocess_env()

            self.assertEqual(str(state_root), env["HOME"])
            self.assertEqual(str(state_root / ".config"), env["XDG_CONFIG_HOME"])
            self.assertEqual(str(state_root / ".cache"), env["XDG_CACHE_HOME"])
            self.assertEqual(str(state_root / ".local" / "share"), env["XDG_DATA_HOME"])
            self.assertEqual(str(state_root / ".openhands"), env["OPENHANDS_HOME"])
            self.assertTrue((state_root / ".openhands").is_dir())
            self.assertTrue((state_root / ".config").is_dir())


if __name__ == "__main__":
    unittest.main()
