from __future__ import annotations

import io
import json
import os
import py_compile
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ValidationCounts:
    total: int
    passed: int
    failed: int


@dataclass(frozen=True)
class UnitTestCounts:
    total: int
    passed: int
    failed: int
    errors: int


class ValidationEngine:
    """
    ValidationEngine performs production-grade validations for:
    - Python syntax via py_compile without modifying repository
    - JSON file parsing
    - Markdown files existence & readability
    - Unittest discovery & execution

    The engine returns a deterministic structured report and logs.
    """

    def __init__(self, root: Optional[Path | str] = None) -> None:
        self.root = Path(root) if root is not None else Path.cwd()
        # Deterministic logs: message-only, no timestamps
        self._logs: List[str] = []

    # ---------------------------- Public API ----------------------------

    def validate(
        self,
        files: Optional[Sequence[str | os.PathLike[str]]] = None,
        run_tests: bool = True,
        test_start_dir: Optional[str | os.PathLike[str]] = None,
        test_pattern: str = "test*.py",
        test_suite: Optional[unittest.TestSuite] = None,
    ) -> Dict[str, object]:
        """
        Validate selected files or the entire repository.

        Parameters:
            files: If provided, only these files are validated by type.
            run_tests: When True, run unittest discovery (or provided suite).
            test_start_dir: Optional explicit start dir for unittest discovery.
            test_pattern: Discovery pattern (default 'test*.py').
            test_suite: Optional explicit unittest TestSuite to run.

        Returns: structured deterministic validation report dict.
        """
        self._logs.clear()
        self._log(f"Validation started. Root: {self.root}")

        files_to_check = self._prepare_file_list(files)
        self._log(
            "Files to validate (by type): "
            + ", ".join(f"{k}={len(v)}" for k, v in files_to_check.items())
        )

        py_report = self._validate_python(files_to_check.get("python", []))
        json_report = self._validate_json(files_to_check.get("json", []))
        md_report = self._validate_markdown(files_to_check.get("markdown", []))

        unit_report: Dict[str, object] = {
            "counts": UnitTestCounts(total=0, passed=0, failed=0, errors=0).__dict__,
            "failures": [],
            "errors": [],
        }
        if run_tests:
            unit_report = self.run_unittests(
                suite=test_suite, start_dir=test_start_dir, pattern=test_pattern
            )

        status = self._overall_status(py_report, json_report, md_report, unit_report)
        self._log(f"Validation completed. Overall status: {status}")

        report: Dict[str, object] = {
            "status": status,
            "summary": {
                "python": py_report["counts"],
                "json": json_report["counts"],
                "markdown": md_report["counts"],
                "unittest": unit_report["counts"],
            },
            "details": {
                "python": py_report["details"],
                "json": json_report["details"],
                "markdown": md_report["details"],
                "unittest": {
                    "failures": unit_report.get("failures", []),
                    "errors": unit_report.get("errors", []),
                },
            },
            "logs": list(self._logs),
        }
        return report

    def run_unittests(
        self,
        suite: Optional[unittest.TestSuite] = None,
        start_dir: Optional[str | os.PathLike[str]] = None,
        pattern: str = "test*.py",
    ) -> Dict[str, object]:
        """
        Execute unittest discovery (or a provided suite) and parse counts from
        the unittest result object, not by fragile text matching.

        Parameters:
            suite: Optional pre-constructed TestSuite to run.
            start_dir: Directory for discovery. Defaults to project root/tests.
            pattern: Discovery pattern, default 'test*.py'.

        Returns: dict with counts and details of failures/errors.
        """
        self._log("Starting unittest execution.")
        if suite is None:
            # Default discovery root: provided start_dir -> else common 'tests' under root -> else root
            discovery_dir = (
                Path(start_dir) if start_dir is not None else self._default_tests_dir()
            )
            self._log(f"Discovering tests in: {discovery_dir} with pattern: {pattern}")
            loader = unittest.TestLoader()
            try:
                suite = loader.discover(start_dir=str(discovery_dir), pattern=pattern)
            except Exception as exc:  # Discovery errors are uncommon but possible
                # Represent discovery as 1 error to surface the issue deterministically
                self._log(f"Test discovery failed: {exc}")
                counts = UnitTestCounts(total=1, passed=0, failed=0, errors=1)
                return {
                    "counts": counts.__dict__,
                    "failures": [],
                    "errors": [
                        {
                            "test": "<discovery>",
                            "error": f"Discovery failed: {exc}",
                        }
                    ],
                }
        else:
            self._log("Running provided unittest suite.")

        # Execute tests with in-memory stream
        stream = io.StringIO()
        runner = unittest.TextTestRunner(stream=stream, verbosity=0)
        result: unittest.TestResult = runner.run(suite)

        total = int(getattr(result, "testsRun", 0) or 0)
        failed_list = list(getattr(result, "failures", []) or [])
        error_list = list(getattr(result, "errors", []) or [])
        failed = len(failed_list)
        errors = len(error_list)
        passed = total - failed - errors

        self._log(
            f"Unittest results: total={total}, passed={passed}, failed={failed}, errors={errors}"
        )

        # Normalize failure/error details in deterministic order
        def _normalize(items: List[Tuple[unittest.case.TestCase, str]]) -> List[Dict[str, str]]:
            normalized: List[Dict[str, str]] = []
            for test, tb in items:
                test_id = test.id() if hasattr(test, "id") else str(test)
                normalized.append({"test": test_id, "traceback": tb})
            normalized.sort(key=lambda x: x["test"])  # deterministic
            return normalized

        counts = UnitTestCounts(total=total, passed=passed, failed=failed, errors=errors)
        return {
            "counts": counts.__dict__,
            "failures": _normalize(failed_list),
            "errors": _normalize(error_list),
        }

    # -------------------------- Internal Logic --------------------------

    def _default_tests_dir(self) -> Path:
        # Prefer a conventional 'tests' directory under root when present; else root
        tests_dir = self.root / "tests"
        return tests_dir if tests_dir.is_dir() else self.root

    def _overall_status(
        self,
        py_report: Dict[str, object],
        json_report: Dict[str, object],
        md_report: Dict[str, object],
        unit_report: Dict[str, object],
    ) -> str:
        def has_fail(d: Dict[str, object]) -> bool:
            counts = d.get("counts", {})  # type: ignore[assignment]
            return int(getattr(type("C", (), counts)(), "failed", 0)) > 0  # robust but odd

        py_failed = int(py_report["counts"]["failed"]) > 0  # type: ignore[index]
        json_failed = int(json_report["counts"]["failed"]) > 0  # type: ignore[index]
        md_failed = int(md_report["counts"]["failed"]) > 0  # type: ignore[index]
        unit_failed = (
            int(unit_report["counts"]["failed"]) > 0  # type: ignore[index]
            or int(unit_report["counts"]["errors"]) > 0  # type: ignore[index]
        )
        return "pass" if not (py_failed or json_failed or md_failed or unit_failed) else "fail"

    def _prepare_file_list(
        self, files: Optional[Sequence[str | os.PathLike[str]]]
    ) -> Dict[str, List[Path]]:
        if files:
            # Only validate explicitly provided files
            paths = [self._abs_path(Path(f)) for f in files]
        else:
            # Full repository scan under root
            paths = list(self._iter_repo_files())

        categorized: Dict[str, List[Path]] = {"python": [], "json": [], "markdown": []}
        for p in paths:
            suffix = p.suffix.lower()
            if suffix == ".py":
                categorized["python"].append(p)
            elif suffix == ".json":
                categorized["json"].append(p)
            elif suffix == ".md":
                categorized["markdown"].append(p)
            else:
                # other files ignored for validation
                continue

        for key in categorized:
            categorized[key].sort(key=lambda x: str(x))
        return categorized

    def _iter_repo_files(self) -> Iterable[Path]:
        for path in sorted(self.root.rglob("*"), key=lambda p: str(p)):
            if path.is_file():
                yield path

    def _abs_path(self, p: Path) -> Path:
        if p.is_absolute():
            return p
        # Resolve relative to root deterministically
        return (self.root / p).resolve()

    def _validate_python(self, files: Sequence[Path]) -> Dict[str, object]:
        details: List[Dict[str, object]] = []
        passed = 0
        failed = 0
        if not files:
            self._log("No Python files to validate.")
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                record: Dict[str, object] = {"file": str(f), "ok": False}
                if not f.exists() or not f.is_file():
                    record["error"] = "File not found"
                    failed += 1
                    details.append(record)
                    self._log(f"Python validation failed (missing): {f}")
                    continue
                try:
                    cfile = os.path.join(tmpdir, os.path.basename(str(f)) + ".pyc")
                    py_compile.compile(str(f), cfile=cfile, doraise=True)
                    record["ok"] = True
                    passed += 1
                    self._log(f"Python syntax OK: {f}")
                except py_compile.PyCompileError as exc:
                    record["error"] = getattr(exc, "msg", str(exc))
                    failed += 1
                    self._log(f"Python syntax error in {f}: {record['error']}")
                except Exception as exc:  # Any unexpected exception
                    record["error"] = str(exc)
                    failed += 1
                    self._log(f"Python validation unexpected error in {f}: {exc}")
                finally:
                    details.append(record)
        counts = ValidationCounts(total=len(files), passed=passed, failed=failed)
        return {"counts": counts.__dict__, "details": details}

    def _validate_json(self, files: Sequence[Path]) -> Dict[str, object]:
        details: List[Dict[str, object]] = []
        passed = 0
        failed = 0
        if not files:
            self._log("No JSON files to validate.")
        for f in files:
            record: Dict[str, object] = {"file": str(f), "ok": False}
            if not f.exists() or not f.is_file():
                record["error"] = "File not found"
                failed += 1
                details.append(record)
                self._log(f"JSON validation failed (missing): {f}")
                continue
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    json.load(fh)
                record["ok"] = True
                passed += 1
                self._log(f"JSON valid: {f}")
            except json.JSONDecodeError as exc:
                record["error"] = f"JSON decode error: {exc.msg} at line {exc.lineno} col {exc.colno}"
                failed += 1
                self._log(f"JSON invalid in {f}: {record['error']}")
            except Exception as exc:
                record["error"] = str(exc)
                failed += 1
                self._log(f"JSON validation unexpected error in {f}: {exc}")
            finally:
                details.append(record)
        counts = ValidationCounts(total=len(files), passed=passed, failed=failed)
        return {"counts": counts.__dict__, "details": details}

    def _validate_markdown(self, files: Sequence[Path]) -> Dict[str, object]:
        details: List[Dict[str, object]] = []
        passed = 0
        failed = 0
        if not files:
            self._log("No Markdown files to validate.")
        for f in files:
            record: Dict[str, object] = {"file": str(f), "ok": False}
            if not f.exists() or not f.is_file():
                record["error"] = "File not found"
                failed += 1
                details.append(record)
                self._log(f"Markdown validation failed (missing): {f}")
                continue
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    # Reading the entire file ensures readability under utf-8
                    _ = fh.read()
                record["ok"] = True
                passed += 1
                self._log(f"Markdown readable: {f}")
            except Exception as exc:
                record["error"] = str(exc)
                failed += 1
                self._log(f"Markdown not readable in {f}: {exc}")
            finally:
                details.append(record)
        counts = ValidationCounts(total=len(files), passed=passed, failed=failed)
        return {"counts": counts.__dict__, "details": details}

    # ------------------------------ Logging -----------------------------

    def _log(self, message: str) -> None:
        # Store logs deterministically without timestamps
        self._logs.append(str(message))


__all__ = ["ValidationEngine", "ValidationCounts", "UnitTestCounts"]
