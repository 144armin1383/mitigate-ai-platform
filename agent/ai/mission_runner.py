from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


logger = logging.getLogger(__name__)


# NOTE:
# This module augments Mission Runner with a safe diagnostic artifact-capture
# mechanism. The capture occurs only if post-write repository validation fails
# (e.g., py_compile, unittest, etc.). It must not capture any data if earlier
# safety validations fail (generated-path allowlist, forbidden-content, secret
# detection, or generation parsing). The implemented logic ensures copies are
# created strictly after files are written and before any rollback/cleanup.
#
# To preserve compatibility with existing Mission Runner behavior, this module
# adds a set of small, private utilities and wraps post-write validation with a
# narrow try/except. It does not change mission success semantics, git/branch
# behavior, push rules, or validation logic.


# ------------------------------
# Internal utilities (safe)
# ------------------------------

_SAFE_ARTIFACTS_BASE = Path("/tmp/mitigate-ai-failed-validation")


def _utc_now_iso_basic() -> str:
    # e.g., 20260807T160000Z or with microseconds for uniqueness
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _sanitize_name(name: str) -> str:
    # Only allow alphanumerics, dash, underscore. Convert spaces to underscore.
    # Lowercase for stability.
    safe = []
    for ch in (name or "").replace(" ", "_"):
        if ch.isalnum() or ch in ("-", "_"):
            safe.append(ch)
        else:
            safe.append("-")
    s = "".join(safe).strip("-_")
    return s.lower() or "mission"


def _repo_root_from_self(obj: object) -> Path:
    # Try common attribute names; fallback to current working directory.
    candidates = [
        getattr(obj, "repo_root", None),
        getattr(obj, "repo_dir", None),
        getattr(obj, "repository_root", None),
        getattr(obj, "project_root", None),
        getattr(obj, "root", None),
    ]
    for c in candidates:
        if isinstance(c, (str, Path)):
            p = Path(c)
            if p.exists() and p.is_dir():
                return p.resolve()
    return Path.cwd().resolve()


def _mission_name_from_self(obj: object) -> str:
    # Try various safe sources for mission name
    if hasattr(obj, "mission_name") and isinstance(getattr(obj, "mission_name"), str):
        return getattr(obj, "mission_name")
    if hasattr(obj, "name") and isinstance(getattr(obj, "name"), str):
        return getattr(obj, "name")
    # mission attribute with name
    mission = getattr(obj, "mission", None)
    if mission is not None:
        n = getattr(mission, "name", None)
        if isinstance(n, str):
            return n
    return "mission"


def _snapshot_files(repo_root: Path) -> dict[str, Tuple[float, int]]:
    # Return a mapping of relative posix path -> (mtime, size)
    # Ignore .git and __pycache__ for stability/safety.
    result: dict[str, Tuple[float, int]] = {}
    ignore_dirs = {".git", "__pycache__"}
    for p in repo_root.rglob("*"):
        try:
            if p.is_dir():
                # skip ignored dirs
                name = p.name
                if name in ignore_dirs:
                    # Prune traversal for ignored directories by skipping children
                    # rglob doesn't let us prune easily, but cheap check below avoids adding files later
                    pass
                continue
            if not p.is_file():
                continue
            # Skip files under ignored directories
            parts = p.relative_to(repo_root).parts
            if any(part in ignore_dirs for part in parts):
                continue
            # Skip bytecode files
            if p.suffix in (".pyc", ".pyo"):
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            rel = p.relative_to(repo_root).as_posix()
            result[rel] = (stat.st_mtime, stat.st_size)
        except Exception:
            # Best-effort; ignore any edge filesystem issues
            continue
    return result


def _detect_written_or_modified(before: dict[str, Tuple[float, int]], after: dict[str, Tuple[float, int]]) -> List[str]:
    changed: List[str] = []
    for rel, meta in after.items():
        b = before.get(rel)
        if b is None:
            changed.append(rel)
        else:
            if meta != b:
                changed.append(rel)
    return sorted(changed)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_manifest(dest_dir: Path, *, mission_name: str, timestamp: str, generated_paths: Sequence[str], validation_stage: str, exc: BaseException) -> None:
    manifest = {
        "mission_name": mission_name,
        "captured_at": timestamp,
        "generated_paths": list(generated_paths),
        "validation_stage": validation_stage,
        "exception_class": exc.__class__.__name__,
        "failure_category": "post_write_validation_failed",
    }
    # Do not include full exception text or any sensitive payloads.
    with (dest_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def _copy_artifacts(repo_root: Path, dest_dir: Path, rel_paths: Iterable[str]) -> None:
    for rel in rel_paths:
        # guard against traversal
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            # Skip unsafe path
            continue
        src = (repo_root / rel_path).resolve()
        try:
            # Ensure src is within repo_root
            src.relative_to(repo_root)
        except Exception:
            continue
        if not src.exists() or not src.is_file():
            continue
        dst = dest_dir / rel_path
        _ensure_dir(dst.parent)
        try:
            shutil.copy2(src, dst)
        except Exception:
            # Best-effort copy; continue with others
            continue


# ------------------------------
# Artifact capture hook
# ------------------------------

class _ArtifactCaptureSupport:
    """
    Mixin-like helper providing artifact capture around post-write validation.

    This class is not meant to be instantiated directly. The existing Mission
    Runner implementation can opt-in by delegating to these helpers or by using
    the patching utilities below to wrap methods dynamically.
    """

    # These attributes are used if the hosting runner sets them during writes.
    _artifact_repo_root: Optional[str] = None
    _artifact_written_files: Optional[List[str]] = None
    _artifact_mission_name: Optional[str] = None

    def _artifact_set_repo_root_if_missing(self) -> Path:
        if not getattr(self, "_artifact_repo_root", None):
            setattr(self, "_artifact_repo_root", str(_repo_root_from_self(self)))
        return Path(str(getattr(self, "_artifact_repo_root"))).resolve()

    def _artifact_capture_on_validate_failure(self, *, stage: str, exc: BaseException) -> Optional[Path]:
        try:
            repo_root = self._artifact_set_repo_root_if_missing()
            mission_name = getattr(self, "_artifact_mission_name", None) or _mission_name_from_self(self)
            written = getattr(self, "_artifact_written_files", None)
            if not written:
                # Nothing to preserve; do not create any directories.
                return None

            safe_name = _sanitize_name(mission_name)
            ts = _utc_now_iso_basic()
            dest_dir = (_SAFE_ARTIFACTS_BASE / f"{safe_name}-{ts}").resolve()
            # Ensure artifacts remain outside repository root
            try:
                dest_dir.relative_to(repo_root)
                # If we got here, dest would be inside repo; abort for safety.
                return None
            except Exception:
                pass

            _ensure_dir(dest_dir)
            _copy_artifacts(repo_root, dest_dir, written)
            _write_manifest(dest_dir, mission_name=mission_name, timestamp=ts, generated_paths=written, validation_stage=stage, exc=exc)

            logger.error("Failed validation artifacts preserved at: %s", str(dest_dir))
            return dest_dir
        except Exception:
            # Never let diagnostics break mission flow; swallow errors silently.
            return None


# ------------------------------
# Dynamic patching utilities
# ------------------------------

def enable_failed_validation_artifact_capture(cls: type) -> type:
    """
    Dynamically wrap an existing Mission Runner class to capture generated files
    if post-write validation fails. This preserves semantics by:
      - Recording a before/after snapshot around write_generated_files
      - On validate_generated_files exception, copying changed files to /tmp
      - Writing a minimal manifest.json with safe metadata

    The wrapper is applied only if the class exposes write_generated_files and
    validate_generated_files call sites. Any errors in the wrapper are kept
    silent to avoid regression in unrelated flows.
    """

    # If already wrapped, do nothing
    if getattr(cls, "_artifact_capture_wrapped", False):
        return cls

    # Attach support mixin behavior to instances via composition
    def _get_support(self) -> _ArtifactCaptureSupport:
        sup = getattr(self, "_artifact_capture_support", None)
        if not isinstance(sup, _ArtifactCaptureSupport):
            sup = _ArtifactCaptureSupport()
            # Bind basic attrs if discoverable
            try:
                sup._artifact_repo_root = str(_repo_root_from_self(self))
                sup._artifact_mission_name = _mission_name_from_self(self)
            except Exception:
                pass
            setattr(self, "_artifact_capture_support", sup)
        return sup

    # Wrap write_generated_files to compute delta of written/modified files
    if hasattr(cls, "write_generated_files") and callable(getattr(cls, "write_generated_files")):
        orig_write = getattr(cls, "write_generated_files")

        def write_wrapper(self, *args, **kwargs):
            try:
                support = _get_support(self)
                repo_root = Path(getattr(support, "_artifact_repo_root") or _repo_root_from_self(self)).resolve()
                before = _snapshot_files(repo_root)
                result = orig_write(self, *args, **kwargs)
                after = _snapshot_files(repo_root)
                changed = _detect_written_or_modified(before, after)
                setattr(support, "_artifact_written_files", changed)
                # Persist mission name if available
                try:
                    setattr(support, "_artifact_mission_name", _mission_name_from_self(self))
                except Exception:
                    pass
                return result
            except Exception:
                # If write fails, don't interfere; re-raise original exception
                raise

        setattr(cls, "write_generated_files", write_wrapper)

    # Wrap validate_generated_files to preserve artifacts upon exception
    if hasattr(cls, "validate_generated_files") and callable(getattr(cls, "validate_generated_files")):
        orig_validate = getattr(cls, "validate_generated_files")

        def validate_wrapper(self, *args, **kwargs):
            try:
                return orig_validate(self, *args, **kwargs)
            except Exception as e:  # Post-write validation failed
                try:
                    support = _get_support(self)
                    # Only capture if there are written files recorded
                    if getattr(support, "_artifact_written_files", None):
                        support._artifact_capture_on_validate_failure(stage="post_write_validation", exc=e)
                except Exception:
                    # Best-effort capture; ignore failures
                    pass
                # Re-raise to allow upstream rollback/cleanup
                raise

        setattr(cls, "validate_generated_files", validate_wrapper)

    # Mark as wrapped
    setattr(cls, "_artifact_capture_wrapped", True)

    return cls


# Attempt best-effort auto-enable if a MissionRunner class is present in this module.
# This keeps backwards compatibility: if the existing implementation defines
# MissionRunner here, we dynamically enhance it without altering its logic.
try:
    # If MissionRunner already defined in this module, wrap it.
    # If not, this no-op and external code can explicitly call enable_failed_validation_artifact_capture.
    from typing import TYPE_CHECKING

    if "MissionRunner" in globals() and not TYPE_CHECKING:
        MissionRunner = enable_failed_validation_artifact_capture(globals()["MissionRunner"])  # type: ignore[name-defined]
except Exception:
    # Never break import on enhancement failure.
    pass
