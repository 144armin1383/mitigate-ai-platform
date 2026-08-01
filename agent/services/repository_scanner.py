from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class RepositoryFile:
    path: str
    extension: str
    size: int
    category: str


@dataclass
class RepositoryIndex:
    root: str
    total_files: int
    total_directories: int
    files: list[RepositoryFile]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "total_files": self.total_files,
            "total_directories": self.total_directories,
            "files": [asdict(item) for item in self.files],
        }


class RepositoryScanner:
    """Scan and classify files inside the MITIGATE repository."""

    ignored_directories = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        "vendor",
    }

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    def scan(self) -> RepositoryIndex:
        files: list[RepositoryFile] = []
        directories: set[Path] = set()

        for path in self.root.rglob("*"):
            relative_parts = path.relative_to(self.root).parts

            if any(part in self.ignored_directories for part in relative_parts):
                continue

            if path.is_dir():
                directories.add(path)
                continue

            if not path.is_file():
                continue

            relative_path = path.relative_to(self.root)

            files.append(
                RepositoryFile(
                    path=str(relative_path),
                    extension=path.suffix.lower(),
                    size=path.stat().st_size,
                    category=self._categorize(path),
                )
            )

        files.sort(key=lambda item: item.path)

        return RepositoryIndex(
            root=str(self.root),
            total_files=len(files),
            total_directories=len(directories),
            files=files,
        )

    @staticmethod
    def _categorize(path: Path) -> str:
        suffix = path.suffix.lower()

        if suffix == ".py":
            return "python"

        if suffix == ".php":
            return "php"

        if suffix in {".json", ".yaml", ".yml", ".toml", ".ini"}:
            return "configuration"

        if suffix in {".css", ".scss"}:
            return "stylesheet"

        if suffix in {".js", ".ts", ".tsx", ".jsx"}:
            return "javascript"

        if suffix in {".md", ".txt"}:
            return "documentation"

        if path.name in {"Dockerfile", "Makefile"}:
            return "infrastructure"

        return "other"
