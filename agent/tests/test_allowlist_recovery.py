# Copyright (c) MITIGATE
# SPDX-License-Identifier: MIT

import json
import os
import unittest

from agent.repair.allowlist_recovery import classify_generated_path


class TestAllowlistRecovery(unittest.TestCase):
    def setUp(self) -> None:
        # Declared deliverables for this mission; order intentionally unsorted
        self.allowed_paths = [
            "docs/architecture/autonomous-self-healing-allowlist-recovery-v2.json",
            "agent/tests/test_allowlist_recovery.py",
            "agent/repair/allowlist_recovery.py",
        ]

    def test_declared_path_allowed(self):
        result = classify_generated_path(
            "agent/repair/allowlist_recovery.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertTrue(result["allowed"])  # allowed True
        self.assertEqual(result["classification"], "allowed")
        self.assertIn("agent/repair/allowlist_recovery.py", result["allowed_paths"])  # canonical includes

    def test_undeclared_path_rejected(self):
        result = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertFalse(result["allowed"])  # not allowed
        self.assertEqual(result["classification"], "outside_allowlist")
        self.assertTrue(result["safely_repairable"])  # ordinary mismatch => safely repairable
        self.assertFalse(result["human_approval_required"])  # does not require human approval

    def test_mitigate_autonomy_path_rejected(self):
        result = classify_generated_path(
            "mitigate/autonomy/example.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "outside_allowlist")
        self.assertFalse(result["allowed"])  # not allowed

    def test_mitigate_self_healing_path_rejected(self):
        result = classify_generated_path(
            "mitigate/self_healing/patch.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "outside_allowlist")
        self.assertFalse(result["allowed"])  # not allowed

    def test_absolute_path_rejected(self):
        result = classify_generated_path(
            "/etc/passwd",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "absolute_path")
        self.assertFalse(result["allowed"])  # not allowed
        self.assertFalse(result["safely_repairable"])  # dangerous => not safely repairable

    def test_traversal_rejected(self):
        result = classify_generated_path(
            "../agent/repair/x.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "repository_escape")
        self.assertFalse(result["allowed"])  # not allowed
        self.assertFalse(result["safely_repairable"])  # dangerous

    def test_protected_core_target_rejected(self):
        # Built-in protected core
        result = classify_generated_path(
            "agent/ai/mission_runner.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "protected_core")
        self.assertFalse(result["allowed"])  # not allowed
        self.assertTrue(result["human_approval_required"])  # requires human approval

    def test_empty_path_rejected(self):
        result = classify_generated_path(
            "",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "malformed_path")
        self.assertFalse(result["allowed"])  # not allowed

    def test_malformed_whitespace_path_rejected(self):
        result = classify_generated_path(
            "   ",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "malformed_path")
        self.assertFalse(result["allowed"])  # not allowed

    def test_repeated_invalid_path_detected(self):
        first = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=self.allowed_paths,
        )
        second = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=self.allowed_paths,
            previous_rejected_paths=[first],
        )
        self.assertTrue(second["repeated_invalid_path"])  # same path repeated across attempts
        # Repetition does not change base classification
        self.assertEqual(second["classification"], "outside_allowlist")

    def test_deterministic_fingerprint(self):
        a = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=self.allowed_paths,
        )
        b = classify_generated_path(
            "./agent/repair/example.py",  # equivalent normalized form
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(a["fingerprint"], b["fingerprint"])  # stable fingerprint

    def test_deterministic_canonical_allowed_ordering(self):
        result = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=list(reversed(self.allowed_paths)),  # supply unsorted input
        )
        self.assertEqual(result["allowed_paths"], sorted(set(self.allowed_paths)))

    def test_inputs_not_mutated(self):
        allowed_in = list(self.allowed_paths)
        _ = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=allowed_in,
        )
        self.assertEqual(allowed_in, self.allowed_paths)  # unchanged

    def test_output_json_serializable(self):
        result = classify_generated_path(
            "agent/repair/example.py",
            allowed_paths=self.allowed_paths,
        )
        # Should not raise
        s = json.dumps(result)
        self.assertIsInstance(s, str)

    def test_outside_allowlist_is_safely_repairable_and_no_human_approval(self):
        result = classify_generated_path(
            "some/other/path.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "outside_allowlist")
        self.assertTrue(result["safely_repairable"])  # can be retried with correct path
        self.assertFalse(result["human_approval_required"])  # no human approval needed

    def test_protected_core_requires_human_approval(self):
        result = classify_generated_path(
            "agent/runtime/mission_queue.py",
            allowed_paths=self.allowed_paths,
        )
        self.assertEqual(result["classification"], "protected_core")
        self.assertTrue(result["human_approval_required"])  # human approval required

    def test_no_implicit_allowlist_expansion(self):
        outside = "new/file.py"
        before = list(self.allowed_paths)
        _ = classify_generated_path(outside, allowed_paths=before)
        after = list(before)
        self.assertEqual(before, after)  # function must not expand or mutate allowlist
        # A second call with same allowlist must still reject the path
        result2 = classify_generated_path(outside, allowed_paths=after)
        self.assertEqual(result2["classification"], "outside_allowlist")

    def test_no_forbidden_imports_or_writes(self):
        # Explicitly verify the production component avoids forbidden modules and write calls
        src_path = os.path.join("agent", "repair", "allowlist_recovery.py")
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        forbidden_imports = [
            "import tempfile",
            "from tempfile",
            "import shutil",
            "from shutil",
            "import subprocess",
            "from subprocess",
            "import requests",
            "from requests",
            "import httpx",
            "from httpx",
            "import aiohttp",
            "from aiohttp",
        ]
        for token in forbidden_imports:
            self.assertNotIn(token, src)

        # Disallow common write/mutation APIs
        forbidden_calls = [
            "os.replace(",
            "os.rename(",
            "os.remove(",
            "os.unlink(",
            "Path.write_text",
            "Path.write_bytes",
        ]
        for token in forbidden_calls:
            self.assertNotIn(token, src)

        # Disallow opening files in write modes
        self.assertNotIn("open(", src)  # module should not open files at all


if __name__ == "__main__":
    unittest.main()
