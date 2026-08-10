from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.runtime.production_execution_reporter import (
    ProductionExecutionReporter,
)


class ProductionExecutionReporterTests(
    unittest.TestCase
):
    def build_reporter(
        self,
        root: Path,
    ) -> ProductionExecutionReporter:
        return ProductionExecutionReporter(
            storage_dir=root / "execution-reports",
            project_id="mitigate-ai-platform",
        )

    def test_completed_autonomous_merge_report(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            reporter = self.build_reporter(
                Path(td)
            )

            started = datetime(
                2026,
                8,
                10,
                19,
                7,
                1,
                tzinfo=timezone.utc,
            )

            completed = started + timedelta(
                seconds=20
            )

            stored = reporter.persist(
                execution_id=(
                    "exec-m1786388821863577-"
                    "e6fefe48"
                ),
                mission_id="m1786388821863577",
                request_id=(
                    "req-production-auto-merge-"
                    "e2e-20260810-v1"
                ),
                started_at=started,
                completed_at=completed,
                status="completed",
                task_type="documentation",
                worker_id="production-worker",
                changed_files=[
                    "docs/runtime/AUTO_MERGE_E2E.md",
                ],
                git_branch=(
                    "agent/mission-"
                    "m1786388821863577-"
                    "20260810-190706"
                ),
                git_commit=(
                    "e6fefe48f175224e8dfb5d76f4a50840"
                    "b61cb13c"
                ),
                validation_status="validated",
                summary=(
                    "Production autonomous merge "
                    "completed."
                ),
                metadata={
                    "risk_level": "low",
                    "merge_recommendation": "approve",
                    "merged_to_main": True,
                },
            )

            self.assertEqual(
                "completed",
                stored["status"],
            )
            self.assertTrue(
                stored["success"]
            )
            self.assertEqual(
                [
                    "docs/runtime/"
                    "AUTO_MERGE_E2E.md"
                ],
                stored["changed_files"],
            )
            self.assertEqual(
                "low",
                stored["metadata"]["risk_level"],
            )
            self.assertTrue(
                stored["metadata"][
                    "merged_to_main"
                ]
            )

            persisted = reporter.get_report(
                "exec-m1786388821863577-e6fefe48"
            )

            self.assertEqual(
                stored,
                persisted,
            )

    def test_blocked_report_preserves_safe_reason(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            reporter = self.build_reporter(
                Path(td)
            )

            started = datetime.now(
                timezone.utc
            )

            stored = reporter.persist(
                execution_id="exec-blocked-001",
                mission_id="m-blocked-001",
                request_id="req-blocked-001",
                started_at=started,
                completed_at=(
                    started
                    + timedelta(seconds=1)
                ),
                status="blocked",
                safe_error_code=(
                    "manual_review_required"
                ),
                validation_status=(
                    "manual_review_required"
                ),
                metadata={
                    "risk_level": "medium",
                    "merge_recommendation": (
                        "manual_review"
                    ),
                    "merged_to_main": False,
                },
            )

            self.assertFalse(
                stored["success"]
            )
            self.assertEqual(
                "blocked",
                stored["status"],
            )
            self.assertEqual(
                "manual_review_required",
                stored["safe_error_code"],
            )

    def test_unknown_project_is_not_accepted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            reporter = self.build_reporter(
                Path(td)
            )

            self.assertIsNone(
                reporter._resolve_project(
                    "other-project"
                )
            )

    def test_status_returns_persisted_report_count(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            reporter = self.build_reporter(
                Path(td)
            )

            started = datetime.now(
                timezone.utc
            )

            reporter.persist(
                execution_id="exec-status-001",
                mission_id="m-status-001",
                request_id="req-status-001",
                started_at=started,
                completed_at=(
                    started
                    + timedelta(seconds=1)
                ),
                status="completed",
            )

            status = reporter.status()

            self.assertEqual(
                1,
                status["total_reports"],
            )


if __name__ == "__main__":
    unittest.main()
