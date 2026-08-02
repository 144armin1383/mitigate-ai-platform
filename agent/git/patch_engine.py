from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PurePath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import shutil
import io


class PatchError(Exception):
    """Base exception for patch-related errors."""


class PatchSyntaxError(PatchError):
    """Raised when the unified diff syntax is invalid or unsupported."""


class PathSecurityError(PatchError):
    """Raised when a path violates repository path security constraints."""


@dataclass(frozen=True)
class HunkLine:
    kind: str  # 'context', 'add', 'remove'
    text: str  # Text including trailing newline if present


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: Tuple[HunkLine, ...]


@dataclass(frozen=True)
class FilePatch:
    old_path: str
    new_path: str
    hunks: Tuple[Hunk, ...]

    @property
    def is_new_file(self) -> bool:
        # Treat /dev/null or old range 0,0 as new file; range check happens elsewhere
        return self.old_path == "/dev/null"


@dataclass(frozen=True)
class PatchParseResult:
    files: Tuple[FilePatch, ...]


@dataclass
class PatchApplyResult:
    success: bool
    dry_run: bool
    applied_files: List[Path]
    backups: Dict[Path, Path]
    logs: List[str]
    error: Optional[str] = None


class PatchEngine:
    """Production-quality unified diff patch engine with path safety, backups, and rollback.

    Key features:
    - Parse and validate unified diff patches
    - Enforce path security (repo-relative only, reject absolute/traversal)
    - Dry-run simulation without file modifications
    - Atomic per-file updates with automatic backups
    - Rollback on any failure
    - Detailed execution logs

    Python 3.12 compatible, fully typed.
    """

    def __init__(self) -> None:
        self._logs: List[str] = []

    def parse_patch(self, patch_text: str) -> PatchParseResult:
        """Parse unified diff text into a structured representation.

        Supports standard unified diff with '---' and '+++' file headers and '@@' hunks.
        Lines beginning with 'diff --git' or 'index' are tolerated and skipped.

        Raises:
            PatchSyntaxError: if the patch syntax is invalid.
        """
        lines = patch_text.splitlines(keepends=True)
        i = 0
        files: List[FilePatch] = []

        def _parse_range(tok: str) -> Tuple[int, int]:
            # tok like '-l,s' or '+l,s' or '-l' or '+l'
            if not tok:
                raise PatchSyntaxError("Empty range token in hunk header")
            sign = tok[0]
            if sign not in ('-', '+'):
                raise PatchSyntaxError(f"Invalid range sign: {sign}")
            body = tok[1:]
            if not body:
                raise PatchSyntaxError("Missing range body after sign in hunk header")
            if ',' in body:
                start_s, count_s = body.split(',', 1)
                try:
                    start_i = int(start_s)
                    count_i = int(count_s)
                except ValueError as exc:
                    raise PatchSyntaxError("Non-integer range values in hunk header") from exc
            else:
                try:
                    start_i = int(body)
                except ValueError as exc:
                    raise PatchSyntaxError("Non-integer start value in hunk header") from exc
                count_i = 1
            return start_i, count_i

        while i < len(lines):
            line = lines[i]
            # Skip non-essential lines until we find a file header '--- '
            if line.startswith('diff --git') or line.startswith('index ') or line.startswith('new file mode') or line.startswith('deleted file mode'):
                i += 1
                continue
            if not line.startswith('--- '):
                i += 1
                continue

            # Parse file header
            old_line = line.rstrip('\n')
            i += 1
            if i >= len(lines):
                raise PatchSyntaxError("Unexpected EOF after '---' header")
            if not lines[i].startswith('+++ '):
                raise PatchSyntaxError("Missing '+++' header after '---'")
            new_line = lines[i].rstrip('\n')
            i += 1

            old_path = old_line[4:].strip()
            new_path = new_line[4:].strip()

            hunks: List[Hunk] = []

            # Parse hunks for this file until next file header or EOF
            while i < len(lines):
                l = lines[i]
                if l.startswith('@@ '):
                    header = l.strip()
                    # Format: @@ -l,s +l,s @@ optional section
                    # Extract the '-l,s +l,s' part between '@@' pairs
                    if not header.endswith('@@'):
                        # It may have trailing context after @@; we only need the middle part
                        pass
                    # Strip leading '@@ ' and split by ' @@'
                    if header.count('@@') < 2:
                        # Handle cases where context text exists: starts with '@@ ' and contains ' @@'
                        # We'll find the second '@@'
                        try:
                            second_at = header.index('@@', 3)
                        except ValueError as exc:
                            raise PatchSyntaxError("Malformed hunk header '@@'") from exc
                        core = header[3:second_at].strip()
                    else:
                        # header like '@@ -a,b +c,d @@'
                        parts = header.split('@@')
                        # parts: ['', ' -a,b +c,d ', ''] or with trailing context
                        core = parts[1].strip()
                    # core now expected '-l,s +l,s'
                    core_parts = core.split()
                    if len(core_parts) < 2:
                        raise PatchSyntaxError("Invalid hunk header ranges")
                    old_range = core_parts[0]
                    new_range = core_parts[1]
                    old_start, old_count = _parse_range(old_range)
                    new_start, new_count = _parse_range(new_range)
                    i += 1

                    hunk_lines: List[HunkLine] = []
                    while i < len(lines):
                        hl = lines[i]
                        if hl.startswith('@@ '):
                            break
                        if hl.startswith('--- ') and not hl.startswith('--- ' + '\\ No newline'):
                            break
                        if hl.startswith('diff --git'):
                            break
                        if hl.startswith('\\ No newline at end of file'):
                            # Sentinel; ignore for content building
                            i += 1
                            continue
                        if not hl:
                            i += 1
                            continue
                        marker = hl[0]
                        if marker not in (' ', '+', '-'):
                            raise PatchSyntaxError("Invalid hunk line marker; expected ' ', '+', or '-'")
                        content = hl[1:]
                        kind = 'context' if marker == ' ' else ('add' if marker == '+' else 'remove')
                        hunk_lines.append(HunkLine(kind=kind, text=content))
                        i += 1
                    hunks.append(Hunk(old_start=old_start, old_count=old_count, new_start=new_start, new_count=new_count, lines=tuple(hunk_lines)))
                    continue
                # Next file header or unrelated line ends hunk parsing for this file
                if l.startswith('--- ') or l.startswith('diff --git'):
                    break
                # Skip stray lines between hunks (should not normally occur)
                i += 1

            files.append(FilePatch(old_path=old_path, new_path=new_path, hunks=tuple(hunks)))

        if not files:
            raise PatchSyntaxError("No file headers ('---'/'+++') found in patch")

        return PatchParseResult(files=tuple(files))

    @staticmethod
    def _normalize_patch_path(path_text: str) -> str:
        """Normalize diff path by dropping 'a/' or 'b/' prefixes commonly used in git diffs."""
        # /dev/null should be preserved as-is
        if path_text == '/dev/null':
            return path_text
        p = path_text.strip()
        # Git diffs typically use a/ and b/ prefixes
        if p.startswith('a/') or p.startswith('b/'):
            p = p[2:]
        return p

    @staticmethod
    def _validate_repo_relative(repo_root: Path, rel_path: str) -> Path:
        """Validate that rel_path is repository-relative and secure.

        - Reject absolute paths
        - Reject path traversal ('..')
        - Ensure final path is within repo_root
        """
        # Normalize using POSIX style then convert to OS path semantics
        if rel_path == '/dev/null':
            raise PathSecurityError("/dev/null is not a repository path for new file header; use valid repo-relative path in '+++'.")

        posix = PurePosixPath(rel_path)
        # Reject absolute or drive-like absolute (Path.is_absolute covers both on respective OS)
        if str(posix).startswith('/'):
            raise PathSecurityError(f"Absolute paths are not allowed: {rel_path}")
        # Reject traversal
        if any(part == '..' for part in posix.parts):
            raise PathSecurityError(f"Path traversal is not allowed: {rel_path}")
        # Normalize '.' components
        safe_rel = PurePosixPath('.') / posix
        # Convert to native path under repo_root without resolving symlinks
        candidate = repo_root.joinpath(*safe_rel.parts[1:]) if safe_rel.parts and safe_rel.parts[0] == '.' else repo_root.joinpath(*safe_rel.parts)
        # Ensure candidate is within repo_root by checking path parts prefix (no FS resolve to avoid side effects)
        # Using PurePath for comparison keeps it static
        root_parts = PurePath(repo_root).parts
        cand_parts = PurePath(candidate).parts
        if len(cand_parts) < len(root_parts) or cand_parts[: len(root_parts)] != root_parts:
            raise PathSecurityError(f"Resolved path escapes repository root: {rel_path}")
        return candidate

    def _generate_backup_path(self, target: Path) -> Path:
        base = target.with_name(target.name + '.bak')
        if not base.exists():
            return base
        # Find next available numeric suffix deterministically
        n = 1
        while True:
            cand = target.with_name(f"{target.name}.bak{n}")
            if not cand.exists():
                return cand
            n += 1

    def apply(self, patch_text: str, repo_root: Path, dry_run: bool = False) -> PatchApplyResult:
        """Apply a unified diff patch to files under repo_root.

        Path security is validated before any file content is accessed or modified.

        Args:
            patch_text: Unified diff text.
            repo_root: Root directory of the repository.
            dry_run: If True, simulate without writing any changes.

        Returns:
            PatchApplyResult with logs, backups mapping, and status.

        Raises:
            PatchError: For any failure condition.
        """
        self._logs = []
        self._logs.append("Starting patch application")
        parse_result = self.parse_patch(patch_text)

        # Path security validation must take precedence
        self._logs.append("Validating file paths for security")
        normalized: List[Tuple[FilePatch, Optional[Path], Optional[Path]]] = []
        for fp in parse_result.files:
            old_path_norm = self._normalize_patch_path(fp.old_path)
            new_path_norm = self._normalize_patch_path(fp.new_path)

            # Validate new path if not /dev/null
            new_target: Optional[Path] = None
            old_target: Optional[Path] = None
            if old_path_norm != '/dev/null':
                old_target = self._validate_repo_relative(repo_root, old_path_norm)
            if new_path_norm != '/dev/null':
                new_target = self._validate_repo_relative(repo_root, new_path_norm)

            # Ensure at least one side is a repo path
            if old_target is None and new_target is None:
                raise PathSecurityError("Neither old nor new path refers to a repository-relative file")

            normalized.append((fp, old_target, new_target))

        # After path validation, proceed to verify and possibly apply
        backups: Dict[Path, Path] = {}
        applied_files: List[Path] = []

        try:
            if dry_run:
                self._logs.append("Dry-run mode: Verifying applicability without changes")
                for fp, old_t, new_t in normalized:
                    if fp.is_new_file:
                        if new_t is None:
                            raise PatchError("New file patch missing '+++' target path")
                        if new_t.exists():
                            raise PatchError(f"New file already exists: {new_t}")
                        # Validate hunk content: only additions allowed
                        for h in fp.hunks:
                            for hl in h.lines:
                                if hl.kind != 'add':
                                    raise PatchError("New-file hunks must contain only additions")
                        self._logs.append(f"Would create new file: {new_t}")
                    else:
                        # Modify existing file
                        target = old_t if old_t is not None else new_t
                        if target is None:
                            raise PatchError("Missing target path for modification")
                        if not target.exists():
                            raise PatchError(f"Target file does not exist: {target}")
                        # Verify hunks match
                        original = self._read_file_lines(target)
                        _ = self._apply_hunks_preview(original, fp.hunks, target)
                        self._logs.append(f"Would modify file: {target}")
                return PatchApplyResult(success=True, dry_run=True, applied_files=[], backups={}, logs=self._logs.copy())

            # Not dry-run: perform backups and apply atomically
            # Stage: verify all hunks first to fail-fast before writing
            self._logs.append("Pre-verifying all hunks before applying changes")
            previews: Dict[Path, List[str]] = {}
            for fp, old_t, new_t in normalized:
                if fp.is_new_file:
                    if new_t is None:
                        raise PatchError("New file patch missing '+++' target path")
                    if new_t.exists():
                        raise PatchError(f"New file already exists: {new_t}")
                    # Build new content from added lines
                    new_lines = self._build_new_file_lines(fp.hunks)
                    previews[new_t] = new_lines
                else:
                    target = old_t if old_t is not None else new_t
                    if target is None:
                        raise PatchError("Missing target path for modification")
                    if not target.exists():
                        raise PatchError(f"Target file does not exist: {target}")
                    original = self._read_file_lines(target)
                    new_lines = self._apply_hunks_preview(original, fp.hunks, target)
                    previews[target] = new_lines

            # Stage: write with backups atomically per file
            for fp, old_t, new_t in normalized:
                if fp.is_new_file:
                    assert new_t is not None
                    target = new_t
                    # Ensure parent exists
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # Write to temp file then move
                    self._write_atomic(target, previews[target])
                    applied_files.append(target)
                    self._logs.append(f"Created new file: {target}")
                else:
                    target = (old_t if old_t is not None else new_t)
                    assert target is not None
                    # Backup
                    backup_path = self._generate_backup_path(target)
                    # Ensure parent exists (should already)
                    if not target.exists():
                        raise PatchError(f"Target file disappeared: {target}")
                    shutil.copy2(target, backup_path)
                    backups[target] = backup_path
                    self._logs.append(f"Backed up {target} -> {backup_path}")
                    # Write temp then replace
                    self._write_atomic(target, previews[target])
                    applied_files.append(target)
                    self._logs.append(f"Modified file: {target}")

            self._logs.append("Patch application completed successfully")
            return PatchApplyResult(success=True, dry_run=False, applied_files=applied_files, backups=backups, logs=self._logs.copy())

        except Exception as exc:  # Rollback on any failure
            self._logs.append(f"Error encountered: {exc}. Initiating rollback.")
            # Restore backups
            for tgt, bkp in backups.items():
                try:
                    if bkp.exists():
                        shutil.copy2(bkp, tgt)
                        self._logs.append(f"Restored backup for {tgt} from {bkp}")
                except Exception as rex:
                    self._logs.append(f"Failed to restore backup for {tgt}: {rex}")
            # Remove any newly created files that have no backup
            for f in applied_files:
                if f not in backups and f.exists():
                    try:
                        f.unlink()
                        self._logs.append(f"Removed newly created file during rollback: {f}")
                    except Exception as dex:
                        self._logs.append(f"Failed to remove newly created file {f}: {dex}")
            return PatchApplyResult(success=False, dry_run=dry_run, applied_files=applied_files, backups=backups, logs=self._logs.copy(), error=str(exc))

    @staticmethod
    def _read_file_lines(path: Path) -> List[str]:
        # Read file preserving line endings
        data = path.read_bytes()
        # Attempt UTF-8; if fails, fall back to latin-1 to keep bytes mapping stable
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('latin-1')
        return text.splitlines(keepends=True)

    @staticmethod
    def _write_atomic(target: Path, lines: Sequence[str]) -> None:
        # Write to a temporary in the same directory then replace
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        tmp = parent / (target.name + '.tmp_patch')
        # Ensure tmp does not collide
        idx = 0
        while tmp.exists():
            idx += 1
            tmp = parent / (target.name + f'.tmp_patch{idx}')
        text = ''.join(lines)
        # Use same encoding assumption as read: write UTF-8
        tmp.write_text(text, encoding='utf-8', newline='')
        # Move to target atomically where possible
        tmp.replace(target)

    @staticmethod
    def _build_new_file_lines(hunks: Sequence[Hunk]) -> List[str]:
        result: List[str] = []
        for h in hunks:
            for hl in h.lines:
                if hl.kind != 'add':
                    raise PatchError("New-file hunks must contain only additions")
                result.append(hl.text)
        return result

    @staticmethod
    def _apply_hunks_preview(original: Sequence[str], hunks: Sequence[Hunk], target: Path) -> List[str]:
        # Validate hunks match original content and produce new content without writing
        new_content: List[str] = []
        old_index = 0  # 0-based index in original
        for h in hunks:
            # Copy unchanged content before this hunk
            h_start_index = max(h.old_start - 1, 0)
            if h_start_index < old_index:
                raise PatchError(f"Overlapping hunks detected for {target}")
            # Bounds check
            if h_start_index > len(original):
                raise PatchError(f"Hunk start beyond end of file for {target}")
            new_content.extend(original[old_index:h_start_index])
            cursor = h_start_index
            # Validate hunk line counts loosely according to unified diff semantics
            old_consumed = 0
            new_produced = 0
            for hl in h.lines:
                if hl.kind == 'context':
                    if cursor >= len(original) or original[cursor] != hl.text:
                        raise PatchError(f"Context mismatch when applying hunk to {target}")
                    new_content.append(hl.text)
                    cursor += 1
                    old_consumed += 1
                    new_produced += 1
                elif hl.kind == 'remove':
                    if cursor >= len(original) or original[cursor] != hl.text:
                        raise PatchError(f"Removal line mismatch when applying hunk to {target}")
                    cursor += 1
                    old_consumed += 1
                elif hl.kind == 'add':
                    new_content.append(hl.text)
                    new_produced += 1
                else:
                    raise PatchError("Unknown hunk line kind")
            old_index = cursor
            # Optional strict count check: if counts provided, validate they match consumed/produced
            if h.old_count != 0 and old_consumed != h.old_count:
                # Allow some diffs omit strict counts; however we enforce for correctness
                raise PatchError(f"Old line count mismatch in hunk for {target} (expected {h.old_count}, got {old_consumed})")
            if h.new_count != 0 and new_produced != h.new_count:
                raise PatchError(f"New line count mismatch in hunk for {target} (expected {h.new_count}, got {new_produced})")
        # Append remaining original content after last hunk
        new_content.extend(original[old_index:])
        return new_content


__all__ = [
    "PatchEngine",
    "PatchError",
    "PatchSyntaxError",
    "PathSecurityError",
    "PatchApplyResult",
]
