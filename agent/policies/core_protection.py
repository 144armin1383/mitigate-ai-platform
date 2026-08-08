from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
import json

__all__ = [
    "CoreProtectionConfig",
    "ProtectionKind",
    "ProtectionDecision",
    "ManifestValidationError",
    "load_core_lock_manifest",
    "classify_protected_path",
    "validate_mission_write",
    "core_protection_status",
]


_DEFAULT_MANIFEST_PATH = Path("agent/policies/core_lock_manifest.json")
_SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


class ManifestValidationError(ValueError):
    """Raised when the core lock manifest is malformed or contains unknown fields."""


class ProtectionKind(Enum):
    UNPROTECTED = "unprotected"
    PROTECTED_CORE = "protected_core"
    CANONICAL_TEST = "canonical_test"


@dataclass(frozen=True)
class CoreProtectionConfig:
    schema_version: str
    protected_core_paths: Tuple[str, ...]
    canonical_test_paths: Tuple[str, ...]
    core_maintenance_marker: str
    test_contract_maintenance_marker: str
    manual_merge_required_for_core_changes: bool
    full_suite_required_for_core_changes: bool
    recovery_gate_required_for_core_changes: bool


@dataclass(frozen=True)
class ProtectionDecision:
    allowed: bool
    kind: ProtectionKind
    code: Optional[str] = None
    manual_merge_required: bool = False
    full_suite_required: bool = False
    recovery_gate_required: bool = False
    message: str = ""


def _normalize_repo_path(path: str) -> str:
    """Normalize a repository path to a safe, relative, POSIX-style path.

    - Converts backslashes to slashes.
    - Removes leading slashes.
    - Resolves '.' segments.
    - Resolves '..' segments with root clamping (cannot escape above root).
    - Removes redundant separators.

    Returns an empty string for paths that normalize to repository root.
    """
    s = str(path).replace("\\", "/")
    # strip leading slashes to ensure relative
    while s.startswith("/"):
        s = s[1:]
    parts: List[str] = []
    for seg in s.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
            else:
                # clamp at repo root; do not preserve leading ..
                continue
        else:
            parts.append(seg)
    return "/".join(parts)


def _ensure_dir_prefix(p: str) -> str:
    """Return a normalized directory prefix path ending with '/'."""
    n = _normalize_repo_path(p)
    if n and not n.endswith("/"):
        n = n + "/"
    elif not n:
        # root directory
        n = ""
    return n


def _normalize_manifest_paths(paths: Iterable[str]) -> Tuple[str, ...]:
    return tuple(_normalize_repo_path(p) for p in paths)


def _validate_manifest_types(data: dict) -> None:
    required_fields = {
        "schema_version": str,
        "protected_core_paths": list,
        "canonical_test_paths": list,
        "core_maintenance_marker": str,
        "test_contract_maintenance_marker": str,
        "manual_merge_required_for_core_changes": bool,
        "full_suite_required_for_core_changes": bool,
        "recovery_gate_required_for_core_changes": bool,
    }
    unknown = set(data.keys()) - set(required_fields.keys())
    if unknown:
        raise ManifestValidationError(f"unknown fields in manifest: {sorted(unknown)}")
    for k, t in required_fields.items():
        if k not in data:
            raise ManifestValidationError(f"missing required field: {k}")
        v = data[k]
        if t is list:
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise ManifestValidationError(f"field '{k}' must be a list of strings")
        else:
            if not isinstance(v, t):
                raise ManifestValidationError(f"field '{k}' must be of type {t.__name__}")


def load_core_lock_manifest(manifest_path: Optional[Path | str] = None) -> CoreProtectionConfig:
    """Load and validate the core lock manifest.

    Strictly validates required fields, types, and supported schema versions.
    Rejects unknown fields deterministically.
    """
    path = Path(manifest_path) if manifest_path is not None else _DEFAULT_MANIFEST_PATH
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError as e:
        raise ManifestValidationError(f"manifest not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ManifestValidationError(f"manifest is not valid JSON: {path}") from e

    if not isinstance(raw, dict):
        raise ManifestValidationError("manifest root must be an object")

    _validate_manifest_types(raw)

    schema_version = raw["schema_version"]
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestValidationError(f"unsupported schema_version: {schema_version}")

    protected_core_paths = _normalize_manifest_paths(raw["protected_core_paths"])
    canonical_test_paths = _normalize_manifest_paths(raw["canonical_test_paths"])

    return CoreProtectionConfig(
        schema_version=schema_version,
        protected_core_paths=tuple(protected_core_paths),
        canonical_test_paths=tuple(canonical_test_paths),
        core_maintenance_marker=raw["core_maintenance_marker"],
        test_contract_maintenance_marker=raw["test_contract_maintenance_marker"],
        manual_merge_required_for_core_changes=raw["manual_merge_required_for_core_changes"],
        full_suite_required_for_core_changes=raw["full_suite_required_for_core_changes"],
        recovery_gate_required_for_core_changes=raw["recovery_gate_required_for_core_changes"],
    )


def _is_within_dir(target: str, dir_prefix: str) -> bool:
    """Check if target is within the given dir prefix (normalized).

    dir_prefix must be a normalized directory path ending with '/'.
    """
    if dir_prefix == "":
        # root prefix protects everything
        return True
    if not dir_prefix.endswith("/"):
        dir_prefix = dir_prefix + "/"
    return target == dir_prefix[:-1] or target.startswith(dir_prefix)


def _canonical_test_match(target: str, paths: Sequence[str]) -> bool:
    for p in paths:
        if not p:
            continue
        if p.endswith("/"):
            # directory-style canonical lock
            if _is_within_dir(target, p):
                return True
        else:
            if target == p:
                return True
    return False


def classify_protected_path(path: str | Path, config: CoreProtectionConfig) -> ProtectionKind:
    """Classify a path as unprotected, protected core, or canonical test.

    Handles path normalization and traversal.
    """
    target = _normalize_repo_path(str(path))

    # Canonical tests take precedence: even if inside a protected core dir, it's a canonical test
    if _canonical_test_match(target, config.canonical_test_paths):
        return ProtectionKind.CANONICAL_TEST

    # Check protected core directories
    for entry in config.protected_core_paths:
        # Interpret entries as directory prefixes
        pref = entry if entry.endswith("/") else (entry + "/")
        if _is_within_dir(target, pref):
            return ProtectionKind.PROTECTED_CORE

    return ProtectionKind.UNPROTECTED


def _has_exact_marker_line(mission_text: str, marker: str) -> bool:
    return any(
        line.strip() == marker
        for line in mission_text.splitlines()
    )


def _has_core_marker(mission_text: str, config: CoreProtectionConfig) -> bool:
    return _has_exact_marker_line(
        mission_text,
        config.core_maintenance_marker,
    )


def _has_test_contract_marker(mission_text: str, config: CoreProtectionConfig) -> bool:
    return _has_exact_marker_line(
        mission_text,
        config.test_contract_maintenance_marker,
    )


def validate_mission_write(
    target_path: str | Path,
    mission_text: str,
    config: CoreProtectionConfig,
) -> ProtectionDecision:
    """Validate whether a mission may write to target_path.

    - Denies by default for protected core paths (CORE_PATH_LOCKED).
    - Denies by default for canonical tests (CANONICAL_TEST_LOCKED).
    - Allows core path modification only with explicit core marker.
    - Allows canonical test modification only with both core and test-contract markers.
    - When allowed due to overrides, emits required flags for manual review and testing gates.
    """
    # Do not mutate inputs; normalize a local copy only
    target = _normalize_repo_path(str(target_path))
    kind = classify_protected_path(target, config)

    if kind is ProtectionKind.UNPROTECTED:
        return ProtectionDecision(
            allowed=True,
            kind=kind,
            message="unprotected path allow",
        )

    if kind is ProtectionKind.PROTECTED_CORE:
        if _has_core_marker(mission_text, config):
            return ProtectionDecision(
                allowed=True,
                kind=kind,
                manual_merge_required=config.manual_merge_required_for_core_changes,
                full_suite_required=config.full_suite_required_for_core_changes,
                recovery_gate_required=config.recovery_gate_required_for_core_changes,
                message="core path override by explicit marker",
            )
        return ProtectionDecision(
            allowed=False,
            kind=kind,
            code="CORE_PATH_LOCKED",
            message="write denied: protected core path",
        )

    # Canonical tests require both markers
    if kind is ProtectionKind.CANONICAL_TEST:
        if _has_core_marker(mission_text, config) and _has_test_contract_marker(mission_text, config):
            return ProtectionDecision(
                allowed=True,
                kind=kind,
                manual_merge_required=config.manual_merge_required_for_core_changes,
                full_suite_required=config.full_suite_required_for_core_changes,
                recovery_gate_required=config.recovery_gate_required_for_core_changes,
                message="canonical test override by explicit markers",
            )
        return ProtectionDecision(
            allowed=False,
            kind=kind,
            code="CANONICAL_TEST_LOCKED",
            message="write denied: canonical test path",
        )

    # Fallback fail-closed (should not be reachable)
    return ProtectionDecision(
        allowed=False,
        kind=kind,
        code="CORE_PATH_LOCKED",
        message="write denied: unknown classification",
    )


def core_protection_status(mission_text: str, config: CoreProtectionConfig) -> dict:
    """Return a deterministic summary of markers and enforcement requirements.

    Useful for reporting and tests.
    """
    return {
        "schema_version": config.schema_version,
        "core_marker_present": _has_core_marker(mission_text, config),
        "test_contract_marker_present": _has_test_contract_marker(mission_text, config),
        "manual_merge_required_for_core_changes": config.manual_merge_required_for_core_changes,
        "full_suite_required_for_core_changes": config.full_suite_required_for_core_changes,
        "recovery_gate_required_for_core_changes": config.recovery_gate_required_for_core_changes,
    }
