from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


def _run(command: list[str], *, timeout: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False,
            "error": type(exc).__name__,
        }

    output = (result.stdout or result.stderr or "").strip()

    return {
        "available": result.returncode == 0,
        "returncode": result.returncode,
        "output": output[:1000],
    }


def _pypi_latest(package: str) -> tuple[str | None, str | None]:
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{package}/json",
            timeout=12,
        ) as response:
            payload = json.load(response)
        version = str(payload.get("info", {}).get("version") or "").strip()
        return (version or None, None)
    except Exception as exc:
        return (None, type(exc).__name__)


def _npm_latest(package: str) -> tuple[str | None, str | None]:
    probe = _run(["npm", "view", package, "version"], timeout=15)
    if not probe.get("available"):
        return (None, str(probe.get("error") or "npm_lookup_failed"))
    version = str(probe.get("output") or "").splitlines()[-1].strip()
    return (version or None, None)


def _with_update_status(
    data: dict[str, Any],
    *,
    latest: str | None,
    error: str | None,
) -> dict[str, Any]:
    current = str(data.get("version") or "").strip()
    data["latest_version"] = latest
    data["update_check_error"] = error
    data["update_available"] = bool(latest and current and latest != current)
    data["up_to_date"] = bool(latest and current and latest == current)
    return data


def _openhands(
    runtime_root: Path,
    *,
    check_updates: bool,
) -> dict[str, Any]:
    python = runtime_root / "venv" / "bin" / "python"

    if not python.is_file():
        data = {
            "name": "OpenHands",
            "provider": "openhands",
            "available": False,
            "reason": "python_runtime_missing",
        }
        if check_updates:
            latest, error = _pypi_latest("openhands-sdk")
            return _with_update_status(data, latest=latest, error=error)
        return data

    probe = _run(
        [
            str(python),
            "-c",
            (
                "import importlib.metadata as m; "
                "import openhands.sdk; "
                "print(m.version('openhands-sdk'))"
            ),
        ]
    )

    data: dict[str, Any] = {
        "name": "OpenHands",
        "provider": "openhands",
        "available": bool(probe.get("available")),
        "version": (
            probe.get("output")
            if probe.get("available")
            else None
        ),
        "mode": "sdk",
        "llm_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "error": probe.get("error"),
    }
    if check_updates:
        latest, error = _pypi_latest("openhands-sdk")
        _with_update_status(data, latest=latest, error=error)
    return data


def _openclaw(
    runtime_root: Path,
    *,
    deep: bool,
    check_updates: bool,
) -> dict[str, Any]:
    binary = (
        runtime_root
        / "npm"
        / "node_modules"
        / ".bin"
        / "openclaw"
    )

    if not binary.is_file():
        data = {
            "name": "OpenClaw",
            "provider": "openclaw",
            "available": False,
            "reason": "binary_missing",
        }
        if check_updates:
            latest, error = _npm_latest("openclaw")
            return _with_update_status(data, latest=latest, error=error)
        return data

    probe = _run([str(binary), "--version"])
    raw_version = str(probe.get("output") or "")
    match = re.search(r"OpenClaw\s+([^\s]+)", raw_version)
    current_version = match.group(1) if match else raw_version.strip()

    data: dict[str, Any] = {
        "name": "OpenClaw",
        "provider": "openclaw",
        "available": bool(probe.get("available")),
        "version": current_version or None,
        "version_raw": raw_version or None,
        "mode": "cli",
    }

    if check_updates:
        latest, error = _npm_latest("openclaw")
        _with_update_status(data, latest=latest, error=error)

    if deep and data["available"]:
        functional = _run(
            [
                str(binary),
                "mcp",
                "status",
                "--json",
            ],
            timeout=60,
        )

        data["functional_probe"] = (
            "ok"
            if functional.get("available")
            else "failed"
        )

        if functional.get("output"):
            try:
                data["functional_result"] = json.loads(
                    str(functional["output"])
                )
            except ValueError:
                data["functional_result"] = str(
                    functional["output"]
                )[:500]

    return data


def _ruflo(
    runtime_root: Path,
    *,
    deep: bool,
    check_updates: bool,
) -> dict[str, Any]:
    binary = (
        runtime_root
        / "npm"
        / "node_modules"
        / ".bin"
        / "ruflo"
    )

    if not binary.is_file():
        data = {
            "name": "Ruflo",
            "provider": "ruflo",
            "available": False,
            "reason": "binary_missing",
        }
        if check_updates:
            latest, error = _npm_latest("ruflo")
            return _with_update_status(data, latest=latest, error=error)
        return data

    probe = _run([str(binary), "--version"])
    raw_version = str(probe.get("output") or "")
    current_version = re.sub(r"^ruflo\s+v", "", raw_version).strip()

    data: dict[str, Any] = {
        "name": "Ruflo",
        "provider": "ruflo",
        "available": bool(probe.get("available")),
        "version": current_version or None,
        "version_raw": raw_version or None,
        "mode": "cli",
    }

    if check_updates:
        latest, error = _npm_latest("ruflo")
        _with_update_status(data, latest=latest, error=error)

    if deep and data["available"]:
        functional = _run(
            [
                str(binary),
                "doctor",
                "--json",
            ],
            timeout=60,
        )

        data["functional_probe"] = (
            "ok"
            if functional.get("available")
            else "failed"
        )

        if functional.get("output"):
            try:
                data["functional_result"] = json.loads(
                    str(functional["output"])
                )
            except ValueError:
                data["functional_result"] = str(
                    functional["output"]
                )[:500]

    return data


def probe_external_runtimes(
    *,
    deep: bool = False,
    check_updates: bool = True,
) -> dict[str, Any]:
    runtime_root = Path(
        os.environ.get(
            "MITIGATE_EXTERNAL_RUNTIME_ROOT",
            "/srv/mitigate/external-runtimes",
        )
    ).resolve()

    runtimes = [
        _openhands(runtime_root, check_updates=check_updates),
        _openclaw(
            runtime_root,
            deep=deep,
            check_updates=check_updates,
        ),
        _ruflo(
            runtime_root,
            deep=deep,
            check_updates=check_updates,
        ),
    ]

    return {
        "ok": all(
            bool(runtime.get("available"))
            for runtime in runtimes
        ),
        "runtime_root": str(runtime_root),
        "deep": deep,
        "check_updates": check_updates,
        "updates_available": sum(
            1 for runtime in runtimes if runtime.get("update_available")
        ),
        "runtimes": runtimes,
    }


__all__ = ["probe_external_runtimes"]
