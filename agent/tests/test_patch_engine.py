from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from agent.git.patch_engine import PatchEngine, PatchError, PatchSyntaxError, PathSecurityError


class TestPatchEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PatchEngine()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.repo = Path(self.tmpdir.name)

    def write_file(self, rel: str, content: str) -> Path:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p

    def read_file(self, rel: str) -> str:
        p = self.repo / rel
        return p.read_text(encoding='utf-8')

    def test_modify_existing_file(self) -> None:
        # Prepare a file
        self.write_file('file.txt', 'hello\nworld\n')
        # Unified diff to change 'world' to 'there'
        patch = (
            '--- a/file.txt\n'
            '+++ b/file.txt\n'
            '@@ -1,2 +1,2 @@\n'
            ' hello\n'
            '-world\n'
            '+there\n'
        )
        res = self.engine.apply(patch, self.repo, dry_run=False)
        self.assertTrue(res.success)
        self.assertFalse(res.dry_run)
        # Content updated
        self.assertEqual(self.read_file('file.txt'), 'hello\nthere\n')
        # Backup created
        backups = list(res.backups.values())
        self.assertTrue(any(b.exists() for b in backups))

    def test_dry_run_no_changes(self) -> None:
        self.write_file('a.txt', 'one\ntwo\n')
        patch = (
            '--- a/a.txt\n'
            '+++ b/a.txt\n'
            '@@ -1,2 +1,2 @@\n'
            ' one\n'
            '-two\n'
            '+dos\n'
        )
        res = self.engine.apply(patch, self.repo, dry_run=True)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        # File unchanged
        self.assertEqual(self.read_file('a.txt'), 'one\ntwo\n')

    def test_reject_absolute_paths(self) -> None:
        # Ensure absolute path rejected before any access
        patch = (
            '--- /etc/passwd\n'
            '+++ /etc/passwd\n'
            '@@ -1,1 +1,1 @@\n'
            '-root\n'
            '+user\n'
        )
        with self.assertRaises(PathSecurityError):
            self.engine.apply(patch, self.repo, dry_run=True)

    def test_reject_path_traversal(self) -> None:
        patch = (
            '--- a/../evil.txt\n'
            '+++ b/../evil.txt\n'
            '@@ -1,1 +1,1 @@\n'
            '-bad\n'
            '+worse\n'
        )
        with self.assertRaises(PathSecurityError):
            self.engine.apply(patch, self.repo, dry_run=False)

    def test_new_file_creation_with_zero_zero_hunk(self) -> None:
        # Create new file using @@ -0,0 +1,2 @@
        patch = (
            '--- /dev/null\n'
            '+++ b/newdir/new.txt\n'
            '@@ -0,0 +1,2 @@\n'
            '+alpha\n'
            '+beta\n'
        )
        res = self.engine.apply(patch, self.repo, dry_run=False)
        self.assertTrue(res.success)
        self.assertTrue((self.repo / 'newdir' / 'new.txt').exists())
        self.assertEqual((self.repo / 'newdir' / 'new.txt').read_text(encoding='utf-8'), 'alpha\nbeta\n')

    def test_new_file_creation_rejected_if_exists(self) -> None:
        self.write_file('exists.txt', 'present\n')
        patch = (
            '--- /dev/null\n'
            '+++ b/exists.txt\n'
            '@@ -0,0 +1,1 @@\n'
            '+present\n'
        )
        res = self.engine.apply(patch, self.repo, dry_run=False)
        self.assertFalse(res.success)
        self.assertIn('already exists', res.error or '')
        # Ensure original content unchanged
        self.assertEqual(self.read_file('exists.txt'), 'present\n')

    def test_rollback_on_failure_keeps_originals(self) -> None:
        # Two files; second will fail due to mismatch
        self.write_file('f1.txt', 'A\nB\nC\n')
        self.write_file('f2.txt', 'X\nY\nZ\n')
        patch = (
            '--- a/f1.txt\n'
            '+++ b/f1.txt\n'
            '@@ -1,3 +1,3 @@\n'
            ' A\n'
            '-B\n'
            '+BB\n'
            ' C\n'
            '--- a/f2.txt\n'
            '+++ b/f2.txt\n'
            '@@ -1,3 +1,3 @@\n'
            ' X\n'
            '-Y\n'
            '+QQ\n'
            ' C\n'
        )
        res = self.engine.apply(patch, self.repo, dry_run=False)
        self.assertFalse(res.success)
        # Verify both files retain original contents due to rollback
        self.assertEqual(self.read_file('f1.txt'), 'A\nB\nC\n')
        self.assertEqual(self.read_file('f2.txt'), 'X\nY\nZ\n')

    def test_syntax_error_when_missing_headers(self) -> None:
        invalid_patch = (
            'diff --git a/a.txt b/a.txt\n'
            '@@ -1,1 +1,1 @@\n'
            '-x\n'
            '+y\n'
        )
        with self.assertRaises(PatchSyntaxError):
            self.engine.parse_patch(invalid_patch)


if __name__ == '__main__':
    unittest.main()
