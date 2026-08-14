from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.maintenance.reconcile_manual_review_approvals import reconcile_one


class _Queue:
    def __init__(self) -> None:
        self.approved: list[str] = []

    def approve_manual_review(self, mission_id: str) -> None:
        self.approved.append(mission_id)


class _Service:
    def __init__(self, *, ancestor: bool, equivalent: bool) -> None:
        self.queue = _Queue()
        self.ancestor = ancestor
        self.equivalent = equivalent
        self.record = None

    def _validate_manual_review(self, mission_id: str, actor: str):
        return {"id": mission_id, "state": "blocked"}, {"request_id": "request-1"}

    def _git(self, *args: str, check: bool = True, timeout: int = 30):
        if args == ("branch", "--show-current"):
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        if args == ("status", "--porcelain"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("fetch", "origin", "main"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args == ("rev-parse", "HEAD"):
            return SimpleNamespace(returncode=0, stdout="main-sha\n", stderr="")
        if args == ("rev-parse", "origin/main"):
            return SimpleNamespace(returncode=0, stdout="main-sha\n", stderr="")
        if args[:2] == ("merge-base", "--is-ancestor"):
            return SimpleNamespace(returncode=0 if self.ancestor else 1, stdout="", stderr="")
        if args[:2] == ("diff", "--quiet"):
            return SimpleNamespace(returncode=0 if self.equivalent else 1, stdout="", stderr="")
        raise AssertionError(args)

    def _mission_ref(self, mission_id: str):
        return f"agent/mission-{mission_id}-20260814", "mission-sha"

    def _changed_files(self, branch: str):
        return ["docs/assessment.md"]

    def _write_decision_record(self, **kwargs):
        self.record = kwargs
        return "/tmp/decision.json"


class ManualReviewReconciliationTests(unittest.TestCase):
    def test_ancestor_mission_reconciles_without_merge(self) -> None:
        service = _Service(ancestor=True, equivalent=False)
        result = reconcile_one(service, "m123")
        self.assertTrue(result["reconciled"])
        self.assertEqual("commit_ancestor", result["satisfaction"])
        self.assertEqual(["m123"], service.queue.approved)
        self.assertEqual("reconciled", service.record["decision"])
        self.assertEqual("completed", service.record["result_state"])

    def test_content_equivalent_diverged_mission_reconciles(self) -> None:
        service = _Service(ancestor=False, equivalent=True)
        result = reconcile_one(service, "m456")
        self.assertTrue(result["reconciled"])
        self.assertEqual("content_equivalent", result["satisfaction"])
        self.assertEqual(["m456"], service.queue.approved)
        self.assertFalse(service.record["already_merged"])

    def test_unsatisfied_mission_remains_blocked(self) -> None:
        service = _Service(ancestor=False, equivalent=False)
        result = reconcile_one(service, "m789")
        self.assertFalse(result["reconciled"])
        self.assertEqual("mission_output_not_satisfied_on_main", result["reason"])
        self.assertEqual([], service.queue.approved)
        self.assertIsNone(service.record)


if __name__ == "__main__":
    unittest.main()
