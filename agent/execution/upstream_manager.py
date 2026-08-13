from __future__ import annotations

import json
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

    This class never upgrades production by itself. It reads the tested pins,
    can inspect locally installed versions, and exposes deterministic metadata
    for a separate compatibility-test/approval workflow.
    """

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)

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
        versions: dict[str, str | None] = {}
        for component in self.components():
            versions[component.name] = self._installed_version(component)
        return versions

    @staticmethod
    def _installed_version(component: UpstreamComponent) -> str | None:
        if component.ecosystem == "python":
            command = [
                "python",
                "-c",
                (
                    "import importlib.metadata as m; "
                    f"print(m.version({component.package!r}))"
                ),
            ]
        elif component.ecosystem == "npm":
            command = ["npm", "view", component.package, "version", "--offline"]
        else:
            return None

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

    def compatibility_summary(self) -> Mapping[str, Any]:
        installed = self.installed_versions()
        rows: list[dict[str, Any]] = []
        for component in self.components():
            current = installed.get(component.name)
            rows.append(
                {
                    "name": component.name,
                    "pinned_version": component.pinned_version,
                    "installed_version": current,
                    "matches_pin": current == component.pinned_version,
                    "required": component.required,
                    "role": component.role,
                }
            )
        return {"components": rows}


__all__ = ["UpstreamComponent", "UpstreamRuntimeManager"]
