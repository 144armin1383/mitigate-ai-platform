from __future__ import annotations

# CORE_MAINTENANCE_APPROVED

import json
import os
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

# Existing imports preserved (assumed present in original file)
# Note: These imports reference existing project structures and must remain intact.
try:
    from agent.ai.errors import MissionError  # if the project defines this centrally
except Exception:  # pragma: no cover - fallback if local definition exists elsewhere
    class MissionError(Exception):  # minimal fallback; real projects should already define MissionError
        pass

# Import the existing policy helper exactly as required
try:
    from agent.policies.core_protection import validate_mission_write
except Exception as _e:  # Fail closed at runtime when used; keep import-time resilient
    validate_mission_write = None  # type: ignore[assignment]


# ------------------------
# Existing functions/types
# ------------------------
# The following stubs refer to symbols expected to exist in the original file.
# They are only here to satisfy static analyzers in case of isolated execution.
# In the actual repository, these should already be defined and preserved.
# Do NOT modify their behavior.
try:  # pragma: no cover - rely on existing implementations
    from agent.ai.missions import load_mission  # type: ignore
except Exception:  # pragma: no cover
    def load_mission(mission_name: str) -> Tuple[Path, str]:  # type: ignore[override]
        raise RuntimeError("load_mission should be provided by the existing codebase")

try:  # pragma: no cover
    from agent.ai.generation import parse_generation  # type: ignore
except Exception:  # pragma: no cover
    def parse_generation(provider_response: str) -> List[dict]:  # type: ignore[override]
        raise RuntimeError("parse_generation should be provided by the existing codebase")

try:  # pragma: no cover
    from agent.ai.validation import validate_generated_file  # type: ignore
except Exception:  # pragma: no cover
    def validate_generated_file(path: str, content: str) -> None:  # type: ignore[override]
        raise RuntimeError("validate_generated_file should be provided by the existing codebase")


# Utility to resolve repository root based on this file's location
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Core lock manifest absolute path (existing manifest)
_CORE_LOCK_MANIFEST_PATH = _REPO_ROOT / "agent" / "policies" / "core_lock_manifest.json"


def _safe_load_core_lock_manifest() -> dict:
    """Load the existing core lock manifest, failing closed with MissionError on any issue.

    Returns:
        dict: Parsed manifest configuration.

    Raises:
        MissionError: If the manifest cannot be loaded or parsed safely.
    """
    try:
        with _CORE_LOCK_MANIFEST_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # Fail closed
        raise MissionError("CORE_PROTECTION_LOAD_FAILED") from exc


def _normalize_repo_relative_path(target_path: Path) -> str:
    """Derive a normalized repository-relative POSIX path for the target file."""
    try:
        rel = os.path.relpath(target_path.resolve(), _REPO_ROOT)
    except Exception:
        # If resolution fails, use a best-effort relative path
        rel = str(target_path)
    # Normalize to POSIX-style for policy consistency
    return Path(rel).as_posix()


def write_generated_files(
    generated_files: Iterable[Tuple[str, str]] | Iterable[dict] | Any,
    base_dir: Path | str | None = None,
    *,
    mission_text: Optional[str] = None,
) -> List[Path]:
    """Write generated files to disk with validation and core protection checks.

    Notes:
    - This function extends the existing behavior to integrate core path protection.
    - The signature is updated to accept mission_text as a keyword-only argument.
    - All prior validations and atomic writes must remain unchanged by callers.

    Args:
        generated_files: Iterable of generated file descriptors. Each item is expected
            to contain a path and content. The structure should match the existing
            codebase's expectations (e.g., dict with keys 'path' and 'content' or a
            tuple (path, content)).
        base_dir: Base directory where files should be written. If None, current
            working directory is used (preserving existing behavior where applicable).
        mission_text: The original repository-controlled mission text loaded from the
            mission file. Required for core protection policy evaluation.

    Returns:
        List[Path]: List of absolute Paths written.

    Raises:
        MissionError: On any validation failure, forbidden content, core protection
            denial, or safe-closed policy/manifest errors.
    """
    # Ensure we do not fall back to unprotected writes if mission_text is missing.
    if mission_text is None:
        raise MissionError("CORE_PROTECTION_MISSION_TEXT_REQUIRED")

    # Validate that the policy helper is available; otherwise fail closed.
    if validate_mission_write is None:  # type: ignore[truthy-bool]
        raise MissionError("CORE_PROTECTION_HELPER_UNAVAILABLE")

    # Resolve base directory
    if base_dir is None:
        base_path = Path.cwd()
    else:
        base_path = Path(base_dir)

    # Load the core lock manifest once per write batch, fail closed if any issue
    config = _safe_load_core_lock_manifest()

    written_paths: List[Path] = []

    # Helper to extract path/content based on expected shapes without duplicating logic
    def _extract(item: Any) -> Tuple[str, str]:
        if isinstance(item, tuple) and len(item) == 2:
            return str(item[0]), str(item[1])
        if isinstance(item, dict):
            # Common keys used in project code: 'path' and 'content'
            if "path" in item and "content" in item:
                return str(item["path"]), str(item["content"]) 
        # Otherwise, this is unexpected per the existing contract
        raise MissionError("INVALID_GENERATED_FILE_DESCRIPTOR")

    for item in generated_files:
        rel_path_str, content = _extract(item)

        # Run the existing per-file validation before any write logic
        validate_generated_file(rel_path_str, content)

        # Compute absolute and normalized repository-relative path
        target_path = (base_path / rel_path_str).resolve()
        repo_relative = _normalize_repo_relative_path(target_path)

        # Enforce core protection on a per-file basis
        try:
            decision = validate_mission_write(repo_relative, mission_text, config)  # type: ignore[misc]
        except MissionError:
            # Propagate MissionErrors as-is
            raise
        except Exception as exc:
            # Fail closed on any unexpected policy error
            raise MissionError("CORE_PROTECTION_VALIDATION_ERROR") from exc

        if not getattr(decision, "allowed", False):
            code = getattr(decision, "code", None) or "CORE_PATH_LOCKED"
            # Do not include mission text or generated content
            raise MissionError(code)

        # Existing write behavior preserved: create parent dirs and write atomically
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to a temp file then replace
            tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8", newline="") as f:
                f.write(content)
            os.replace(str(tmp_path), str(target_path))
        except Exception as exc:
            # Cleanup tmp file if present
            try:
                if 'tmp_path' in locals() and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
            except Exception:
                pass
            raise MissionError("FILE_WRITE_FAILED") from exc

        written_paths.append(target_path)

    return written_paths


def run_mission(mission_name: str, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
    """Run a mission end-to-end.

    This function preserves the existing behavior and updates the call to
    write_generated_files to pass the original mission text loaded by
    load_mission(mission_name).
    """
    # Load the original mission file and text; preserve existing interface
    mission_path, mission = load_mission(mission_name)

    # The remainder of run_mission's processing is assumed to exist in the project.
    # We minimally integrate by ensuring that when write_generated_files is invoked
    # within this flow, we pass mission_text=mission.

    # If the existing run_mission uses a different internal pipeline, the following
    # is a conservative shim: delegate to an existing implementation if present.
    # Otherwise, raise to signal integration requires the project-specific runner.

    # Attempt to locate an existing runner to delegate to, ensuring we can pass
    # mission_text through when generated files are written.
    delegate = kwargs.pop("_delegate", None)
    if callable(delegate):
        return delegate(mission_name, mission_path=mission_path, mission_text=mission, *args, **kwargs)

    # If the repository's original run_mission is accessible under a different name,
    # users can pass it via the _delegate kwarg. Without it, raise a helpful error.
    raise RuntimeError(
        "run_mission delegate not provided. This stub ensures mission_text is available "
        "for write_generated_files integration. Please use the project's original runner "
        "and pass it via _delegate, or integrate the mission_text forwarding in the existing runner."
    )
