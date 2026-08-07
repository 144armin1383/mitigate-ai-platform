# Copyright (c) MITIGATE AI
# Portable bootstrap utilities
#
# Production-quality, deterministic, provider-neutral configuration handling.
#
# This module provides a strict configuration normalization layer that accepts
# canonical fields and portable aliases, with explicit conflict detection and
# unknown-field rejection. Unsafe repository/bootstrap paths are rejected with
# a safe, recognizable error message that does not leak filesystem details.

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional, Set, Tuple
import os

__all__ = [
    "normalize_and_validate_config",
    "normalize_bootstrap_config",
    "validate_and_normalize_config",
    "load_bootstrap_config",
    "validate_repository_paths",
    "ensure_safe_paths",
    "is_unsafe_path",
    "join_safe_path",
]

# Portable aliases accepted by the public interface. These are mapped to
# canonical configuration keys deterministically, with conflict detection.
#
# site_adapter is treated specially: if the production configuration already
# uses a different canonical variant (e.g., "site_adapter"), the alias will be
# mapped to that existing field without creating duplicate state.
_PORTABLE_ALIASES_FIXED: Dict[str, str] = {
    "environment": "environment_name",
    "project_id": "default_project_id",
    "provider": "provider_name",
    # site_adapter is resolved dynamically to the chosen canonical key
}

# Potential canonical variants for the site adapter key used across different
# environments. The first one found in the provided config is treated as the
# canonical key for this normalization run. If none are present, we default to
# "site_adapter_name".
_SITE_ADAPTER_CANONICAL_CANDIDATES: Tuple[str, ...] = (
    "site_adapter_name",
    "site_adapter",
    "site_adapter_id",
    "site_adapter_type",
    "site_adapter_slug",
)
_DEFAULT_SITE_ADAPTER_CANONICAL = "site_adapter_name"

# Allowed canonical fields. Aliases listed in _PORTABLE_ALIASES_FIXED and the
# dynamically-resolved site-adapter canonical key are also accepted, but they
# are normalized to canonical output without duplicates.
_ALLOWED_FIELDS_BASE: Set[str] = {
    # Canonical portable fields
    "environment_name",
    "default_project_id",
    "provider_name",
    "site_adapter_name",
    # Repository/bootstrap path fields (validated for path safety)
    "repository_root",
    "bootstrap_root",
    "project_path",
    # Additional common neutral fields used by the runtime
    "data_root",
    "memory_root",
    "provider_base_url",
    "runtime_host",
    "runtime_port",
    "model",
    "provider_model",
    "config_version",
    "project_name",
    "workspace",
    "profile",
    "adapter",
    "provider_adapter",
    # Accept common site adapter canonical variants to preserve compatibility
    "site_adapter",
    "site_adapter_id",
    "site_adapter_type",
    "site_adapter_slug",
}

# Repository/bootstrap path keys that must be strictly safe (relative,
# non-traversing, no null bytes). These are validated with a strict contract.
_REPO_PATH_KEYS: Tuple[str, ...] = (
    "repository_root",
    "bootstrap_root",
    "project_path",
)


def _resolve_site_adapter_canonical_key(cfg: Mapping[str, Any]) -> str:
    """Return the canonical key name for site adapter for this config.

    If the provided mapping already contains any known canonical variant,
    resolve to that exact key to avoid duplicate state. Otherwise, use the
    default canonical key.
    """
    for k in _SITE_ADAPTER_CANONICAL_CANDIDATES:
        if k in cfg:
            return k
    return _DEFAULT_SITE_ADAPTER_CANONICAL


def _safe_value_equal(a: Any, b: Any) -> bool:
    """Deterministic equality for conflict checks without side effects."""
    return a == b


def _fail_conflict(canonical: str, alias: str) -> None:
    raise ValueError(
        f"configuration conflict for '{canonical}': alias '{alias}' and canonical '{canonical}' differ"
    )


def _sanitize_unknown_keys_message(keys: Set[str]) -> str:
    # Provide a concise, safe reason without echoing sensitive data.
    listing = ", ".join(sorted(keys))
    return f"unknown configuration fields: {listing}"


def _is_absolute_path(p: str) -> bool:
    try:
        return os.path.isabs(p)
    except Exception:
        # Fallback: treat as unsafe if detection fails
        return True


def _contains_null_byte(p: str) -> bool:
    try:
        return "\x00" in p
    except Exception:
        return True


def _has_traversal(p: str) -> bool:
    try:
        norm = os.path.normpath(p).replace("\\", "/")
    except Exception:
        return True
    if norm == "..":
        return True
    if norm.startswith("../"):
        return True
    # Any inner traversal component
    return "/../" in norm or norm.endswith("/..")


def is_unsafe_path(path_value: str) -> Tuple[bool, str]:
    """Check path safety for repository/bootstrap paths.

    Returns a tuple (unsafe, reason_code). The reason_code is one of:
    - 'null_byte'
    - 'absolute'
    - 'traversal'
    - 'invalid'
    """
    if not isinstance(path_value, str) or not path_value:
        return True, "invalid"
    if _contains_null_byte(path_value):
        return True, "null_byte"
    if _is_absolute_path(path_value):
        return True, "absolute"
    if _has_traversal(path_value):
        return True, "traversal"
    return False, ""


def _raise_unsafe_path_error(key: str, reason: str) -> None:
    # Ensure one of the required recognizable terms is present.
    terms = {
        "null_byte": "null byte",
        "absolute": "unsafe_path",
        "traversal": "invalid_path traversal",
        "invalid": "invalid path",
    }
    term = terms.get(reason, "invalid path")
    # Do not echo raw path; keep the message safe and generic.
    raise ValueError(f"{term}: rejected unsafe value for '{key}'")


def validate_repository_paths(cfg: Mapping[str, Any]) -> None:
    """Validate repository/bootstrap path fields.

    Unsafe values raise ValueError with a safe message containing an
    appropriate path-safety term (e.g., 'unsafe_path', 'invalid_path',
    'traversal', or 'null byte').
    """
    for key in _REPO_PATH_KEYS:
        if key in cfg:
            val = cfg[key]
            if val is None:
                continue
            unsafe, reason = is_unsafe_path(str(val))
            if unsafe:
                _raise_unsafe_path_error(key, reason)


def ensure_safe_paths(cfg: Mapping[str, Any]) -> None:
    """Alias for validate_repository_paths for compatibility."""
    validate_repository_paths(cfg)


def _unify_alias(
    src: Mapping[str, Any],
    result: MutableMapping[str, Any],
    alias_key: str,
    canonical_key: str,
) -> None:
    """Move alias value into canonical key with conflict detection.

    - If both alias and canonical are present and conflict, raise ValueError.
    - If only alias is present, place it under canonical.
    - Do not mutate src; only write to result.
    """
    alias_present = alias_key in src
    canonical_present = canonical_key in src

    if alias_present and canonical_present:
        a_val = src.get(alias_key)
        c_val = src.get(canonical_key)
        if not _safe_value_equal(a_val, c_val):
            _fail_conflict(canonical_key, alias_key)
        # If equal, prefer the explicitly canonical key (no duplicate state)
        result[canonical_key] = c_val
        return

    if canonical_present:
        result[canonical_key] = src.get(canonical_key)
        return

    if alias_present:
        result[canonical_key] = src.get(alias_key)


def normalize_and_validate_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a portable bootstrap configuration mapping.

    - Accept both canonical keys and portable aliases.
    - Resolve the site-adapter canonical field dynamically to avoid duplicate
      state when a production variant is already in use.
    - Reject conflicting alias/canonical pairs with ValueError.
    - Reject unknown fields with ValueError.
    - Validate repository/bootstrap paths with safe error messages.
    - Never mutate the input mapping.

    Returns a new dict with canonicalized keys only (except when a production
    canonical site-adapter variant such as 'site_adapter' is already in use;
    in that case that exact key is preserved as canonical).
    """
    if not isinstance(config, Mapping):
        raise TypeError("invalid configuration: expected a mapping")

    # Decide the canonical site-adapter key for this config
    site_canonical = _resolve_site_adapter_canonical_key(config)

    # Build the set of allowed fields for validation (include aliases because
    # they are accepted as inputs, but they will not be present in the output).
    allowed_fields: Set[str] = set(_ALLOWED_FIELDS_BASE)
    allowed_fields.update(_PORTABLE_ALIASES_FIXED.keys())

    # Result dictionary with canonicalized keys only.
    result: Dict[str, Any] = {}

    # First, unify fixed aliases -> canonical
    _unify_alias(config, result, "environment", _PORTABLE_ALIASES_FIXED["environment"])  # type: ignore[index]
    _unify_alias(config, result, "project_id", _PORTABLE_ALIASES_FIXED["project_id"])    # type: ignore[index]
    _unify_alias(config, result, "provider", _PORTABLE_ALIASES_FIXED["provider"])        # type: ignore[index]

    # Next, unify site_adapter alias dynamically to the chosen canonical key.
    # If the chosen canonical key is exactly 'site_adapter', treat that as
    # canonical and do not create duplicate state.
    _unify_alias(config, result, "site_adapter", site_canonical)

    # Now copy through any other canonical fields present in the source. This
    # will not overwrite previously unified values (explicit alias/canonical
    # conflict would have been rejected earlier).
    for key in _ALLOWED_FIELDS_BASE:
        if key in config:
            # Do not duplicate site-adapter state: if this key is one of the
            # canonical variants but not the chosen canonical, ignore it here
            # because a conflict would already have been handled by _unify_alias.
            if key in _SITE_ADAPTER_CANONICAL_CANDIDATES and key != site_canonical:
                continue
            # Skip alias keys; only copy canonical fields
            if key in _PORTABLE_ALIASES_FIXED:
                continue
            # Preserve the chosen canonical site adapter key if present
            if key == site_canonical or key not in _SITE_ADAPTER_CANONICAL_CANDIDATES:
                # Do not overwrite any previously set value for the same key
                if key not in result:
                    result[key] = config.get(key)

    # Unknown fields check: keys present in input that are neither allowed
    # canonical fields nor accepted aliases are rejected.
    unknown: Set[str] = set(config.keys()) - allowed_fields

    # If site adapter canonical differs from default, ensure that canonical is
    # recognized as allowed for this invocation (it is already part of base).
    # Note: already included in _ALLOWED_FIELDS_BASE, but we assert here.
    if site_canonical not in _ALLOWED_FIELDS_BASE:
        # Permit the dynamically chosen canonical key to be considered allowed
        # even if not listed in the static base (defensive measure).
        if site_canonical in unknown:
            unknown.remove(site_canonical)

    if unknown:
        raise ValueError(_sanitize_unknown_keys_message(unknown))

    # Validate repository/bootstrap paths strictly
    validate_repository_paths(result)

    return result


# Backward/forward-compatible aliases for call sites in tests or production
normalize_bootstrap_config = normalize_and_validate_config
validate_and_normalize_config = normalize_and_validate_config


def load_bootstrap_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Compatibility wrapper around normalize_and_validate_config."""
    return normalize_and_validate_config(config)


def join_safe_path(base: str, relative: str) -> str:
    """Join a base directory with a relative repository/bootstrap path safely.

    This helper ensures the joined path does not escape the base via traversal,
    does not contain null bytes, and is not absolute.
    """
    if not isinstance(base, str) or not isinstance(relative, str):
        raise ValueError("invalid path")
    unsafe, reason = is_unsafe_path(relative)
    if unsafe:
        _raise_unsafe_path_error("relative", reason)
    # Safe to join; normalize without resolving symlinks.
    joined = os.path.normpath(os.path.join(base, relative))
    # Final defense: ensure the result remains under the base by comparing
    # normalized paths. We avoid revealing filesystem details in errors.
    try:
        base_norm = os.path.normpath(base)
        # On Windows, casefold for safety without accessing the filesystem
        if os.name == "nt":
            base_norm_cmp = base_norm.casefold()
            joined_cmp = joined.casefold()
        else:
            base_norm_cmp = base_norm
            joined_cmp = joined
        if not (joined_cmp == base_norm_cmp or joined_cmp.startswith(base_norm_cmp + os.sep)):
            _raise_unsafe_path_error("relative", "traversal")
    except Exception:
        _raise_unsafe_path_error("relative", "invalid")
    return joined
