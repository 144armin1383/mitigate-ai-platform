"""
Portable bootstrap utilities for repository structure validation.

This module performs safe, deterministic checks to ensure a checkout satisfies
portable recovery contract requirements without invoking network calls,
subprocesses, or external tooling. It is intentionally strict for structure
but permissive about configuration placeholders in a clean checkout.

Safety:
- No subprocess, exec, eval, or dynamic imports
- No network access
- No deployment execution

Python compatibility: 3.12+
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence

# Required repository directories and subdirectories for a structurally
# complete portable recovery environment.
REQUIRED_REPO_DIRS: Sequence[str] = (
    "agent",
    "agent/bootstrap",
    "agent/ai",
    "agent/runtime",
    "agent/api",
    "agent/orchestrator",
    "agent/autonomy",
    "agent/memory",
    "agent/operations",
    "agent/missions",
    "agent/tests",
    "agent/deploy",
)


def resolve_repo_root(candidate: Optional[Path | str] = None) -> Path:
    """Resolve the repository root path.

    Priority order:
    1) Explicit candidate path
    2) Environment override via MITIGATE_REPO_ROOT or REPO_ROOT (not read here to
       avoid ambient env dependency in core validation)
    3) Two levels up from this file (agent/bootstrap/ -> repo root)

    Returns:
        Path to repository root (absolute).
    """
    if candidate is not None:
        root = Path(candidate).expanduser().resolve()
        return root

    # Resolve from this file location to ensure caller working directory
    # does not affect correctness.
    here = Path(__file__).resolve()
    # agent/bootstrap/portable_bootstrap.py -> repo root is parents[2]
    # parents[0]=file's dir, [1]=agent/bootstrap, [2]=agent
    # Actually: __file__ in agent/bootstrap/, parents[0]=bootstrap, [1]=agent, [2]=repo_root
    # But because this file is in agent/bootstrap/, we need parents[2] to reach repo root.
    repo_root = here.parents[2]
    return repo_root


def required_repo_directories() -> List[str]:
    """Return the list of required repository directories (relative paths)."""
    return list(REQUIRED_REPO_DIRS)


def _list_missing_dirs(repo_root: Path, required: Iterable[str]) -> List[Path]:
    missing: List[Path] = []
    for rel in required:
        p = (repo_root / rel).resolve()
        if not p.exists() or not p.is_dir():
            missing.append(p)
    return missing


def validate_required_directories(repo_root: Optional[Path | str] = None) -> Path:
    """Validate that required directories exist.

    Args:
        repo_root: Optional explicit path. If not provided, resolved from file location.

    Returns:
        Resolved repository root as Path when validation succeeds.

    Raises:
        FileNotFoundError: if any required directory is missing.
        ValueError: if repo_root resolves to a non-directory path.
    """
    root = resolve_repo_root(repo_root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Repository root is not a directory: {root}")

    missing = _list_missing_dirs(root, REQUIRED_REPO_DIRS)
    if missing:
        # Provide a clear, safe error message without leaking secrets.
        missing_str = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(
            f"Required repository directories are missing: {missing_str}"
        )
    return root


def validate_repository_structure(repo_root: Optional[Path | str] = None) -> Path:
    """Alias for validate_required_directories for broader naming compatibility."""
    return validate_required_directories(repo_root)


def ensure_portable_repository(repo_root: Optional[Path | str] = None) -> Path:
    """Validate and return the repository root when structure is complete.

    This function is intended to be a single-call entrypoint from tests or
    bootstrap logic. It purposely does not validate external configuration
    values; placeholders are acceptable at this stage.
    """
    return validate_required_directories(repo_root)


__all__ = [
    "REQUIRED_REPO_DIRS",
    "resolve_repo_root",
    "required_repo_directories",
    "validate_required_directories",
    "validate_repository_structure",
    "ensure_portable_repository",
]
