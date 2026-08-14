from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent.execution.openhands_adapter import OpenHandsRuntimeAdapter
from agent.execution.runtime_adapter import ExecutionRequest


class ManagedOpenHandsProcessError(RuntimeError):
    """Structured failure from the independently managed OpenHands process."""

    def __init__(
        self,
        code: str,
        *,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.code = str(code or "managed_openhands_execution_failed")[:200]
        self.returncode = returncode
        self.stdout = str(stdout or "")[-4000:]
        self.stderr = str(stderr or "")[-4000:]
        detail = self.stderr or self.stdout
        super().__init__(self.code + (":" + detail[:2500] if detail else ""))

    def evidence(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "returncode": self.returncode,
            "stdout_tail": self.stdout,
            "stderr_tail": self.stderr,
        }


class ExternalOpenHandsRunner:
    """Run OpenHands from its managed external venv in a disposable worktree."""

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
        # Preserve the venv-facing symlink path. Resolving bin/python to the
        # system interpreter prevents CPython from discovering pyvenv.cfg.
        expanded_python = Path(configured).expanduser()
        self.python_path = Path(os.path.abspath(str(expanded_python)))
        self.runner_script = (
            self.repository_root
            / "agent"
            / "execution"
            / "openhands_subprocess_runner.py"
        ).resolve()

    def available(self) -> bool:
        return (
            self.python_path.is_file()
            and os.access(self.python_path, os.X_OK)
            and self.runner_script.is_file()
        )

    @staticmethod
    def _safe_workspace(workspace: Path) -> Path:
        resolved = Path(workspace).expanduser().resolve()
        if not resolved.is_dir():
            raise ManagedOpenHandsProcessError("managed_openhands_workspace_unavailable")
        return resolved

    def _venv_root(self) -> Path:
        return self.python_path.parent.parent.absolute()

    def _managed_site_packages(self) -> tuple[Path, ...]:
        venv_root = self._venv_root()
        candidates = sorted(
            path.resolve()
            for path in (venv_root / "lib").glob("python*/site-packages")
            if path.is_dir()
        )
        return tuple(candidates)

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        for key in (
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTHONUSERBASE",
            "__PYVENV_LAUNCHER__",
        ):
            env.pop(key, None)

        venv_root = self._venv_root()
        site_packages = self._managed_site_packages()
        env["VIRTUAL_ENV"] = str(venv_root)
        existing_path = env.get("PATH", "")
        env["PATH"] = (
            str(self.python_path.parent)
            + (os.pathsep + existing_path if existing_path else "")
        )
        if site_packages:
            env["PYTHONPATH"] = os.pathsep.join(str(path) for path in site_packages)
        env["PYTHONNOUSERSITE"] = "1"
        env["OPENHANDS_SUPPRESS_BANNER"] = "1"
        env.setdefault("GIT_CONFIG_NOSYSTEM", "0")
        env["GIT_OPTIONAL_LOCKS"] = "0"
        return env

    def _preflight(
        self,
        *,
        workspace: Path,
        env: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        # `openhands` is a namespace package in the SDK distribution, so
        # find_spec("openhands").origin may legitimately be None. Validate the
        # concrete public SDK module instead; this mirrors the production import
        # used by openhands_subprocess_runner.py.
        probe = (
            "import importlib.util,json,site,sys;"
            "sdk=importlib.util.find_spec('openhands.sdk');"
            "print(json.dumps({"
            "'executable':sys.executable,"
            "'prefix':sys.prefix,"
            "'base_prefix':sys.base_prefix,"
            "'sitepackages':site.getsitepackages(),"
            "'openhands_sdk_spec':getattr(sdk,'origin',None),"
            "'openhands_sdk_available':sdk is not None"
            "}))"
        )
        try:
            proc = subprocess.run(
                [str(self.python_path), "-c", probe],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=max(10, min(timeout, 30)),
                check=False,
            )
        except OSError as exc:
            raise ManagedOpenHandsProcessError(
                "managed_openhands_process_start_failed",
                stderr=str(exc),
            ) from exc

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        payload: dict[str, Any] = {}
        if proc.returncode == 0:
            try:
                parsed = json.loads(stdout.strip().splitlines()[-1])
                if isinstance(parsed, dict):
                    payload = parsed
            except (ValueError, IndexError):
                payload = {}

        if proc.returncode != 0 or not payload.get("openhands_sdk_available"):
            detail = json.dumps(payload, sort_keys=True) if payload else stdout
            raise ManagedOpenHandsProcessError(
                "managed_openhands_runtime_incompatible",
                returncode=proc.returncode,
                stdout=detail,
                stderr=stderr,
            )
        return payload

    def __call__(self, *, request: ExecutionRequest, workspace: Path) -> Any:
        if not self.available():
            raise ManagedOpenHandsProcessError("managed_openhands_runtime_unavailable")

        workspace = self._safe_workspace(workspace)
        if workspace == self.repository_root:
            raise ManagedOpenHandsProcessError("managed_openhands_refuses_canonical_workspace")

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

        env = self._subprocess_env()
        env["MITIGATE_OPENHANDS_REQUEST_JSON"] = json.dumps(
            payload,
            separators=(",", ":"),
        )
        timeout = max(30, int(request.timeout_seconds))
        preflight = self._preflight(workspace=workspace, env=env, timeout=timeout)

        try:
            proc = subprocess.run(
                [
                    str(self.python_path),
                    str(self.runner_script),
                    "--workspace",
                    str(workspace),
                ],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("managed_openhands_timeout") from exc
        except OSError as exc:
            raise ManagedOpenHandsProcessError(
                "managed_openhands_process_start_failed",
                stderr=str(exc),
            ) from exc

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0:
            detail = (stderr or stdout).lower()
            if "insufficient_quota" in detail or "credit_balance_exhausted" in detail:
                code = "openhands_llm_quota_exhausted"
            elif "configured_llm_api_key_is_unavailable" in detail:
                code = "openhands_llm_credentials_unavailable"
            elif "modulenotfounderror" in detail or "importerror" in detail:
                code = "managed_openhands_runtime_incompatible"
            elif "permission denied" in detail:
                code = "managed_openhands_permission_denied"
            else:
                code = "managed_openhands_execution_failed"
            stderr_with_preflight = stderr
            if preflight:
                stderr_with_preflight += "\nMITIGATE_OPENHANDS_PREFLIGHT=" + json.dumps(
                    preflight,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            raise ManagedOpenHandsProcessError(
                code,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr_with_preflight,
            )

        run_id = None
        for line in reversed(stdout.splitlines()):
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

        return SimpleNamespace(
            id=run_id,
            provider_metadata={
                "working_directory": str(workspace),
                "python_executable": str(self.python_path),
                "virtual_env": str(self._venv_root()),
                "site_packages": [str(path) for path in self._managed_site_packages()],
                "runtime_preflight": preflight,
                "returncode": proc.returncode,
                "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-2000:],
            },
        )


__all__ = ["ExternalOpenHandsRunner", "ManagedOpenHandsProcessError"]
