from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent.execution.openhands_adapter import OpenHandsRuntimeAdapter
from agent.execution.runtime_adapter import ExecutionRequest


class ExternalOpenHandsRunner:
    """Run OpenHands from the managed external runtime environment.

    The MITIGATE worker intentionally has a small Python environment. OpenHands is
    installed and upgraded independently under the external-runtime root, so coding
    missions must invoke that managed interpreter instead of assuming the SDK is
    installed in the worker venv.
    """

    def __init__(
        self,
        *,
        repository_root: str | Path,
        python_path: str | Path | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        configured = str(
            python_path
            or os.environ.get("MITIGATE_OPENHANDS_PYTHON")
            or "/srv/mitigate/external-runtimes/venv/bin/python"
        ).strip()
        self.python_path = Path(configured).expanduser().resolve()

    def available(self) -> bool:
        return self.python_path.is_file() and os.access(self.python_path, os.X_OK)

    def __call__(self, *, request: ExecutionRequest, workspace: Path) -> Any:
        if not self.available():
            raise RuntimeError("managed_openhands_python_unavailable")

        prompt = OpenHandsRuntimeAdapter._prompt(request)
        payload = {
            "model": str(
                request.metadata.get("model")
                or os.environ.get("MITIGATE_OPENHANDS_MODEL")
                or "gpt-5.5"
            ),
            "api_key_env": str(
                request.metadata.get("api_key_env")
                or "OPENAI_API_KEY"
            ),
            "prompt": prompt,
        }

        env = dict(os.environ)
        env["MITIGATE_OPENHANDS_REQUEST_JSON"] = json.dumps(
            payload,
            separators=(",", ":"),
        )

        proc = subprocess.run(
            [
                str(self.python_path),
                "-m",
                "agent.execution.openhands_subprocess_runner",
                "--workspace",
                str(workspace),
            ],
            cwd=self.repository_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=max(30, int(request.timeout_seconds)),
            check=False,
        )

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-3000:]
            lowered = detail.lower()
            if "insufficient_quota" in lowered or "credit_balance_exhausted" in lowered:
                raise RuntimeError("openhands_llm_quota_exhausted")
            if "configured_llm_api_key_is_unavailable" in lowered:
                raise RuntimeError("openhands_llm_credentials_unavailable")
            raise RuntimeError(
                "managed_openhands_execution_failed:" + detail[:2500]
            )

        run_id = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                candidate = value.get("run_id")
                if candidate is not None:
                    run_id = str(candidate)
                    break

        return SimpleNamespace(id=run_id)


__all__ = ["ExternalOpenHandsRunner"]
