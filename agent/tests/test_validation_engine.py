import os
import tempfile
import textwrap
import unittest

from agent.validators.validation_engine import ValidationEngine


class TestValidationEngineUnittests(unittest.TestCase):
    def test_unittest_run_with_passing_suite_counts(self):
        class PassingTest(unittest.TestCase):
            def test_ok(self):
                self.assertTrue(True)

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PassingTest)
        engine = ValidationEngine(root=os.getcwd())
        result = engine.run_unittests(suite=suite)
        counts = result["counts"]
        self.assertEqual(counts["total"], 1)
        self.assertEqual(counts["passed"], 1)
        self.assertEqual(counts["failed"], 0)
        self.assertEqual(counts["errors"], 0)

    def test_unittest_run_with_failure_and_error_counts(self):
        class FailingTest(unittest.TestCase):
            def test_fail(self):
                self.assertEqual(1, 0)

        class ErrorTest(unittest.TestCase):
            def test_error(self):
                raise RuntimeError("boom")

        suite = unittest.TestSuite()
        suite.addTests(
            [
                unittest.defaultTestLoader.loadTestsFromTestCase(FailingTest),
                unittest.defaultTestLoader.loadTestsFromTestCase(ErrorTest),
            ]
        )
        engine = ValidationEngine(root=os.getcwd())
        result = engine.run_unittests(suite=suite)
        counts = result["counts"]
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["passed"], 0)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["errors"], 1)

    def test_unittest_discovery_single_passing_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_code = textwrap.dedent(
                """
                import unittest
                
                class Sample(unittest.TestCase):
                    def test_ok(self):
                        self.assertTrue(True)
                """
            )
            path = os.path.join(tmpdir, "test_sample.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(test_code)

            engine = ValidationEngine(root=tmpdir)
            result = engine.run_unittests(start_dir=tmpdir, pattern="test*.py")
            counts = result["counts"]
            self.assertEqual(counts["total"], 1)
            self.assertEqual(counts["passed"], 1)
            self.assertEqual(counts["failed"], 0)
            self.assertEqual(counts["errors"], 0)

    def test_unittest_discovery_single_failing_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_code = textwrap.dedent(
                """
                import unittest
                
                class Sample(unittest.TestCase):
                    def test_fail(self):
                        self.assertTrue(False)
                """
            )
            path = os.path.join(tmpdir, "test_sample_fail.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(test_code)

            engine = ValidationEngine(root=tmpdir)
            result = engine.run_unittests(start_dir=tmpdir, pattern="test*.py")
            counts = result["counts"]
            self.assertEqual(counts["total"], 1)
            self.assertEqual(counts["passed"], 0)
            self.assertEqual(counts["failed"], 1)
            self.assertEqual(counts["errors"], 0)


class TestValidationEngineFileValidation(unittest.TestCase):
    def test_validate_selected_files_mixed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Python files
            good_py = os.path.join(tmpdir, "good.py")
            bad_py = os.path.join(tmpdir, "bad.py")
            with open(good_py, "w", encoding="utf-8") as f:
                f.write("def add(a, b):\n    return a + b\n")
            with open(bad_py, "w", encoding="utf-8") as f:
                # Invalid syntax
                f.write("def broken(:\n    pass\n")

            # JSON files
            good_json = os.path.join(tmpdir, "good.json")
            bad_json = os.path.join(tmpdir, "bad.json")
            with open(good_json, "w", encoding="utf-8") as f:
                f.write("{\n  \"a\": 1, \"b\": [1,2,3]\n}")
            with open(bad_json, "w", encoding="utf-8") as f:
                f.write("{\n  \"a\": 1, \n  \"b\": [1,2,3,]\n}")  # trailing comma invalid JSON

            # Markdown files
            good_md = os.path.join(tmpdir, "README.md")
            missing_md = os.path.join(tmpdir, "MISSING.md")
            with open(good_md, "w", encoding="utf-8") as f:
                f.write("# Title\n\nSome content.\n")

            selected = [good_py, bad_py, good_json, bad_json, good_md, missing_md]

            engine = ValidationEngine(root=tmpdir)
            report = engine.validate(files=selected, run_tests=False)

            self.assertEqual(report["status"], "fail")
            summary = report["summary"]

            self.assertEqual(summary["python"]["total"], 2)
            self.assertEqual(summary["python"]["passed"], 1)
            self.assertEqual(summary["python"]["failed"], 1)

            self.assertEqual(summary["json"]["total"], 2)
            self.assertEqual(summary["json"]["passed"], 1)
            self.assertEqual(summary["json"]["failed"], 1)

            self.assertEqual(summary["markdown"]["total"], 2)
            self.assertEqual(summary["markdown"]["passed"], 1)
            self.assertEqual(summary["markdown"]["failed"], 1)

            # Details should include an entry for missing markdown file with an error
            md_details = report["details"]["markdown"]
            missing_entries = [d for d in md_details if d["file"] == missing_md]
            self.assertEqual(len(missing_entries), 1)
            self.assertFalse(missing_entries[0]["ok"])
            self.assertIn("File not found", missing_entries[0]["error"])  # type: ignore[index]

    def test_full_repository_scan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup repo-like structure
            os.makedirs(os.path.join(tmpdir, "pkg"), exist_ok=True)

            good_py = os.path.join(tmpdir, "pkg", "mod.py")
            with open(good_py, "w", encoding="utf-8") as f:
                f.write("x = 1\n")

            good_json = os.path.join(tmpdir, "data.json")
            with open(good_json, "w", encoding="utf-8") as f:
                f.write("{\"k\": \"v\"}")

            good_md = os.path.join(tmpdir, "README.md")
            with open(good_md, "w", encoding="utf-8") as f:
                f.write("# Readme\n")

            engine = ValidationEngine(root=tmpdir)
            report = engine.validate(run_tests=False)

            self.assertEqual(report["status"], "pass")
            summary = report["summary"]

            self.assertEqual(summary["python"]["total"], 1)
            self.assertEqual(summary["python"]["failed"], 0)

            self.assertEqual(summary["json"]["total"], 1)
            self.assertEqual(summary["json"]["failed"], 0)

            self.assertEqual(summary["markdown"]["total"], 1)
            self.assertEqual(summary["markdown"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
