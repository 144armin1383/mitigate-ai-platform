from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


AGENT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = AGENT_ROOT / "manifest.json"


@dataclass
class BootstrapResult:
    created_directories: list[str] = field(default_factory=list)
    created_package_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    invalid_json_files: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.missing_files and not self.invalid_json_files


class Bootstrap:
    """Validate and repair the basic MITIGATE AI Agent structure."""

    def __init__(self, root: Path = AGENT_ROOT) -> None:
        self.root = root.resolve()
        self.manifest_path = self.root / "manifest.json"
        self.manifest = self._load_json(self.manifest_path)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"Required JSON file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError(f"JSON root must be an object: {path}")

        return data

    def run(self) -> BootstrapResult:
        result = BootstrapResult()

        for relative in self.manifest.get("required_directories", []):
            directory = self.root / relative

            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                result.created_directories.append(relative)

        for package in self.manifest.get("python_packages", []):
            package_directory = self.root / package
            package_directory.mkdir(parents=True, exist_ok=True)

            init_file = package_directory / "__init__.py"

            if not init_file.exists():
                init_file.touch()
                result.created_package_files.append(
                    str(init_file.relative_to(self.root))
                )

        for relative in self.manifest.get("required_files", []):
            path = self.root / relative

            if not path.is_file():
                result.missing_files.append(relative)
                continue

            if path.suffix == ".json":
                try:
                    self._load_json(path)
                except (OSError, json.JSONDecodeError, ValueError):
                    result.invalid_json_files.append(relative)

        return result


def run_bootstrap() -> BootstrapResult:
    return Bootstrap().run()


if __name__ == "__main__":
    bootstrap_result = run_bootstrap()

    print("MITIGATE AI Bootstrap")
    print(f"Created directories: {len(bootstrap_result.created_directories)}")
    print(f"Created package files: {len(bootstrap_result.created_package_files)}")
    print(f"Missing required files: {len(bootstrap_result.missing_files)}")
    print(f"Invalid JSON files: {len(bootstrap_result.invalid_json_files)}")

    if bootstrap_result.missing_files:
        print("\nMissing files:")
        for item in bootstrap_result.missing_files:
            print(f"  - {item}")

    if bootstrap_result.invalid_json_files:
        print("\nInvalid JSON files:")
        for item in bootstrap_result.invalid_json_files:
            print(f"  - {item}")

    if bootstrap_result.healthy:
        print("\nBootstrap status: HEALTHY")
    else:
        print("\nBootstrap status: ATTENTION REQUIRED")
        raise SystemExit(1)
