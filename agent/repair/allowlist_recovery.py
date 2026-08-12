# Copyright (c) MITIGATE
# SPDX-License-Identifier: MIT

"""
Allowlist-aware recovery decision contract (pure, side-effect-free).

This module provides a deterministic classification of a proposed generated
repository path against a declared set of allowed deliverable paths, with
additional protections for core repository files and path safety rules.

Design constraints:
- Pure functions only; no filesystem, network, subprocess, or environment IO.
- Deterministic and provider-independent.
- Inputs are not mutated; outputs are JSON-serializable.
- No implicit allowlist expansion; no repository or configuration mutations.

Public API:
- class PathRecoveryDecision
- function classify_generated_path(...)

Required minimum fields in the decision:
- normalized_path
- classification
- allowed
- safely_repairable
- human_approval_required
- repeated_invalid_path
- allowed_paths (canonical ordering)
- recovery_instruction
- fingerprint

Classifications supported:
- allowed
- outside_allowlist
- repository_escape
- absolute_path
- protected_core
- malformed_path
- repeated_invalid_path (signaled via the boolean repeated_invalid_path)

Note on repeated_invalid_path:
- The classification field reports the root cause (e.g., outside_allowlist),
  while the boolean flag repeated_invalid_path indicates the request is a
  repeated invalid target across attempts. This allows repair loops to avoid
  infinite retries without losing the underlying cause of rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

# IMPORTANT: Do not import or use any IO, network, or subprocess modules.
# The tests assert these are not imported in this module.

__all__ = [
    "PathRecoveryDecision",
    "classify_generated_path",
]


# Protected Core: built-in immutable set of known core-sensitive files/dirs.
# These are rejected and require human approval.
_PROTECTED_CORE_FILES: Tuple[str, ...] = (
    # Explicit core files mentioned in mission text
    "agent/ai/mission_runner.py",
    "agent/ai/autonomous_controller.py",
    "agent/runtime/background_worker.py",
    "agent/runtime/mission_queue.py",
)

# Directories treated as protected (reject attempts to write beneath them)
_PROTECTED_CORE_DIRS: Tuple[str, ...] = (
    "agent/ai",
    "agent/runtime",
    # Conservative default for service/boot integration areas
    "systemd",
)


def _is_malformed(original: str) -> bool:
    if original is None:
        return True
    s = str(original)
    if "\x00" in s:
        return True
    if s.strip() == "":
        return True
    return False


def _windows_drive_absolute(s: str) -> bool:
    # Detect patterns like "C:/path" or "C:\\path" as absolute on Windows-like inputs
    if len(s) >= 2 and s[1] == ":":
        return True
    return False


def _split_posix(path: str) -> List[str]:
    # Normalize separators to POSIX and split into components.
    # Keep '..' segments for safety checks; drop '.' segments and empty components.
    # This function is intentionally conservative: it DOES NOT collapse '..' because
    # any presence of '..' is treated as a repository_escape.
    p = path.replace("\\", "/")
    # Strip leading './' repeatedly
    while p.startswith("./"):
        p = p[2:]
    # Collapse repeated slashes by split-join
    parts_raw = p.split("/")
    parts: List[str] = []
    for part in parts_raw:
        if part == "" or part == ".":
            continue
        parts.append(part)
    return parts


def _normalize_for_compare(path: str) -> str:
    # Strict normalization for deterministic comparison and fingerprinting.
    # - Converts separators to '/'
    # - Removes leading './' segments and redundant slashes
    # - Removes '.' segments
    # - Keeps '..' segments intact (we do not resolve them into parent directories)
    if path is None:
        return ""
    parts = _split_posix(str(path))
    return "/".join(parts)


def _is_absolute(path: str) -> bool:
    if not isinstance(path, str):
        return False
    if path.startswith("/"):
        return True
    if _windows_drive_absolute(path):
        return True
    # Leading backslash alone is considered absolute on Windows; treat conservatively
    if path.startswith("\\"):
        return True
    return False


def _has_traversal(normalized: str) -> bool:
    # After normalization, any '..' segment indicates traversal attempt.
    return any(part == ".." for part in normalized.split("/") if part)


def _canonicalize_list(paths: Iterable[str]) -> List[str]:
    # Produce a sorted, unique, normalized list without mutating input.
    seen = set()
    out: List[str] = []
    for p in list(paths) if not isinstance(paths, (list, tuple)) else paths:  # snapshot
        if p is None:
            continue
        n = _normalize_for_compare(str(p))
        if n not in seen and n != "":
            seen.add(n)
            out.append(n)
    out.sort()
    return out


def _is_under_dir(path: str, protected_dir: str) -> bool:
    # path and protected_dir are normalized POSIX strings (no leading './').
    if path == protected_dir:
        return True
    if protected_dir == "":
            return False
    prefix = protected_dir + "/"
    return path.startswith(prefix)


def _compute_fingerprint(normalized_path: str) -> str:
    # Deterministic fingerprint based solely on normalized path.
    # This avoids hidden dependencies and remains stable across runs.
    h = sha256()
    h.update(b"mitigate:self-healing:v2:")
    h.update(normalized_path.encode("utf-8", errors="strict"))
    return h.hexdigest()


@dataclass(frozen=True)
class PathRecoveryDecision:
    normalized_path: str
    classification: str
    allowed: bool
    safely_repairable: bool
    human_approval_required: bool
    repeated_invalid_path: bool
    allowed_paths: Tuple[str, ...]
    recovery_instruction: str
    fingerprint: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "normalized_path": self.normalized_path,
            "classification": self.classification,
            "allowed": self.allowed,
            "safely_repairable": self.safely_repairable,
            "human_approval_required": self.human_approval_required,
            "repeated_invalid_path": self.repeated_invalid_path,
            "allowed_paths": list(self.allowed_paths),
            "recovery_instruction": self.recovery_instruction,
            "fingerprint": self.fingerprint,
        }


PreviousPathType = Union[str, Mapping[str, object]]


def _extract_previous_keys(previous: Iterable[PreviousPathType]) -> Tuple[set, set]:
    # Build sets of normalized paths and fingerprints from previous rejected entries.
    normalized_set = set()
    fingerprint_set = set()
    for item in list(previous) if not isinstance(previous, (list, tuple)) else previous:  # snapshot
        try:
            if isinstance(item, str):
                n = _normalize_for_compare(item)
                if n:
                    normalized_set.add(n)
                continue
            if isinstance(item, Mapping):
                # Accept several common keys without mutating input
                for k in ("normalized_path", "generated_path", "path"):
                    v = item.get(k)  # type: ignore[index]
                    if isinstance(v, str):
                        n = _normalize_for_compare(v)
                        if n:
                            normalized_set.add(n)
                fp = item.get("fingerprint")  # type: ignore[index]
                if isinstance(fp, str) and fp:
                    fingerprint_set.add(fp)
        except Exception:
            # Remain strictly pure and fail-closed on odd inputs by skipping them.
            continue
    return normalized_set, fingerprint_set


def classify_generated_path(
    generated_path: str,
    allowed_paths: Sequence[str],
    protected_paths: Sequence[str] | Tuple[str, ...] = (),
    previous_rejected_paths: Sequence[PreviousPathType] | Tuple[PreviousPathType, ...] = (),
) -> Dict[str, object]:
    """
    Classify a proposed generated path against an allowlist and protected paths.

    This function is pure and deterministic. It performs no IO and mutates no input.

    Parameters:
    - generated_path: Proposed file path within the repository (string-like).
    - allowed_paths: Declared deliverable paths for the current mission.
    - protected_paths: Additional protected paths (files or directories) that must not be targeted.
    - previous_rejected_paths: History of previously rejected targets to detect repeats.

    Returns a JSON-serializable dict containing the required minimum fields.
    """
    # Snapshot and canonicalize inputs without mutating callers' data
    allowed_canon: List[str] = _canonicalize_list(allowed_paths)

    # Protected: combine built-ins with caller-specified additions
    protected_combined: List[str] = []
    protected_combined.extend(_PROTECTED_CORE_FILES)
    protected_combined.extend(_PROTECTED_CORE_DIRS)
    protected_combined.extend(_canonicalize_list(protected_paths))

    normalized = _normalize_for_compare(generated_path)

    # Determine basic safety classifications
    if _is_malformed(generated_path):
        classification = "malformed_path"
        allowed = False
        safely_repairable = False
        human_approval_required = False
    elif _is_absolute(generated_path):
        classification = "absolute_path"
        allowed = False
        safely_repairable = False
        human_approval_required = False
    elif _has_traversal(normalized):
        classification = "repository_escape"
        allowed = False
        safely_repairable = False
        human_approval_required = False
    else:
        # Check protected core (files or directories)
        is_protected = False
        for prot in protected_combined:
            if prot in _PROTECTED_CORE_FILES:
                if normalized == prot:
                    is_protected = True
                    break
            else:
                if _is_under_dir(normalized, prot):
                    is_protected = True
                    break
        if is_protected:
            classification = "protected_core"
            allowed = False
            safely_repairable = False
            human_approval_required = True
        else:
            if normalized in allowed_canon:
                classification = "allowed"
                allowed = True
                safely_repairable = True
                human_approval_required = False
            else:
                classification = "outside_allowlist"
                allowed = False
                safely_repairable = True
                human_approval_required = False

    # Compute fingerprint and repeated detection
    fingerprint = _compute_fingerprint(normalized)
    prev_norm, prev_fp = _extract_previous_keys(previous_rejected_paths)
    is_repeated = (not allowed) and (normalized in prev_norm or fingerprint in prev_fp)

    # Recovery guidance messages
    if classification == "allowed":
        instruction = (
            f"Path '{normalized}' is allowed. Proceed with generation strictly within the declared deliverables."
        )
    elif classification == "outside_allowlist":
        allowed_list_str = ", ".join(allowed_canon) if allowed_canon else "<none>"
        instruction = (
            f"Path '{normalized}' is not in the declared deliverables. Allowed paths: [{allowed_list_str}]. "
            "No new paths may be created. Regenerate using only the exact declared deliverables."
        )
    elif classification == "absolute_path":
        allowed_list_str = ", ".join(allowed_canon) if allowed_canon else "<none>"
        instruction = (
            f"Absolute paths are rejected. Proposed: '{generated_path}'. Use only repository-relative paths and "
            f"restrict output to these declared deliverables: [{allowed_list_str}]."
        )
    elif classification == "repository_escape":
        allowed_list_str = ", ".join(allowed_canon) if allowed_canon else "<none>"
        instruction = (
            f"Path traversal is rejected. Proposed: '{generated_path}'. Do not use '..' or attempt repository escape. "
            f"Regenerate strictly within declared deliverables: [{allowed_list_str}]."
        )
    elif classification == "protected_core":
        allowed_list_str = ", ".join(allowed_canon) if allowed_canon else "<none>"
        instruction = (
            f"Target '{normalized}' is protected Core and cannot be modified without human approval. "
            f"Fail closed. Regenerate targeting only declared deliverables: [{allowed_list_str}]."
        )
    else:  # malformed_path or any other conservative failure
        allowed_list_str = ", ".join(allowed_canon) if allowed_canon else "<none>"
        instruction = (
            f"Malformed path rejected. Proposed: '{generated_path}'. Provide a non-empty, repository-relative file path "
            f"from the declared deliverables: [{allowed_list_str}]."
        )

    decision = PathRecoveryDecision(
        normalized_path=normalized,
        classification=classification,
        allowed=allowed,
        safely_repairable=safely_repairable,
        human_approval_required=human_approval_required,
        repeated_invalid_path=is_repeated,
        allowed_paths=tuple(allowed_canon),
        recovery_instruction=instruction,
        fingerprint=fingerprint,
    )

    # Return JSON-serializable mapping (not the dataclass instance itself)
    return decision.to_dict()
