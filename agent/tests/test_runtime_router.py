from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import (
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)
from agent.execution.runtime_router import RuntimeRouter
from agent.execution.workspace_manager import DisposableWorkspaceManager


class FakeAdapter:
    name = "fake"

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            coding=True,
            terminal=True,
            file_editing=True,
            tests=True,
            isolated_workspace=True,
        )

    def healthcheck(self):
        return {"available": True}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        workspace = Path(str(request.metadata["workspace_root"]))
        target = workspace / "agent" / "generated.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
        )

    def cancel(self, provider_run_id: str) -> bool:
        del provider_run_id
        return False


class RuntimeRouterTests(unittest.TestCase):
    def _repository(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "MITIGATE Tests"], cwd=root, check=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True)
        return td, root

    def test_external_execution_uses_disposable_worktree_and_keeps_canonical_clean(self) -> None:
        td, root = self._repository()
        with td:
            with tempfile.TemporaryDirectory() as workspaces:
                manager = DisposableWorkspaceManager(root, workspace_parent=workspaces)
                router = RuntimeRouter(RuntimeRegistry([FakeAdapter()]), manager)
                base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
                request = ExecutionRequest(
                    request_id="r1",
                    mission_id="m1",
                    objective="Generate one allowed file",
                    repository_root=str(root),
                    base_revision=base,
                    allowed_paths=("agent",),
                )

                result = router.execute(
                    request,
                    require=RuntimeCapabilities(coding=True, isolated_workspace=True),
                    preferred=("fake",),
                )

                self.assertEqual(RuntimeStatus.succeeded, result.status)
                self.assertTrue(manager.canonical_is_clean())
                self.assertFalse((root / "agent" / "generated.py").exists())
                self.assertEqual([], list(Path(workspaces).iterdir()))

    def test_dirty_canonical_repository_blocks_before_provider_execution(self) -> None:
        td, root = self._repository()
        with td:
            (root / "dirty.txt").write_text("x\n", encoding="utf-8")
            manager = DisposableWorkspaceManager(root)
            router = RuntimeRouter(RuntimeRegistry([FakeAdapter()]), manager)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            request = ExecutionRequest(
                request_id="r2",
                mission_id="m2",
                objective="Should not run",
                repository_root=str(root),
                base_revision=base,
            )

            result = router.execute(
                request,
                require=RuntimeCapabilities(coding=True),
            )

            self.assertEqual(RuntimeStatus.blocked, result.status)
            self.assertEqual("canonical_repository_not_clean", result.reason)

    def test_unavailable_runtime_does_not_create_workspace(self) -> None:
        td, root = self._repository()
        with td:
            with tempfile.TemporaryDirectory() as workspaces:
                manager = DisposableWorkspaceManager(root, workspace_parent=workspaces)
                router = RuntimeRouter(RuntimeRegistry(), manager)
                base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
                request = ExecutionRequest(
                    request_id="r3",
                    mission_id="m3",
                    objective="No provider",
                    repository_root=str(root),
                    base_revision=base,
                )

                result = router.execute(
                    request,
                    require=RuntimeCapabilities(coding=True),
                )

                self.assertEqual(RuntimeStatus.unavailable, result.status)
                self.assertEqual([], list(Path(workspaces).iterdir()))


if __name__ == "__main__":
    unittest.main()
