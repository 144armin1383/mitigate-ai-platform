from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent.execution.external_openhands_runner import ExternalOpenHandsRunner


class OpenHandsTimeoutCleanupTests(unittest.TestCase):
    def test_timeout_kills_process_tree_and_workspace_processes(self) -> None:
        if not Path("/proc").is_dir():
            self.skipTest("requires procfs")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            workspace = root / "workspace"
            runner_script = repo / "agent" / "execution" / "openhands_subprocess_runner.py"
            runner_script.parent.mkdir(parents=True)
            workspace.mkdir()

            runner_script.write_text(
                "import subprocess,sys,time\n"
                "workspace=sys.argv[sys.argv.index('--workspace')+1]\n"
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)',workspace])\n"
                "time.sleep(60)\n",
                encoding="utf-8",
            )

            runner = ExternalOpenHandsRunner(
                repository_root=repo,
                python_path=sys.executable,
            )

            with self.assertRaisesRegex(TimeoutError, "managed_openhands_timeout"):
                runner._run_agent(
                    workspace=workspace,
                    env=dict(os.environ),
                    timeout=1,
                )

            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and runner._workspace_processes(workspace):
                time.sleep(0.1)

            self.assertEqual([], runner._workspace_processes(workspace))


if __name__ == "__main__":
    unittest.main()
