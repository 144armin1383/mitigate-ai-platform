import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.repair.allowlist_recovery import (
    AllowlistRecovery,
    AllowlistDiff,
    DEFAULT_TOKEN_PATTERN,
    update_allowlist_from_events,
    parse_allowlist_text,
    dump_allowlist,
)


class TestAllowlistRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base = Path(self.tempdir.name)
        self.allowlist_path = self.base / "allowlist.txt"

    def _write(self, content: str) -> None:
        self.allowlist_path.write_text(content, encoding="utf-8")

    def _read(self) -> str:
        return self.allowlist_path.read_text(encoding="utf-8")

    def test_parse_and_dump_roundtrip(self):
        content = """
# comment line
svc-alpha

svc-beta  
# another
svc-gamma
""".strip("\n")
        tokens = parse_allowlist_text(content)
        self.assertEqual(tokens, {"svc-alpha", "svc-beta", "svc-gamma"})
        dumped = dump_allowlist(tokens)
        # All tokens present, one per line, sorted and newline terminated
        self.assertTrue(dumped.endswith("\n"))
        self.assertEqual(dumped.splitlines(), sorted(tokens))

    def test_recover_adds_new_valid_entries_only(self):
        self._write("# header\nsvc-alpha\nsvc-beta\n")
        rec = AllowlistRecovery(self.allowlist_path)

        events = [
            "svc-gamma",  # new valid
            "svc-beta",  # duplicate
            "invalid token",  # contains space -> invalid
            "# commented",  # ignored
            {"candidate": "svc-delta"},  # dict form accepted
            {"token": "svc-epsilon"},  # dict form accepted
            {"noop": "ignored"},  # ignored
            "svc-gamma",  # duplicate in events
        ]
        diff = rec.recover_from_events(events, create_backup=False)

        self.assertIsInstance(diff, AllowlistDiff)
        self.assertTrue(diff.changed)
        self.assertEqual(diff.removals, set())
        self.assertSetEqual(diff.additions, {"svc-gamma", "svc-delta", "svc-epsilon"})

        # File content contains all entries, sorted
        content = self._read()
        lines = content.splitlines()
        self.assertEqual(lines, sorted({"svc-alpha", "svc-beta", "svc-gamma", "svc-delta", "svc-epsilon"}))
        self.assertTrue(content.endswith("\n"))

    def test_idempotent_no_changes_does_not_create_backup(self):
        # Start with an existing file
        self._write("svc-alpha\nsvc-beta\n")
        rec = AllowlistRecovery(self.allowlist_path)

        # No new tokens
        backup_ts = "20240101T000000Z"
        diff = rec.recover_from_events(["svc-alpha", "svc-beta"], create_backup=True, timestamp=backup_ts)
        self.assertFalse(diff.changed)
        # No backup created for idempotent operation
        backup_path = self.allowlist_path.with_name(f"{self.allowlist_path.name}.bak.{backup_ts}")
        self.assertFalse(backup_path.exists())

    def test_backup_created_on_change(self):
        initial = "svc-alpha\nsvc-beta\n"
        self._write(initial)
        rec = AllowlistRecovery(self.allowlist_path)

        backup_ts = "20240101T123000Z"
        diff = rec.recover_from_events(["svc-gamma"], create_backup=True, timestamp=backup_ts)
        self.assertTrue(diff.changed)

        backup_path = self.allowlist_path.with_name(f"{self.allowlist_path.name}.bak.{backup_ts}")
        self.assertTrue(backup_path.exists())
        # Backup must contain the original content exactly
        self.assertEqual(backup_path.read_text(encoding="utf-8"), initial)

    def test_custom_validator_is_applied(self):
        # Only tokens beginning with 'svc-' are allowed
        validator = lambda s: s.startswith("svc-")
        rec = AllowlistRecovery(self.allowlist_path, validator=validator)
        diff = rec.recover_from_events(["x", "svc-a", "svc-b"], create_backup=False)
        self.assertTrue(diff.changed)
        self.assertSetEqual(diff.additions, {"svc-a", "svc-b"})

        # Ensure file has only validated tokens, sorted
        lines = self._read().splitlines()
        self.assertEqual(lines, ["svc-a", "svc-b"])  # sorted ordering

    def test_atomic_write_and_ordering(self):
        rec = AllowlistRecovery(self.allowlist_path)
        # Add a collection of tokens in unsorted order
        tokens = ["svc-z", "svc-a", "svc-m", "svc-b"]
        diff = rec.recover_from_events(tokens, create_backup=False)
        self.assertTrue(diff.changed)
        content = self._read()
        lines = content.splitlines()
        self.assertEqual(lines, sorted(set(tokens)))
        self.assertTrue(content.endswith("\n"))

    def test_update_allowlist_from_events_helper(self):
        # Non-existent file should be treated as empty set
        diff = update_allowlist_from_events(self.allowlist_path, ["svc-one", "svc-two"], create_backup=False)
        self.assertTrue(diff.changed)
        self.assertSetEqual(diff.additions, {"svc-one", "svc-two"})

        # Running again with same events is idempotent
        diff2 = update_allowlist_from_events(self.allowlist_path, ["svc-one"], create_backup=False)
        self.assertFalse(diff2.changed)

    def test_invalid_tokens_are_ignored(self):
        rec = AllowlistRecovery(self.allowlist_path)
        # Contains whitespace, too long, or non-matching characters
        too_long = "a" * 65
        events = [
            "valid_token",  # underscore allowed by default pattern
            "invalid token with space",
            "not#allowed",  # contains '#'
            too_long,
            {"candidate": "also_valid"},
        ]
        diff = rec.recover_from_events(events, create_backup=False)
        self.assertTrue(diff.changed)
        self.assertSetEqual(diff.additions, {"valid_token", "also_valid"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
