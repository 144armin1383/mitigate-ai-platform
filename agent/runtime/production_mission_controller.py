"""
Production Mission Controller

Purpose
- Provide robust, deterministic resolution of package and project paths.
- Enable safe loading of repository resources (e.g., docs/architecture/*.json)
  without depending on process working directory or external environment.

Design
- Uses importlib to locate the base package directory reliably.
- Walks parent directories to locate the repository root by presence of
  canonical folders ("docs" and the base package directory).
- Exposes a simple controller that can resolve and load architecture JSON files.

This module is intentionally self-contained and free of side effects and
external dependencies to ensure repeatable behavior in production and test
contexts.

Python: 3.12+
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import importlib
import json

__all__ = [
    "ProductionMissionController",
    "find_project_root",
    "resolve_architecture_path",
]


def _module_dir(module_name: str) -> Path:
    """Return the absolute directory of a loaded module or package.

    Resolution order (deterministic):
    1) If module has __file__, use its parent directory.
    2) If module is a namespace package, use the first entry in __path__.

    Raises:
        ImportError: if the module cannot be imported.
        RuntimeError: if the module path cannot be determined.
    """
    mod = importlib.import_module(module_name)

    file_attr = getattr(mod, "__file__", None)
    if file_attr:
        # __file__ typically points to __init__.py for packages.
        return Path(file_attr).resolve().parent

    # Handle namespace packages where __file__ may be absent.
    path_attr = getattr(mod, "__path__", None)
    if path_attr:
        # Select the first path entry deterministically.
        for entry in path_attr:  # pragma: no branch - deterministic first entry
            return Path(entry).resolve()

    raise RuntimeError(f"Unable to determine directory for module: {module_name}")


def find_project_root(start: Optional[Path] = None, base_package: str = "agent") -> Path:
    """Locate the repository root directory.

    Strategy:
    - Start from the provided path or the base package directory.
    - Walk upwards looking for a directory that contains both:
        * the base package directory (e.g., 'agent')
        * the 'docs' directory
    - If not found, fall back to the parent of the base package directory.

    The search is deterministic and bounded by the filesystem root.
    """
    base_dir = start or _module_dir(base_package)
    # Prefer a root containing both the package and docs folder.
    for parent in (base_dir,) + tuple(base_dir.parents):
        if (parent / base_package).is_dir() and (parent / "docs").is_dir():
            return parent

    # Fallback: parent of the base package directory (common monorepo layout).
    return base_dir.parent


def resolve_architecture_path(name: str, project_root: Optional[Path] = None) -> Path:
    """Return absolute path to an architecture JSON by simple convention.

    Convention: <project_root>/docs/architecture/<name>.json
    """
    root = project_root or find_project_root()
    return (root / "docs" / "architecture" / f"{name}.json").resolve()


def _load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON file from the given absolute path.

    Raises:
        FileNotFoundError: if path does not exist.
        json.JSONDecodeError: if the content is not valid JSON.
    """
    if not path.is_file():  # Defensive check with clear error
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class ProductionMissionController:
    """Production-grade controller for mission runtime path resolution.

    Provides deterministic accessors for:
    - base package directory
    - repository root directory
    - architecture JSON path and loader
    """

    def __init__(self, base_package: str = "agent") -> None:
        if not base_package or not isinstance(base_package, str):
            raise ValueError("base_package must be a non-empty string")
        self._base_package = base_package
        self._package_path = _module_dir(base_package)

    @property
    def base_package(self) -> str:
        return self._base_package

    def package_path(self) -> Path:
        """Absolute directory of the base package (e.g., /repo/agent)."""
        return self._package_path

    def project_root(self) -> Path:
        """Absolute repository root directory.

        Determined by scanning upwards from the base package directory.
        """
        return find_project_root(self._package_path, self._base_package)

    def architecture_json_path(self, name: str) -> Path:
        """Absolute path to the named architecture JSON file."""
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        return resolve_architecture_path(name, self.project_root())

    def load_architecture_json(self, name: str) -> Dict[str, Any]:
        """Load and return the parsed architecture JSON content."""
        return _load_json(self.architecture_json_path(name))
