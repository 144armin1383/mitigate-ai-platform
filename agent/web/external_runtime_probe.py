from __future__ import annotations

import json
import os
import subprocess
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


def _openhands(runtime_root: Path) -> dict[str, Any]:
    python = runtime_root / "venv" / "bin" / "python"

    if not python.is_file():
        return {
            "name": "OpenHands",
            "provider": "openhands",
            "available": False,
            "reason": "python_runtime_missing",
        }

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

    return {
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


def _openclaw(
    runtime_root: Path,
    *,
    deep: bool,
) -> dict[str, Any]:
    binary = (
        runtime_root
        / "npm"
        / "node_modules"
        / ".bin"
        / "openclaw"
    )

    if not binary.is_file():
        return {
            "name": "OpenClaw",
            "provider": "openclaw",
            "available": False,
            "reason": "binary_missing",
        }

    probe = _run([str(binary), "--version"])

    data: dict[str, Any] = {
        "name": "OpenClaw",
        "provider": "openclaw",
        "available": bool(probe.get("available")),
        "version": probe.get("output"),
        "mode": "cli",
    }

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
) -> dict[str, Any]:
    binary = (
        runtime_root
        / "npm"
        / "node_modules"
        / ".bin"
        / "ruflo"
    )

    if not binary.is_file():
        return {
            "name": "Ruflo",
            "provider": "ruflo",
            "available": False,
            "reason": "binary_missing",
        }

    probe = _run([str(binary), "--version"])

    data: dict[str, Any] = {
        "name": "Ruflo",
        "provider": "ruflo",
        "available": bool(probe.get("available")),
        "version": probe.get("output"),
        "mode": "cli",
    }

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
) -> dict[str, Any]:
    runtime_root = Path(
        os.environ.get(
            "MITIGATE_EXTERNAL_RUNTIME_ROOT",
            "/srv/mitigate/external-runtimes",
        )
    ).resolve()

    runtimes = [
        _openhands(runtime_root),
        _openclaw(runtime_root, deep=deep),
        _ruflo(runtime_root, deep=deep),
    ]

    return {
        "ok": all(
            bool(runtime.get("available"))
            for runtime in runtimes
        ),
        "runtime_root": str(runtime_root),
        "deep": deep,
        "runtimes": runtimes,
    }


__all__ = ["probe_external_runtimes"]
