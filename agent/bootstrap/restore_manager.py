from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

__all__ = [
    "RestoreManager",
]


class RestoreManager:
    """
    Portable restore manager with explicit sensitive-material safety.

    Sensitive material is excluded from portable restore data.

    This module is safe to import via a normal package import or through a direct
    importlib spec-loader execution. It performs deterministic path validation and
    filtering, and it never attempts any provider connectivity, network calls, or
    execution of external tools.

    Safety contract:
    - Sensitive material is rejected during validation and excluded during apply.
    - The following are not persisted:
      * authentication material
      * provider access material
      * authorization data
      * private runtime configuration
      * raw provider responses
    - Existing detection and filtering behavior is preserved semantically by using
      conservative keyword- and path-based exclusion.
    """

    # Keywords that indicate sensitive values (case-insensitive key match)
    SENSITIVE_KEYWORDS: Tuple[str, ...] = (
        "api_key",
        "apikey",
        "token",
        "access_token",
        "authorization",
        "auth",
        "secret",
        "password",
        "private",
        "credential",
        "credentials",
        "session",
        "cookie",
        "signature",
        "key",
        # provider prefixed common forms
        "provider_api_key",
        "provider_token",
        "provider_secret",
    )

    # Paths that are always excluded from portable restore
    EXCLUDED_PATH_PATTERNS: Tuple[str, ...] = (
        ".env",
        ".env.local",
        ".env.production",
        "env.local",
        "secrets.json",
        "auth.json",
        "credentials.json",
        "private.conf",
        "private.json",
        "provider.json",
        "provider_secrets.json",
        "runtime_auth.json",
        # any file under hidden .private or .secrets directories
        ".private/",
        ".secrets/",
    )

    def __init__(self, repository_root: Optional[Path | str] = None) -> None:
        root = Path(repository_root) if repository_root is not None else Path.cwd()
        self._root = root.resolve()

    @property
    def repository_root(self) -> Path:
        return self._root

    # Public API: validate a payload for restore
    def validate_restore_payload(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Validate restore payload structure and detect sensitive material.

        Returns a structured mapping describing validation findings. No files are written.
        Sensitive keys or excluded paths cause ok=False unless they are cleanly filtered
        (see apply_restore which excludes them on write). This ensures callers are aware
        that additional configuration is required to complete a production restore.
        """
        rejected_keys: List[str] = []
        sensitive_paths: List[str] = []

        # Key-based scan for sensitive material (recursive)
        def scan(obj: Any, path: str = "$") -> None:
            if isinstance(obj, Mapping):
                for k, v in obj.items():
                    if self._is_sensitive_key(k):
                        rejected_keys.append(f"{path}.{k}")
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for idx, v in enumerate(obj):
                    scan(v, f"{path}[{idx}]")

        scan(payload)

        # Path-based scan if payload declares files to restore
        files_mapping = payload.get("files") if isinstance(payload, Mapping) else None
        if isinstance(files_mapping, Mapping):
            for rel in files_mapping.keys():
                if self._is_excluded_path(str(rel)):
                    sensitive_paths.append(str(rel))

        ok = not rejected_keys and not sensitive_paths
        return {
            "ok": ok,
            "sensitive_keys_detected": sorted(set(rejected_keys)),
            "sensitive_paths_detected": sorted(set(sensitive_paths)),
            "message": (
                "Sensitive material detected and must be excluded before restore."
                if not ok
                else "Payload is structurally valid for portable restore."
            ),
        }

    # Public API: apply a restore in a portable-safe manner
    def apply_restore(self, payload: Mapping[str, Any], target_dir: Path | str, *, validation_only: bool = False) -> Dict[str, Any]:
        """
        Apply a portable restore into target_dir using a filtered view of payload.

        Sensitive material is excluded from portable restore data. Keys deemed
        sensitive are removed and excluded paths are skipped. When validation_only
        is True, no files are written and only the filtering summary is returned.
        """
        target = Path(target_dir).resolve()
        filtered, excluded_keys = self._filter_sensitive(payload)
        excluded_paths: List[str] = []

        # Always validate paths and never write excluded ones
        files_mapping = filtered.get("files") if isinstance(filtered, Mapping) else None
        if isinstance(files_mapping, Mapping) and not validation_only:
            for rel, content in files_mapping.items():
                rel_path = Path(str(rel))
                if self._is_excluded_path(str(rel_path)):
                    excluded_paths.append(str(rel_path))
                    continue
                safe_abs = self._safe_target_path(target, rel_path)
                if safe_abs is None:
                    # Unsafe path is treated as excluded
                    excluded_paths.append(str(rel_path))
                    continue
                # Write text content deterministically
                safe_abs.parent.mkdir(parents=True, exist_ok=True)
                data = content if isinstance(content, (str, bytes)) else json.dumps(content, separators=(",", ":"))
                if isinstance(data, str):
                    data_bytes = data.encode("utf-8")
                else:
                    data_bytes = data
                with open(safe_abs, "wb") as f:
                    f.write(data_bytes)

        return {
            "ok": True,
            "excluded_keys": sorted(excluded_keys),
            "excluded_paths": sorted(set(excluded_paths)),
        }

    # Internal helpers
    def _is_sensitive_key(self, key: str) -> bool:
        k = key.lower().strip()
        for token in self.SENSITIVE_KEYWORDS:
            if token in k:
                return True
        return False

    def _is_excluded_path(self, rel: str) -> bool:
        p = rel.replace("\\", "/").strip()
        if not p:
            return True
        if p.startswith("/"):
            return True
        if ".." in Path(p).parts:
            return True
        for pat in self.EXCLUDED_PATH_PATTERNS:
            if pat.endswith("/"):
                if f"/{pat}".replace("//", "/").strip("/") in p.strip("/"):
                    return True
                if p.startswith(pat):
                    return True
            else:
                if p == pat or p.endswith("/" + pat) or p.startswith(pat + "/"):
                    return True
        return False

    def _filter_sensitive(self, payload: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Return a deep-copied filtered payload and the list of excluded key paths."""
        excluded: List[str] = []

        def recurse(obj: Any, path: str = "$") -> Any:
            if isinstance(obj, Mapping):
                out: Dict[str, Any] = {}
                for k, v in obj.items():
                    if self._is_sensitive_key(k):
                        excluded.append(f"{path}.{k}")
                        continue
                    out[k] = recurse(v, f"{path}.{k}")
                return out
            elif isinstance(obj, list):
                return [recurse(v, f"{path}[]") for v in obj]
            else:
                return obj

        filtered = recurse(payload)
        # Additionally scrub excluded paths from any declared files section
        files_mapping = filtered.get("files") if isinstance(filtered, Mapping) else None
        if isinstance(files_mapping, Mapping):
            safe_files: Dict[str, Any] = {}
            for rel, content in files_mapping.items():
                if self._is_excluded_path(str(rel)):
                    excluded.append(f"$.files[{rel}]")
                    continue
                safe_files[str(rel)] = content
            filtered = dict(filtered)
            filtered["files"] = safe_files
        return filtered, excluded

    @staticmethod
    def _safe_target_path(base: Path, relative: Path) -> Optional[Path]:
        try:
            candidate = (base / relative).resolve()
        except Exception:
            return None
        try:
            base_resolved = base.resolve()
        except Exception:
            return None
        # Ensure candidate is inside base directory
        try:
            candidate.relative_to(base_resolved)
        except Exception:
            return None
        return candidate
