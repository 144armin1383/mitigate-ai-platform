from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.execution.upstream_manager import UpstreamRuntimeManager


class RuntimeDoctor:
    """Read-only production/runtime health inspection for MITIGATE AI."""

    def __init__(
        self,
        *,
        repository_root: str | Path,
        runtime_root: str | Path,
        manifest_path: str | Path | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        self.manifest_path = Path(
            manifest_path or self.repository_root / "agent" / "config" / "external-runtimes.json"
        )

    @staticmethod
    def _run(command: Sequence[str], *, cwd: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )

    def _git(self, *args: str) -> str | None:
        try:
            result = self._run(["git", *args], cwd=self.repository_root)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def _service(self, name: str) -> str | None:
        try:
            result = self._run(["systemctl", "is-active", name], timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else (result.stdout.strip() or result.stderr.strip() or "inactive")

    def _worker_execstart(self) -> str | None:
        try:
            result = self._run(
                ["systemctl", "show", "mitigate-ai-worker.service", "-p", "ExecStart", "--value"],
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def npm_audit(self) -> Mapping[str, Any]:
        npm_root = self.runtime_root / "npm"
        package_json = npm_root / "package.json"
        if not package_json.is_file():
            return {"available": False, "reason": "isolated_npm_package_json_missing"}
        try:
            result = self._run(["npm", "audit", "--json"], cwd=npm_root, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"available": False, "reason": type(exc).__name__}
        try:
            payload = json.loads(result.stdout or "{}")
        except ValueError:
            return {
                "available": False,
                "reason": "npm_audit_invalid_json",
                "returncode": result.returncode,
            }
        vulnerabilities = (
            payload.get("metadata", {}).get("vulnerabilities", {})
            if isinstance(payload, dict)
            else {}
        )
        return {
            "available": True,
            "returncode": result.returncode,
            "vulnerabilities": vulnerabilities if isinstance(vulnerabilities, dict) else {},
        }

    def report(self, *, include_audit: bool = False) -> Mapping[str, Any]:
        manager = UpstreamRuntimeManager(self.manifest_path, runtime_root=self.runtime_root)
        compatibility = manager.compatibility_summary()
        branch = self._git("branch", "--show-current")
        head = self._git("rev-parse", "HEAD")
        origin_main = self._git("rev-parse", "origin/main")
        status = self._git("status", "--porcelain", "--untracked-files=all")
        worker = self._service("mitigate-ai-worker.service")
        runtime_api = self._service("mitigate-ai-runtime-api.service")
        execstart = self._worker_execstart()

        checks = {
            "repository_on_main": branch == "main",
            "repository_clean": status == "",
            "main_matches_origin": bool(head and origin_main and head == origin_main),
            "worker_active": worker == "active",
            "runtime_api_active": runtime_api == "active",
            "consolidated_worker_entrypoint": bool(
                execstart and "agent.runtime.runtime_consolidation_worker" in execstart
            ),
            "installed_versions_match_pins": bool(compatibility.get("all_installed_match")),
        }
        report: dict[str, Any] = {
            "healthy": all(checks.values()),
            "checks": checks,
            "repository": {
                "branch": branch,
                "head": head,
                "origin_main": origin_main,
                "clean": status == "",
            },
            "services": {
                "worker": worker,
                "runtime_api": runtime_api,
                "worker_execstart": execstart,
            },
            "external_runtimes": compatibility,
        }
        if include_audit:
            report["npm_audit"] = self.npm_audit()
        return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MITIGATE consolidated runtime doctor")
    parser.add_argument("--repository-root", default="/srv/mitigate/mitigate-ai-platform")
    parser.add_argument("--runtime-root", default="/srv/mitigate/external-runtimes")
    parser.add_argument("--manifest")
    parser.add_argument("--audit", action="store_true", help="include non-destructive npm audit summary")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    doctor = RuntimeDoctor(
        repository_root=args.repository_root,
        runtime_root=args.runtime_root,
        manifest_path=args.manifest,
    )
    report = doctor.report(include_audit=args.audit)
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if report.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
