from __future__ import annotations

import os
import unittest
from typing import List, Tuple
from unittest.mock import patch

from agent.git.review_engine import GitReviewEngine


class FakeCompletedProcess:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = 0


class TestGitRefValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GitReviewEngine(repo_path=".")

    def test_valid_refs(self) -> None:
        valid = [
            "main",
            "feature/login",
            "release/1.0",
            "v1.0.0",
            "hotfix-123",
            "refs/heads/main",
        ]
        for ref in valid:
            with self.subTest(ref=ref):
                self.assertTrue(self.engine.validate_git_ref(ref))

    def test_invalid_refs(self) -> None:
        invalid = [
            "",  # empty
            "bad ref",  # whitespace
            "bad\tref",  # control char
            "-leadingdash",
            "/leading/slash",
            "trailing/slash/",
            "trailingdot.",
            "branch.lock",
            "contains\\backslash",
            "weird@{ref}",
            "has..dots",
            "double//slash",
            "has*glob",
            "ends.with.lock",
        ]
        for ref in invalid:
            with self.subTest(ref=ref):
                self.assertFalse(self.engine.validate_git_ref(ref))


class TestGitReviewEngineDiffParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GitReviewEngine(repo_path=os.getcwd())

    def _fake_run_side_effect(self, calls: List[Tuple[str, str, str]]):
        """
        Create a side effect function that returns FakeCompletedProcess objects
        for each git command type based on args. Calls is a list of tuples:
        (subcommand, stdout, stderr)
        subcommand keys: 'name-status', 'numstat', 'summary'
        """
        def _side_effect(args, check=False, capture_output=False, text=False):  # type: ignore[no-redef]
            # args is the full command list: [git, -C, repo, diff, ...]
            self.assertIsInstance(args, list)
            self.assertGreaterEqual(len(args), 4)
            self.assertEqual(args[0], "git")
            self.assertEqual(args[1], "-C")
            self.assertIsInstance(args[2], str)
            self.assertEqual(args[3], "diff")
            # Determine which sub-mode
            if "--name-status" in args:
                for key, out, err in calls:
                    if key == "name-status":
                        return FakeCompletedProcess(stdout=out, stderr=err)
                return FakeCompletedProcess(stdout="", stderr="")
            if "--numstat" in args:
                for key, out, err in calls:
                    if key == "numstat":
                        return FakeCompletedProcess(stdout=out, stderr=err)
                return FakeCompletedProcess(stdout="", stderr="")
            if "--summary" in args:
                for key, out, err in calls:
                    if key == "summary":
                        return FakeCompletedProcess(stdout=out, stderr=err)
                return FakeCompletedProcess(stdout="", stderr="")
            return FakeCompletedProcess(stdout="", stderr="")

        return _side_effect

    @patch("subprocess.run")
    def test_parse_added_modified_deleted_renamed_and_stats(self, mock_run) -> None:  # type: ignore[override]
        name_status_out = (
            "A\tnewfile.py\n"
            "M\tsrc/app.py\n"
            "D\tdb/schema.sql\n"
            "R100\told_name.txt\tnew_name.txt\n"
        )
        numstat_out = (
            "10\t2\tnewfile.py\n"
            "5\t3\tsrc/app.py\n"
            "0\t10\tdb/schema.sql\n"
            "0\t0\told_name.txt => new_name.txt\n"
        )
        summary_out = (
            "mode change 100644 => 100755 bin/run.sh\n"
        )
        mock_run.side_effect = self._fake_run_side_effect(
            [
                ("name-status", name_status_out, ""),
                ("numstat", numstat_out, ""),
                ("summary", summary_out, ""),
            ]
        )

        report = self.engine.review("main", "feature/login")

        self.assertTrue(report["validation"]["ok"])  # type: ignore[index]
        files = report["files"]
        self.assertEqual(len(files["added"]), 1)
        self.assertEqual(len(files["modified"]), 1)
        self.assertEqual(len(files["deleted"]), 1)
        self.assertEqual(len(files["renamed"]), 1)

        stats = report["stats"]
        self.assertEqual(stats["total_files_changed"], 4)
        self.assertEqual(stats["insertions"], 15)
        self.assertEqual(stats["deletions"], 15)
        self.assertEqual(stats["renames"], 1)

        # Permission change finding should elevate to high
        self.assertIn("permissions changed", " ".join([f.lower() for f in report["categories"]["findings"]]))
        self.assertIn(report["risk_level"], ["high", "critical"])  # high due to permissions
        self.assertEqual(report["merge_recommendation"], "manual_review")

    def test_secret_like_detection(self) -> None:
        cases = [
            ".env",
            "prod/.env.local",
            "keys/server.KEY",
            "ssh/id_rsa",
            "ssh/id_ed25519",
            "config/credentials.json",
            "config/secrets.yaml",
            "some/path/contains-token-file.txt",
            "nested/PasswordReset/info.txt",
        ]
        for p in cases:
            with self.subTest(path=p):
                self.assertTrue(GitReviewEngine.is_secret_like(p))

    @patch("subprocess.run")
    def test_secret_like_file_triggers_critical(self, mock_run) -> None:  # type: ignore[override]
        name_status_out = (
            "A\tconfig/token_config.yaml\n"
        )
        numstat_out = (
            "1\t0\tconfig/token_config.yaml\n"
        )
        summary_out = ("")
        mock_run.side_effect = self._fake_run_side_effect(
            [
                ("name-status", name_status_out, ""),
                ("numstat", numstat_out, ""),
                ("summary", summary_out, ""),
            ]
        )

        report = self.engine.review("main", "feature/keys")
        self.assertEqual(report["risk_level"], "critical")
        self.assertEqual(report["merge_recommendation"], "reject")
        high_risk_files = report["categories"]["high_risk_files"]
        self.assertTrue(any("token" in fr["path"] for fr in high_risk_files))

    @patch("subprocess.run")
    def test_sensitive_deletion_elevates_risk(self, mock_run) -> None:  # type: ignore[override]
        name_status_out = (
            "D\tk8s/deployment.yaml\n"
        )
        numstat_out = (
            "0\t0\tk8s/deployment.yaml\n"
        )
        summary_out = ("")
        mock_run.side_effect = self._fake_run_side_effect(
            [
                ("name-status", name_status_out, ""),
                ("numstat", numstat_out, ""),
                ("summary", summary_out, ""),
            ]
        )

        report = self.engine.review("main", "feature/remove-deploy")
        self.assertEqual(report["risk_level"], "high")
        self.assertEqual(report["merge_recommendation"], "manual_review")

    @patch("subprocess.run")
    def test_dependency_manifest_changes(self, mock_run) -> None:  # type: ignore[override]
        name_status_out = (
            "M\trequirements.txt\n"
            "A\tpackage.json\n"
        )
        numstat_out = (
            "10\t2\trequirements.txt\n"
            "100\t5\tpackage.json\n"
        )
        summary_out = ("")
        mock_run.side_effect = self._fake_run_side_effect(
            [
                ("name-status", name_status_out, ""),
                ("numstat", numstat_out, ""),
                ("summary", summary_out, ""),
            ]
        )
        report = self.engine.review("v1.0.0", "v1.1.0")
        self.assertEqual(report["risk_level"], "high")  # high due to dependency manifests
        self.assertIn("dependency manifest", " ".join([f.lower() for f in report["categories"]["findings"]]))


if __name__ == "__main__":
    unittest.main()
