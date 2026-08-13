from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.execution.openhands_adapter import OpenHandsRuntimeAdapter
from agent.execution.runtime_adapter import ExecutionRequest, RuntimeStatus


class OpenHandsRuntimeAdapterTests(unittest.TestCase):
    def _git_workspace(self) -> tempfile.TemporaryDirectory[str]:
        td = tempfile.TemporaryDirectory()
        subprocess.run(["git", "init", "-q", td.name], check=True)
        return td

    def _request(
        self,
        *,
        repository_root: str,
        workspace_root: str,
        allowed_paths: tuple[str, ...] = ("agent",),
        denied_paths: tuple[str, ...] = ("secrets",),
    ) -> ExecutionRequest:
        return ExecutionRequest(
            request_id="request-1",
            mission_id="mission-1",
            objective="Make a bounded code change",
            repository_root=repository_root,
            base_revision="",
            allowed_paths=allowed_paths,
            denied_paths=denied_paths,
            acceptance_criteria=("tests pass",),
            metadata={"workspace_root": workspace_root},
        )

    def test_refuses_canonical_repository_workspace(self) -> None:
        with self._git_workspace() as td:
            adapter = OpenHandsRuntimeAdapter(runner=lambda **_: None)
            result = adapter.execute(
                self._request(repository_root=td, workspace_root=td)
            )

        self.assertEqual(RuntimeStatus.blocked, result.status)
        self.assertEqual(
            "openhands_refuses_canonical_repository_workspace",
            result.reason,
        )

    def test_fake_runner_can_change_allowed_path_in_disposable_workspace(self) -> None:
        with self._git_workspace() as canonical, self._git_workspace() as workspace:
            def runner(*, request, workspace):
                del request
                target = Path(workspace) / "agent" / "example.py"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("VALUE = 1\n", encoding="utf-8")
                return SimpleNamespace(id="conversation-1")

            adapter = OpenHandsRuntimeAdapter(runner=runner)
            result = adapter.execute(
                self._request(
                    repository_root=canonical,
                    workspace_root=workspace,
                )
            )

        self.assertEqual(RuntimeStatus.succeeded, result.status)
        self.assertEqual(("agent/example.py",), result.evidence.changed_files)
        self.assertEqual("conversation-1", result.evidence.provider_run_id)

    def test_changes_outside_allowlist_are_blocked(self) -> None:
        with self._git_workspace() as canonical, self._git_workspace() as workspace:
            def runner(*, request, workspace):
                del request
                (Path(workspace) / "unexpected.txt").write_text("x\n", encoding="utf-8")
                return None

            adapter = OpenHandsRuntimeAdapter(runner=runner)
            result = adapter.execute(
                self._request(
                    repository_root=canonical,
                    workspace_root=workspace,
                )
            )

        self.assertEqual(RuntimeStatus.blocked, result.status)
        self.assertEqual(
            "runtime_changed_paths_outside_authorized_scope",
            result.reason,
        )
        self.assertIn(
            "scope_violation:unexpected.txt",
            result.evidence.diagnostics,
        )

    def test_denied_path_wins_even_if_allowlisted(self) -> None:
        with self._git_workspace() as canonical, self._git_workspace() as workspace:
            def runner(*, request, workspace):
                del request
                target = Path(workspace) / "agent" / "secrets" / "token.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("never expose\n", encoding="utf-8")
                return None

            adapter = OpenHandsRuntimeAdapter(runner=runner)
            request = self._request(
                repository_root=canonical,
                workspace_root=workspace,
                allowed_paths=("agent",),
                denied_paths=("agent/secrets",),
            )
            result = adapter.execute(request)

        self.assertEqual(RuntimeStatus.blocked, result.status)
        self.assertIn(
            "scope_violation:agent/secrets/token.txt",
            result.evidence.diagnostics,
        )

    def test_healthcheck_is_available_with_injected_runner(self) -> None:
        adapter = OpenHandsRuntimeAdapter(runner=lambda **_: None)
        health = adapter.healthcheck()
        self.assertTrue(health["available"])
        self.assertEqual("injected", health["mode"])


if __name__ == "__main__":
    unittest.main()
