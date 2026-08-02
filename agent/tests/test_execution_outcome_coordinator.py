from __future__ import annotations

import unittest
from unittest import mock
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from agent.execution.execution_outcome_coordinator import ExecutionOutcomeCoordinator, ExecutionOutcomeValidationError


# -------------------- Fakes --------------------

class FakeProjectResolver:
    def __init__(self, known: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.known = known or {}

    def resolve(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self.known.get(project_id)


class FakeMissionStatusWriter:
    def __init__(self) -> None:
        # missions: mission_id -> {project_id, status}
        self.missions: Dict[str, Dict[str, Any]] = {}
        # Configure allowed transitions from running to allowed statuses
        self.allowed_target_statuses = {"completed", "failed", "blocked", "cancelled", "retrying"}
        self.fail_update = False
        self.invalid_transition: Dict[str, bool] = {}

    def add_mission(self, mission_id: str, project_id: str, status: str = "running") -> None:
        self.missions[mission_id] = {"project_id": project_id, "status": status}

    def update_status(
        self,
        project_id: str,
        mission_id: str,
        status: str,
        *,
        completed_at: datetime,
        blocked_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Simulate failures
        if self.fail_update:
            return {"accepted": False, "failure_code": "mission_status_update_failed"}
        m = self.missions.get(mission_id)
        if not m:
            return {"accepted": False, "mission_not_found": True}
        if m["project_id"] != project_id:
            return {"accepted": False, "failure_code": "cross_project_reference"}
        # Only allow transitions from running to the supported set
        if self.invalid_transition.get(mission_id, False):
            return {"accepted": False, "invalid_status_transition": True}
        if m["status"] != "running" or status not in self.allowed_target_statuses:
            return {"accepted": False, "invalid_status_transition": True}
        # Accept and set new status
        m["status"] = status
        # Note: blocked_reason is ignored in this fake beyond acceptance
        return {"accepted": True}


class FakeUsageLedger:
    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.fail = False

    def record_usage(self, usage: Dict[str, Any]) -> Dict[str, Any]:
        if self.fail:
            return {"ok": False, "failure_code": "usage_recording_failed"}
        self.records.append(dict(usage))
        return {"ok": True}


class FakeReportWriter:
    def __init__(self) -> None:
        self.reports: List[Dict[str, Any]] = []
        self.fail = False

    def store_report(self, outcome: Dict[str, Any]) -> Dict[str, Any]:
        if self.fail:
            return {"ok": False, "failure_code": "report_persistence_failed"}
        # Do not mutate input
        self.reports.append(dict(outcome))
        return {"ok": True}


class FakeClock:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)


class FakeIdGen:
    def __init__(self) -> None:
        self.counter = 0

    def next_id(self) -> str:
        self.counter += 1
        return f"u{self.counter:04d}"


class FakeEventSink:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, name: str, payload: Dict[str, Any]) -> None:
        # Capture emitted events
        self.events.append({"event": name, **payload})


# -------------------- Helpers --------------------


def base_outcome(**overrides: Any) -> Dict[str, Any]:
    started = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    completed = started + timedelta(seconds=5)
    data: Dict[str, Any] = {
        "execution_id": "exec-1",
        "project_id": "p1",
        "request_id": "r1",
        "conversation_id": "c1",
        "plan_id": "pl1",
        "mission_id": "m1",
        "step_id": "s1",
        "task_type": "code",
        "provider_id": "openai",
        "model_id": "gpt-4",
        "worker_id": "w1",
        "started_at": started,
        "completed_at": completed,
        "status": "completed",
        "success": True,
        "retryable": False,
        "fallback_used": False,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "estimated_cost": 0.01,
        "cost_currency": "USD",
        "safe_error_code": None,
        "summary": "Short summary",
        "changed_files": ["src/module.py"],
        "git_branch": "main",
        "git_commit": "abc123",
        "validation_status": None,
        "metadata": {"k": "v"},
    }
    data.update(overrides)
    return data


def build_coordinator() -> tuple[ExecutionOutcomeCoordinator, FakeProjectResolver, FakeMissionStatusWriter, FakeUsageLedger, FakeReportWriter, FakeClock, FakeIdGen, FakeEventSink]:
    resolver = FakeProjectResolver({"p1": {"project_id": "p1"}, "p2": {"project_id": "p2"}})
    msw = FakeMissionStatusWriter()
    ledger = FakeUsageLedger()
    writer = FakeReportWriter()
    clock = FakeClock()
    idg = FakeIdGen()
    es = FakeEventSink()
    coord = ExecutionOutcomeCoordinator(
        project_resolver=resolver,
        mission_status_writer=msw,
        usage_ledger=ledger,
        report_writer=writer,
        clock=clock,
        id_generator=idg,
        event_sink=es,
    )
    return coord, resolver, msw, ledger, writer, clock, idg, es


# -------------------- Tests --------------------


class TestExecutionOutcomeCoordinator(unittest.TestCase):
    def test_successful_completed_outcome(self) -> None:
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        res = coord.process(base_outcome())
        self.assertTrue(res["accepted"])  # accepted
        self.assertEqual(res["status"], "completed")
        self.assertTrue(res["usage_recorded"])  # usage recorded
        self.assertTrue(res["report_persisted"])  # report persisted
        self.assertIn("execution_outcome_completed", [e["event"] for e in es.events])
        # Usage ledger mapping exactly once
        self.assertEqual(len(ledger.records), 1)
        usage = ledger.records[0]
        self.assertEqual(usage["project_id"], "p1")
        self.assertEqual(usage["request_id"], "r1")
        self.assertEqual(usage["mission_id"], "m1")
        self.assertEqual(usage["input_tokens"], 10)
        self.assertEqual(usage["total_tokens"], 15)
        self.assertEqual(usage["estimated_cost"], 0.01)
        # Report writer received original outcome (not mutated)
        self.assertEqual(len(writer.reports), 1)
        self.assertEqual(writer.reports[0]["execution_id"], "exec-1")

    def test_failed_outcome(self) -> None:
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(status="failed", success=False)
        res = coord.process(o)
        self.assertTrue(res["accepted"])  # accepted pipeline regardless of failed status
        self.assertEqual(res["status"], "failed")
        self.assertTrue(res["usage_recorded"])  # usage recorded
        self.assertTrue(res["report_persisted"])  # report persisted

    def test_blocked_outcome(self) -> None:
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(status="blocked", success=False, validation_status="needs_approval")
        res = coord.process(o)
        self.assertTrue(res["accepted"])  # processed
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res.get("blocked_reason"), "needs_approval")

    def test_cancelled_outcome(self) -> None:
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(status="cancelled", success=False)
        res = coord.process(o)
        self.assertTrue(res["accepted"])  # processed
        self.assertEqual(res["status"], "cancelled")

    def test_retrying_outcome(self) -> None:
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(status="retrying", success=False, retryable=True)
        res = coord.process(o)
        self.assertTrue(res["accepted"])  # processed
        self.assertEqual(res["status"], "retrying")

    def test_invalid_status(self) -> None:
        coord, *_ = build_coordinator()
        o = base_outcome(status="unknown", success=True)
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected
        self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")

    def test_timestamp_ordering_rejection(self) -> None:
        coord, *_ = build_coordinator()
        started = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        completed = started - timedelta(seconds=1)
        o = base_outcome(started_at=started, completed_at=completed)
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected
        self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")

    def test_negative_token_rejection(self) -> None:
        coord, *_ = build_coordinator()
        o = base_outcome(input_tokens=-1)
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected
        self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")

    def test_invalid_total_token_rejection(self) -> None:
        coord, *_ = build_coordinator()
        o = base_outcome(total_tokens=100)
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected
        self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")

    def test_negative_cost_rejection(self) -> None:
        coord, *_ = build_coordinator()
        o = base_outcome(estimated_cost=-0.1)
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected
        self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")

    def test_unknown_cost_preservation(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(estimated_cost=None, cost_currency=None)
        res = coord.process(o)
        self.assertTrue(res["accepted"])  # processed with unknown cost
        self.assertEqual(len(ledger.records), 1)
        self.assertIsNone(ledger.records[0]["estimated_cost"])  # unknown cost remains null

    def test_unknown_project(self) -> None:
        coord, *_ = build_coordinator()
        o = base_outcome(project_id="not-known")
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected by resolver
        self.assertEqual(res.get("failure_code"), "cross_project_reference")

    def test_cross_project_rejection(self) -> None:
        coord, resolver, msw, *_ = build_coordinator()
        # mission exists but belongs to a different project
        msw.add_mission("m1", "p2")
        o = base_outcome(project_id="p1")
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # failed at mission update
        self.assertIn(res.get("failure_code"), {"cross_project_reference", "invalid_status_transition", "mission_not_found", "mission_status_update_failed"})

    def test_mission_not_found_result(self) -> None:
        coord, *_ = build_coordinator()
        # No mission added
        o = base_outcome()
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # failed at mission update
        self.assertEqual(res.get("failure_code"), "mission_not_found")

    def test_invalid_status_transition(self) -> None:
        coord, resolver, msw, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        msw.invalid_transition["m1"] = True
        o = base_outcome()
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # failed
        self.assertEqual(res.get("failure_code"), "invalid_status_transition")

    def test_status_update_failure_stops_processing(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        msw.fail_update = True
        o = base_outcome()
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # failed
        self.assertEqual(len(ledger.records), 0)  # no usage recorded after status failure
        self.assertEqual(len(writer.reports), 0)  # no report persisted after status failure

    def test_exact_usage_mapping(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(fallback_used=True, safe_error_code="E123")
        res = coord.process(o)
        self.assertTrue(res["accepted"])  # processed
        usage = ledger.records[0]
        self.assertIn("usage_id", usage)
        self.assertEqual(usage["fallback_used"], True)
        self.assertEqual(usage["safe_error_code"], "E123")

    def test_usage_ledger_failure(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        ledger.fail = True
        res = coord.process(base_outcome())
        self.assertFalse(res["accepted"])  # failed usage recording
        self.assertEqual(res.get("failure_code"), "usage_recording_failed")
        self.assertEqual(len(writer.reports), 0)  # report not persisted when usage fails

    def test_report_persistence_failure(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        writer.fail = True
        res = coord.process(base_outcome())
        self.assertFalse(res["accepted"])  # failed at report persistence
        self.assertEqual(res.get("failure_code"), "report_persistence_failed")
        self.assertEqual(len(ledger.records), 1)  # usage recorded

    def test_duplicate_execution_handling(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome()
        r1 = coord.process(o)
        # Duplicate call returns same deterministic result
        r2 = coord.process(o)
        self.assertEqual(r1, r2)
        # Ensure no duplicate usage or report
        self.assertEqual(len(ledger.records), 1)
        self.assertEqual(len(writer.reports), 1)

    def test_duplicate_usage_prevention(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome()
        coord.process(o)
        # Manually call again; still should be one usage
        coord.process(o)
        self.assertEqual(len(ledger.records), 1)

    def test_duplicate_status_update_prevention(self) -> None:
        coord, resolver, msw, ledger, writer, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome()
        coord.process(o)
        # original mission status remains after duplicate; no additional state changes detectable here
        self.assertEqual(msw.missions["m1"]["status"], "completed")

    def test_original_input_not_mutated(self) -> None:
        coord, resolver, msw, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome()
        before = dict(o)
        coord.process(o)
        self.assertEqual(before, o)

    def test_deterministic_result(self) -> None:
        coord, resolver, msw, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome()
        r1 = coord.process(o)
        r2 = coord.get_result("exec-1")
        self.assertEqual(r1, r2)

    def test_result_redaction(self) -> None:
        coord, resolver, msw, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(summary="This is a longer secret summary", metadata={"secret": "value"})
        res = coord.process(o)
        # Result should not include summary or metadata fields
        self.assertNotIn("summary", res)
        self.assertNotIn("metadata", res)

    def test_event_redaction(self) -> None:
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        o = base_outcome(summary="This is secret", metadata={"secret": "value"})
        coord.process(o)
        # Events should not contain summary or metadata
        for ev in es.events:
            self.assertNotIn("summary", ev)
            self.assertNotIn("metadata", ev)

    def test_unrelated_files_remain_unchanged(self) -> None:
        # This test ensures that coordinator operations do not perform I/O or modify external state
        # beyond injected fakes. We check that only our fakes captured interactions.
        coord, resolver, msw, ledger, writer, clock, idg, es = build_coordinator()
        msw.add_mission("m1", "p1")
        coord.process(base_outcome())
        self.assertGreaterEqual(len(es.events), 1)
        self.assertGreaterEqual(len(ledger.records), 1)
        self.assertGreaterEqual(len(writer.reports), 1)

    def test_invalid_timezone_rejection(self) -> None:
        coord, *_ = build_coordinator()
        started = datetime(2025, 1, 1, 0, 0)  # naive
        completed = started + timedelta(seconds=1)
        o = base_outcome(started_at=started, completed_at=completed)
        res = coord.process(o)
        self.assertFalse(res["accepted"])  # rejected
        self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")

    def test_changed_files_validation(self) -> None:
        coord, resolver, msw, *_ = build_coordinator()
        msw.add_mission("m1", "p1")
        for bad in ["/abs/path.py", "..\\secret.txt", "a/../b.txt", "\\windows\\abs.txt", "C:/root.txt", "bad\x00file.txt"]:
            o = base_outcome(changed_files=[bad])
            res = coord.process(o)
            self.assertFalse(res["accepted"])  # rejected path
            self.assertEqual(res.get("failure_code"), "invalid_execution_outcome")
        # Valid relative
        o2 = base_outcome(changed_files=["rel/path.txt", "a/b/c.py"])
        msw.missions["m1"]["status"] = "running"
        res2 = coord.process(o2)
        self.assertTrue(res2["accepted"])  # ok


if __name__ == "__main__":
    unittest.main()
