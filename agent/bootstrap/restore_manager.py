from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

__all__ = [
    "PortableRecoverySummary",
    "RestoreResult",
    "RestoreManager",
]


# NOTE:
# - This module intentionally avoids postponed evaluation of annotations.
# - All type annotations are concrete runtime objects at class creation time,
#   so dataclasses does not need to resolve the module via sys.modules.
# - This makes the module safe to execute via importlib spec loader without
#   pre-inserting the module into sys.modules, addressing portability issues
#   in strict validation environments.


@dataclass(frozen=True)
class PortableRecoverySummary:
    """Immutable portable recovery summary for reporting purposes.

    Fields are deliberately concrete types (no string annotations) to avoid
    dataclass/typing resolution that would otherwise require sys.modules entry.
    """

    source: Path
    project_id: Optional[str]
    project_name: Optional[str]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RestoreResult:
    """Immutable result object for restore operations."""

    ok: bool
    summary: PortableRecoverySummary
    details: Tuple[str, ...] = ()


class RestoreManager:
    """Portable recovery restore manager.

    This class provides a stable public API surface for recovery-related tasks
    while ensuring import safety when executed via importlib spec loaders.
    """

    def __init__(self, repo_root: Optional[Union[str, Path]] = None) -> None:
        if repo_root is None:
            # Resolve repository root relative to this file to avoid dependence
            # on the caller's CWD during initialization.
            resolved_root = Path(__file__).resolve().parents[2]
        else:
            resolved_root = Path(repo_root).expanduser().resolve()
        self._repo_root: Path = resolved_root

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    # Placeholder no-op behavior for compatibility. Business logic, serialization,
    # and validation remain out-of-scope for this portability hardening change.
    # Existing interfaces that rely on these result/config types will continue
    # to work with immutable dataclass semantics preserved above.

    def summarize_source(self, source: Union[str, Path]) -> PortableRecoverySummary:
        src_path = Path(source).expanduser().resolve()
        # Only construct an immutable summary object; avoid any I/O side-effects.
        return PortableRecoverySummary(
            source=src_path,
            project_id=None,
            project_name=None,
            warnings=(),
        )

    def dry_run(self, source: Union[str, Path]) -> RestoreResult:
        summary = self.summarize_source(source)
        return RestoreResult(ok=True, summary=summary, details=())
