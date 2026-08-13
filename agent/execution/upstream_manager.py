from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class UpstreamComponent:
    name: str
    repository: str
    ecosystem: str
    package: str
    pinned_version: str
    role: str
    required: bool


class UpstreamRuntimeManager:
    """MITIGATE-owned metadata and compatibility boundary for external runtimes.

    Production upgrades are never performed here. Installed versions are read
    from the isolated runtime root, never from the network/registry, so the
    compatibility report describes what MITIGATE can actually execute.
    """

    def __init__(
        self,
        manifest_path: str | Path,
        *,
        runtime_root: str | Path | None = None,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.runtime_root = Path(
            runtime_root
            or os.environ.get("MITIGATE_EXTERNAL_RUNTIME_ROOT")
            or "/srv/mitigate/external-runtimes"
        ).expanduser()

    def manifest(self) -> Mapping[str, Any]:
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported_external_runtime_manifest")
        return data

    def components(self) -> tuple[UpstreamComponent, ...]:
        raw = self.manifest().get("components", [])
        if not isinstance(raw, list):
            raise ValueError("components_must_be_list")
        result: list[UpstreamComponent] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("component_must_be_object")
            result.append(
                UpstreamComponent(
                    name=str(item["name"]),
                    repository=str(item["repository"]),
                    ecosystem=str(item["ecosystem"]),
                    package=str(item["package"]),
                    pinned_version=str(item["pinned_version"]),
                    role=str(item["role"]),
                    required=bool(item.get("required", False)),
                )
            )
        return tuple(result)

    def installed_versions(self) -> Mapping[str, str | None]:
        return {
            component.name: self._installed_version(component)
            for component in self.components()
        }

    def _installed_version(self, component: UpstreamComponent) -> str | None:
        if component.ecosystem == "python":
            return self._python_package_version(component.package)
        if component.ecosystem == "npm":
            return self._npm_package_version(component.package)
        return None

    def _python_package_version(self, package: str) -> str | None:
        python = self.runtime_root / "venv" / "bin" / "python"
        if not python.is_file():
            return None
        command = [
            str(python),
            "-c",
            "import importlib.metadata as m,sys; print(m.version(sys.argv[1]))",
            package,
        ]
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _npm_package_version(self, package: str) -> str | None:
        package_json = self.runtime_root / "npm" / "node_modules" / package / "package.json"
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return self._npm_binary_version(package)
        value = data.get("version") if isinstance(data, dict) else None
        return str(value).strip() if value else None

    def _npm_binary_version(self, package: str) -> str | None:
        binary = self.runtime_root / "npm" / "node_modules" / ".bin" / package
        if not binary.is_file():
            return None
        try:
            result = subprocess.run(
                [str(binary), "--version"],
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9._-]+)?)", result.stdout)
        return match.group(1) if match else None

    def compatibility_summary(self) -> Mapping[str, Any]:
        installed = self.installed_versions()
        rows: list[dict[str, Any]] = []
        required_ok = True
        all_installed_match = True
        for component in self.components():
            current = installed.get(component.name)
            matches = current == component.pinned_version
            if component.required and not matches:
                required_ok = False
            if current is not None and not matches:
                all_installed_match = False
            rows.append(
                {
                    "name": component.name,
                    "pinned_version": component.pinned_version,
                    "installed_version": current,
                    "matches_pin": matches,
                    "required": component.required,
                    "role": component.role,
                }
            )
        return {
            "runtime_root": str(self.runtime_root),
            "required_ok": required_ok,
            "all_installed_match": all_installed_match,
            "components": rows,
        }


__all__ = ["UpstreamComponent", "UpstreamRuntimeManager"]
