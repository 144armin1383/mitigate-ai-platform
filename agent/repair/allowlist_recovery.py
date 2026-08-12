from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Iterable, Optional, Sequence, Set, Union

# Public API
__all__ = [
    "AllowlistRecovery",
    "AllowlistDiff",
    "update_allowlist_from_events",
    "DEFAULT_TOKEN_PATTERN",
]

# Default pattern: conservative set of characters suitable for identifiers and host-like tokens.
# - Alphanumerics
# - Dot, underscore, dash, colon
# Length: 1..64 to prevent abuse and pathological file growth.
DEFAULT_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class AllowlistRecoveryError(Exception):
    """Raised for allowlist recovery related errors."""


@dataclass(frozen=True)
class AllowlistDiff:
    """Represents the change between two allowlist states."""

    additions: Set[str]
    removals: Set[str]

    @property
    def changed(self) -> bool:  # pragma: no cover - trivial property
        return bool(self.additions or self.removals)


def _normalize_line(line: str) -> str:
    """Normalize lines by stripping whitespace and removing trailing carriage returns.

    This is intentionally conservative: we do not transform case or perform any
    Unicode normalization to avoid accidental token mutation.
    """
    return line.strip().replace("\r", "")


def parse_allowlist_text(text: str) -> Set[str]:
    """Parse allowlist content into a set of tokens.

    - Ignores blank lines and comments beginning with '#'.
    - Tokens must not contain whitespace.

    Returns a set of tokens in the file (order not preserved).
    """
    tokens: Set[str] = set()
    for raw in text.splitlines():
        line = _normalize_line(raw)
        if not line or line.startswith("#"):
            continue
        # Reject inline comments to avoid ambiguous parsing; callers should supply pure tokens per line.
        if any(ch.isspace() for ch in line):
            continue
        tokens.add(line)
    return tokens


def dump_allowlist(tokens: Set[str]) -> str:
    """Serialize a set of tokens to canonical allowlist text.

    - Sorted lexicographically for deterministic diffs
    - One token per line
    - Always ends with a single trailing newline
    """
    ordered = sorted(tokens)
    return "\n".join(ordered) + ("\n" if ordered or tokens is not None else "")


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text content to a file.

    Writes to a temporary file in the same directory and replaces the target path.
    Ensures the operation is as atomic as the host filesystem supports.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create a named temporary file in the same directory for atomic replace
    with NamedTemporaryFile("w", delete=False, dir=str(path.parent), prefix=f".{path.name}.tmp-", encoding="utf-8") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    # Replace the destination atomically
    os.replace(str(tmp_path), str(path))


def _make_backup_path(path: Path, timestamp: str) -> Path:
    # Backup alongside the original, do not alter suffixes unexpectedly.
    # Example: allowlist.txt -> allowlist.txt.bak.20240101T000000Z
    return path.with_name(f"{path.name}.bak.{timestamp}")


class AllowlistRecovery:
    """Allowlist self-healing and recovery utilities.

    This component assists with safely adding valid tokens discovered from events
    to an allowlist file. It provides:
    - Parsing and canonical serialization of allowlist files
    - Validation of candidate tokens via a regex or custom callable
    - Atomic writes to avoid torn files
    - Optional backups on change
    - Deterministic ordering for reproducible diffs
    """

    def __init__(
        self,
        path: Union[str, Path],
        *,
        validator: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.path = Path(path)
        self._validator = validator if validator is not None else (lambda s: bool(DEFAULT_TOKEN_PATTERN.match(s)))

    # ----------------------- File IO -----------------------
    def load_allowlist(self) -> Set[str]:
        if not self.path.exists():
            return set()
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            raise AllowlistRecoveryError(f"Failed to read allowlist: {self.path}") from exc
        return parse_allowlist_text(text)

    def save_allowlist(self, tokens: Set[str]) -> None:
        content = dump_allowlist(tokens)
        try:
            _atomic_write_text(self.path, content)
        except OSError as exc:  # pragma: no cover - defensive
            raise AllowlistRecoveryError(f"Failed to write allowlist: {self.path}") from exc

    def backup_allowlist(self, timestamp: str) -> Path:
        if not timestamp or not re.match(r"^\d{8}T\d{6}Z$", timestamp):
            raise AllowlistRecoveryError("Timestamp must be in UTC compact format: YYYYMMDDTHHMMSSZ")
        if not self.path.exists():
            # Nothing to backup
            return _make_backup_path(self.path, timestamp)
        backup_path = _make_backup_path(self.path, timestamp)
        try:
            # Copy via read/write to avoid shutil dependency and to be explicit
            content = self.path.read_text(encoding="utf-8")
            _atomic_write_text(backup_path, content)
        except OSError as exc:  # pragma: no cover - defensive
            raise AllowlistRecoveryError(f"Failed to create backup: {backup_path}") from exc
        return backup_path

    # ----------------------- Recovery logic -----------------------
    def _extract_candidates(self, events: Iterable[Union[str, dict]]) -> Set[str]:
        candidates: Set[str] = set()
        for ev in events:
            if isinstance(ev, str):
                val = _normalize_line(ev)
                if val and not val.startswith("#") and not any(ch.isspace() for ch in val):
                    candidates.add(val)
            elif isinstance(ev, dict):
                # Accept common keys for a token candidate
                for key in ("candidate", "token", "value", "id"):
                    if key in ev and isinstance(ev[key], str):
                        val = _normalize_line(ev[key])
                        if val and not any(ch.isspace() for ch in val):
                            candidates.add(val)
                            break
        return candidates

    def recover_from_events(
        self,
        events: Iterable[Union[str, dict]],
        *,
        create_backup: bool = True,
        timestamp: Optional[str] = None,
    ) -> AllowlistDiff:
        """Recover allowlist entries from events, writing changes if needed.

        - Extract candidate tokens from the provided events
        - Validate tokens using the configured validator
        - Add only new, valid tokens
        - Optionally create a backup before writing changes (only if there are changes)

        Returns an AllowlistDiff describing what changed.
        """
        current = self.load_allowlist()
        candidates = self._extract_candidates(events)
        valid_new = {tok for tok in candidates if self._validator(tok)} - current

        if not valid_new:
            return AllowlistDiff(additions=set(), removals=set())

        if create_backup and self.path.exists():
            if timestamp is None:
                # Deterministic timestamps are recommended for tests; if not provided, use UTC compact now.
                # Use time.strftime without importing timezones to keep dependencies minimal.
                from datetime import datetime, timezone

                ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            else:
                ts = timestamp
            self.backup_allowlist(ts)

        new_tokens = set(current)
        new_tokens.update(valid_new)
        self.save_allowlist(new_tokens)

        return AllowlistDiff(additions=valid_new, removals=set())


def update_allowlist_from_events(
    path: Union[str, Path],
    events: Iterable[Union[str, dict]],
    *,
    validator: Optional[Callable[[str], bool]] = None,
    create_backup: bool = True,
    timestamp: Optional[str] = None,
) -> AllowlistDiff:
    """Convenience function to recover and update an allowlist file from events.

    Parameters
    - path: Path to the allowlist file to update
    - events: Iterable of string lines or dicts containing candidate tokens
    - validator: Optional callable to validate tokens; defaults to DEFAULT_TOKEN_PATTERN
    - create_backup: Whether to create a backup before writing changes
    - timestamp: Optional UTC compact timestamp for backup naming (YYYYMMDDTHHMMSSZ)

    Returns
    - AllowlistDiff describing changes applied
    """
    rec = AllowlistRecovery(path, validator=validator)
    return rec.recover_from_events(events, create_backup=create_backup, timestamp=timestamp)
