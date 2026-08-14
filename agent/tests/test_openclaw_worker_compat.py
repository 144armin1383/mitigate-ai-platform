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

    @staticmethod
    def _stable_local_fake(path: Path) -> None:
        path.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$*\" == \"agent exec --help\" ]]; then\n"
            "  echo 'error: unknown command exec' >&2\n"
            "  exit 1\n"
            "fi\n"
            "if [[ \"$*\" == \"agent --help\" ]]; then\n"
            "  echo 'Usage: openclaw agent --message-file <path> --session-key <key> --local --json'\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"$*\" == \"--version\" ]]; then echo 'OpenClaw 2026.7.1-2'; exit 0; fi\n"
            "printf 'PWD=%s\\n' \"$PWD\"\n"
            "printf 'WORKSPACE=%s\\n' \"${OPENCLAW_WORKSPACE_DIR:-}\"\n"
            "printf 'MODE=%s\\n' \"${MITIGATE_OPENCLAW_EXEC_MODE:-}\"\n"
            "printf 'ARGS=%s\\n' \"$*\"\n"
            "prev=''\n"
            "for arg in \"$@\"; do\n"
            "  if [[ \"$prev\" == \"--message-file\" ]]; then\n"
            "    printf 'MESSAGE_FILE=%s\\n' \"$arg\"\n"
            "    printf 'MESSAGE='\n"
            "    cat \"$arg\"\n"
            "    printf '\\n'\n"
            "  fi\n"
            "  prev=\"$arg\"\n"
            "done\n",
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

    def test_wrapper_translates_stable_agent_local_into_disposable_workspace(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspaces = root / "workspaces"
            workspace = workspaces / "m-stable-test"
            workspace.mkdir(parents=True)
            fake = root / "openclaw"
            self._stable_local_fake(fake)
            proc = subprocess.run(
                [
                    "bash", str(wrapper), "agent", "exec",
                    "--message-file", "-", "--cwd", str(workspace), "--json",
                ],
                text=True,
                input="probe\nmultiline",
                capture_output=True,
                env={
                    **os.environ,
                    "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                    "MITIGATE_WORKSPACE_ROOT": str(workspaces),
                    "MITIGATE_OPENCLAW_CODING_DISABLED": "0",
                },
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn(f"PWD={workspace.resolve()}", proc.stdout)
            self.assertIn(f"WORKSPACE={workspace.resolve()}", proc.stdout)
            self.assertIn("MODE=agent-local-compat", proc.stdout)
            self.assertIn("ARGS=agent --session-key mitigate-m-stable-test", proc.stdout)
            self.assertIn("--local --message-file /tmp/mitigate-openclaw-prompt.", proc.stdout)
            self.assertIn("MESSAGE=probe\nmultiline", proc.stdout)
            self.assertNotIn("--message-file -", proc.stdout)
            self.assertNotIn("agent exec", proc.stdout)

    def test_wrapper_reports_stable_local_cli_healthy(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "openclaw"
            self._stable_local_fake(fake)
            proc = subprocess.run(
                ["bash", str(wrapper), "--version"],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                    "MITIGATE_OPENCLAW_CODING_DISABLED": "0",
                },
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("OpenClaw 2026.7.1-2", proc.stdout)

    def test_wrapper_marks_fully_unsupported_cli_unhealthy(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        wrapper = repo / "agent" / "execution" / "openclaw_compat_wrapper.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "openclaw"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$*\" == \"--version\" ]]; then echo 'OpenClaw legacy'; exit 0; fi\n"
                "echo 'Usage: openclaw agent --message <text>'\nexit 0\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            proc = subprocess.run(
                ["bash", str(wrapper), "--version"],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "MITIGATE_OPENCLAW_REAL_BINARY": str(fake),
                    "MITIGATE_OPENCLAW_CODING_DISABLED": "0",
                },
                check=False,
            )
            self.assertEqual(64, proc.returncode)
            self.assertIn("MITIGATE_OPENCLAW_CODING_CLI_UNSUPPORTED", proc.stderr)

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

    def test_activation_supports_native_and_stable_local_modes_fail_closed(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        text = (repo / "agent" / "maintenance" / "activate_openclaw_worker_compat.sh").read_text(encoding="utf-8")
        self.assertIn("OPENCLAW_AGENT_EXEC_SUPPORTED", text)
        self.assertIn("OPENCLAW_AGENT_LOCAL_COMPAT_SUPPORTED", text)
        self.assertIn('EXEC_MODE="agent-local-compat"', text)
        self.assertIn("MemoryDenyWriteExecute=false", text)
        self.assertIn("MITIGATE_OPENCLAW_CODING_DISABLED=0", text)
        self.assertIn("MemoryDenyWriteExecute=true", text)
        self.assertIn("MITIGATE_OPENCLAW_CODING_DISABLED=1", text)
        self.assertIn("MITIGATE_OPENCLAW_BINARY", text)


if __name__ == "__main__":
    unittest.main()
