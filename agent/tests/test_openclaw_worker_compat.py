from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class OpenClawWorkerCompatTests(unittest.TestCase):
    @staticmethod
    def _compatible_fake(path: Path) -> None:
        path.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$*\" == \"agent exec --help\" ]]; then\n"
            "  echo 'Usage: openclaw agent exec [message] --message-file <path> --cwd <dir> --json'\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"$*\" == \"--version\" ]]; then echo 'OpenClaw test'; exit 0; fi\n"
            "printf 'PWD=%s\\n' \"$PWD\"\n"
            "printf 'ARGS=%s\\n' \"$*\"\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    def test_wrapper_applies_cwd_for_compatible_agent_exec(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspaces = root / "workspaces"
            workspace = workspaces / "m1-test"
            workspace.mkdir(parents=True)
            fake = root / "openclaw"
            self._compatible_fake(fake)
            proc = subprocess.run(
                ["bash", str(wrapper), "agent", "exec", "--message-file", "-", "--cwd", str(workspace), "--json"],
                text=True,
                input="probe",
                capture_output=True,
                env={
                    **os.environ,
                    "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                    "MITIGATE_WORKSPACE_ROOT": str(workspaces),
                    "NODE_OPTIONS": "--jitless",
                },
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn(f"PWD={workspace.resolve()}", proc.stdout)
            self.assertIn("ARGS=agent exec --message-file - --json", proc.stdout)
            self.assertNotIn("--cwd", proc.stdout)

    def test_wrapper_marks_legacy_cli_unhealthy(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "openclaw"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$*\" == \"--version\" ]]; then echo 'OpenClaw 2026.7.1'; exit 0; fi\n"
                "echo 'Usage: openclaw agent [options]'\nexit 0\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            proc = subprocess.run(
                ["bash", str(wrapper), "--version"],
                text=True,
                capture_output=True,
                env={**os.environ, "MITIGATE_OPENCLAW_REAL_BINARY": str(fake)},
                check=False,
            )
            self.assertEqual(64, proc.returncode)
            self.assertIn("MITIGATE_OPENCLAW_AGENT_EXEC_UNSUPPORTED", proc.stderr)

    def test_wrapper_explicit_disabled_mode_never_launches_node(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "openclaw"
            fake.write_text("#!/usr/bin/env bash\necho SHOULD_NOT_RUN\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            proc = subprocess.run(
                ["bash", str(wrapper), "--version"],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                    "MITIGATE_OPENCLAW_CODING_DISABLED": "1",
                },
                check=False,
            )
            self.assertEqual(64, proc.returncode)
            self.assertNotIn("SHOULD_NOT_RUN", proc.stdout)
            self.assertIn("MITIGATE_OPENCLAW_CODING_DISABLED", proc.stderr)

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
            self._compatible_fake(fake)
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

    def test_activation_keeps_legacy_openclaw_fail_closed_and_hardened(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        text = (repo / "agent" / "maintenance" / "activate_openclaw_worker_compat.sh").read_text(encoding="utf-8")
        self.assertIn("OPENCLAW_AGENT_EXEC_SUPPORTED=no", text)
        self.assertIn("MemoryDenyWriteExecute=true", text)
        self.assertIn("MITIGATE_OPENCLAW_CODING_DISABLED=1", text)
        self.assertIn("MITIGATE_OPENCLAW_BINARY", text)


if __name__ == "__main__":
    unittest.main()
