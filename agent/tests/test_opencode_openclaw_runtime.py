from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.execution.openclaw_adapter import OpenClawRuntimeAdapter
from agent.execution.runtime_adapter import ExecutionRequest, RuntimeStatus
from agent.runtime.provider_secret_store import load_provider_secret, save_provider_secret


class OpenCodeOpenClawRuntimeTests(unittest.TestCase):
    def test_provider_secret_store_is_private_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"MITIGATE_AI_DATA_ROOT": td}, clear=False
        ):
            path = save_provider_secret(
                provider="opencode",
                api_key="sk-test-not-real",
                model="opencode/glm-5.2",
            )
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            self.assertEqual(0o700, path.parent.stat().st_mode & 0o777)
            loaded = load_provider_secret("opencode")
            self.assertEqual("opencode/glm-5.2", loaded["model"])
            self.assertEqual("sk-test-not-real", loaded["api_key"])

    def test_openclaw_agent_exec_uses_managed_opencode_key_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"MITIGATE_AI_DATA_ROOT": td}, clear=False
        ):
            root = Path(td)
            repo = root / "repo"
            workspace = root / "workspace"
            repo.mkdir()
            workspace.mkdir()
            save_provider_secret(
                provider="opencode",
                api_key="sk-runtime-not-real",
                model="opencode/glm-5.2",
            )

            request = ExecutionRequest(
                request_id="r1",
                mission_id="m1",
                objective="Create a harmless documentation file",
                repository_root=str(repo),
                base_revision="main",
                allowed_paths=("docs",),
                denied_paths=(".git",),
                timeout_seconds=60,
                metadata={"workspace_root": str(workspace)},
            )
            adapter = OpenClawRuntimeAdapter(binary="/usr/local/bin/openclaw")
            calls = []

            def fake_run(command, **kwargs):
                calls.append((list(command), kwargs))
                if command[:2] == ["git", "status"]:
                    return mock.Mock(returncode=0, stdout="", stderr="")
                payload = {
                    "ok": True,
                    "status": "ok",
                    "final": "done",
                    "provider": "opencode",
                    "model": "glm-5.2",
                    "sessionId": "session-1",
                }
                return mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

            with mock.patch.object(adapter, "_binary_path", return_value="/usr/local/bin/openclaw"), mock.patch(
                "agent.execution.openclaw_adapter.subprocess.run", side_effect=fake_run
            ):
                result = adapter.execute(request)

            self.assertEqual(RuntimeStatus.succeeded, result.status)
            command, kwargs = calls[0]
            self.assertIn("--model", command)
            self.assertIn("opencode/glm-5.2", command)
            self.assertIn("--auth-env-only", command)
            self.assertEqual("sk-runtime-not-real", kwargs["env"]["OPENCODE_API_KEY"])
            self.assertEqual("sk-runtime-not-real", kwargs["env"]["OPENCODE_ZEN_API_KEY"])
            self.assertEqual("opencode", result.evidence.provider_metadata["managed_llm_provider"])
            self.assertEqual("opencode/glm-5.2", result.evidence.provider_metadata["managed_llm_model"])


if __name__ == "__main__":
    unittest.main()
