from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class OpenClawWorkerCompatTests(unittest.TestCase):
    def test_wrapper_applies_cwd_without_forwarding_unsupported_flag(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspaces = root / "workspaces"
            workspace = workspaces / "m1-test"
            workspace.mkdir(parents=True)
            fake = root / "openclaw"
            fake.write_text(
                "#!/usr/bin/env bash\nprintf 'PWD=%s\\n' \"$PWD\"\nprintf 'ARGS=%s\\n' \"$*\"\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            env = {
                **os.environ,
                "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                "MITIGATE_WORKSPACE_ROOT": str(workspaces),
                "NODE_OPTIONS": "--jitless",
            }
            proc = subprocess.run(
                [
                    "bash",
                    str(wrapper),
                    "agent",
                    "exec",
                    "--message-file",
                    "-",
                    "--cwd",
                    str(workspace),
                    "--json",
                ],
                text=True,
                input="probe",
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn(f"PWD={workspace.resolve()}", proc.stdout)
            self.assertIn("ARGS=agent exec --message-file - --json", proc.stdout)
            self.assertNotIn("--cwd", proc.stdout)

    def test_wrapper_rejects_cwd_outside_disposable_root(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspaces = root / "workspaces"
            outside = root / "outside"
            workspaces.mkdir()
            outside.mkdir()
            fake = root / "openclaw"
            fake.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            proc = subprocess.run(
                ["bash", str(wrapper), "agent", "exec", "--cwd", str(outside)],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                    "MITIGATE_WORKSPACE_ROOT": str(workspaces),
                },
                check=False,
            )
            self.assertEqual(2, proc.returncode)
            self.assertIn("outside MITIGATE disposable workspace root", proc.stderr)

    def test_activation_uses_targeted_worker_override(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        text = (repo / "agent" / "maintenance" / "activate_openclaw_worker_compat.sh").read_text(encoding="utf-8")
        self.assertIn("MemoryDenyWriteExecute=false", text)
        self.assertIn('Environment="NODE_OPTIONS="', text)
        self.assertIn("MITIGATE_OPENCLAW_BINARY", text)


if __name__ == "__main__":
    unittest.main()
