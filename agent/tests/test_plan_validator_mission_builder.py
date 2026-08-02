import unittest
from typing import Any, Dict, List, Mapping, Optional, Set
from copy import deepcopy

from agent.orchestrator.plan_validator_mission_builder import (
    PlanValidatorMissionBuilder,
    InvalidApprovedRequestError,
    InvalidPlanError,
    DuplicateStepError,
    UnknownDependencyError,
    SelfDependencyError,
    CircularDependencyError,
    UnsafePayloadError,
)


def make_id_generator(ids: List[str]):
    seq = list(ids)

    def gen() -> str:
        if not seq:
            raise RuntimeError("No more ids in generator")
        return seq.pop(0)

    return gen


def make_clock(ts: str):
    def clock() -> str:
        return ts

    return clock


class TestPlanValidatorMissionBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.supported: Set[str] = {"plan", "analysis", "write", "review"}
        self.clock_value = "2024-01-01T00:00:00Z"
        self.builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=make_id_generator(["X1", "X2", "X3", "X4", "X5", "X6"]),
            clock=make_clock(self.clock_value),
        )
        self.approved_request: Dict[str, Any] = {
            "request_id": "req-123",
            "project_id": "proj-1",
            "conversation_id": "conv-1",
            "provider_id": "prov-1",
            "model_id": "model-1",
            "task_type": "plan",
            "created_at": "2024-01-01T00:00:00Z",
        }

    def _plan(self, steps: List[Dict[str, Any]], summary: str = "A plan", plan_id: str = "plan-1") -> Dict[str, Any]:
        return {
            "plan_id": plan_id,
            "request_id": self.approved_request["request_id"],
            "project_id": self.approved_request["project_id"],
            "summary": summary,
            "steps": steps,
        }

    def test_valid_plan_acceptance(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "First",
                "description": "Do analysis",
                "dependencies": [],
                "priority": 5,
                "task_type": "analysis",
                "payload": {"note": "We may mention bash or CLI here, descriptive only."},
            },
            {
                "step_id": "b",
                "title": "Second",
                "description": "Continue",
                "dependencies": [],
                "priority": 5,
                "task_type": "analysis",
                "payload": {"info": "No commands executed"},
            },
        ]
        plan = self._plan(steps)
        missions = self.builder.build_missions(plan, self.approved_request)
        self.assertEqual(len(missions), 2)
        # Deterministic creation time and status
        for m in missions:
            self.assertEqual(m["status"], "pending")
            self.assertEqual(m["created_at"], self.clock_value)
            self.assertEqual(m["project_id"], self.approved_request["project_id"])
            self.assertEqual(m["request_id"], self.approved_request["request_id"])
        # With equal priorities and step_id ordering a<b we keep generator order X1, X2
        self.assertEqual([m["mission_id"] for m in missions], ["X1", "X2"])

    def test_empty_plan_rejection(self) -> None:
        plan = self._plan([])
        with self.assertRaises(InvalidPlanError):
            self.builder.build_missions(plan, self.approved_request)

    def test_duplicate_step_rejection(self) -> None:
        steps = [
            {
                "step_id": "dup",
                "title": "One",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "dup",
                "title": "Two",
                "description": "D",
                "dependencies": [],
                "priority": 2,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        with self.assertRaises(DuplicateStepError):
            self.builder.build_missions(plan, self.approved_request)

    def test_unknown_dependency_rejection(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "One",
                "description": "D",
                "dependencies": ["missing"],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            }
        ]
        plan = self._plan(steps)
        with self.assertRaises(UnknownDependencyError):
            self.builder.build_missions(plan, self.approved_request)

    def test_self_dependency_rejection(self) -> None:
        steps = [
            {
                "step_id": "self",
                "title": "One",
                "description": "D",
                "dependencies": ["self"],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            }
        ]
        plan = self._plan(steps)
        with self.assertRaises(SelfDependencyError):
            self.builder.build_missions(plan, self.approved_request)

    def test_circular_dependency_rejection(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "A",
                "description": "D",
                "dependencies": ["b"],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "b",
                "title": "B",
                "description": "D",
                "dependencies": ["a"],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        with self.assertRaises(CircularDependencyError):
            self.builder.build_missions(plan, self.approved_request)

    def test_request_mismatch_rejection(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "One",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            }
        ]
        bad_plan = dict(self._plan(steps))
        bad_plan["request_id"] = "different"
        with self.assertRaises(InvalidPlanError):
            self.builder.build_missions(bad_plan, self.approved_request)

    def test_project_mismatch_rejection(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "One",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            }
        ]
        bad_plan = dict(self._plan(steps))
        bad_plan["project_id"] = "proj-2"
        with self.assertRaises(InvalidPlanError):
            self.builder.build_missions(bad_plan, self.approved_request)

    def test_unknown_field_rejection_plan_level(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "One",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            }
        ]
        plan = self._plan(steps)
        plan["extra"] = True
        with self.assertRaises(InvalidPlanError):
            self.builder.build_missions(plan, self.approved_request)

    def test_unknown_field_rejection_step_level(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "One",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
                "extra": 42,
            }
        ]
        plan = self._plan(steps)
        with self.assertRaises(InvalidPlanError):
            self.builder.build_missions(plan, self.approved_request)

    def test_invalid_approved_request_unknown_field(self) -> None:
        bad_req = dict(self.approved_request)
        bad_req["unknown"] = "x"
        with self.assertRaises(InvalidApprovedRequestError):
            self.builder.build_missions(self._plan([
                {
                    "step_id": "a",
                    "title": "t",
                    "description": "d",
                    "dependencies": [],
                    "priority": 1,
                    "task_type": "analysis",
                    "payload": {},
                }
            ]), bad_req)

    def test_unsafe_payload_key_rejection(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "Run",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {"cmd": "rm -rf /"},
            }
        ]
        plan = self._plan(steps)
        with self.assertRaises(UnsafePayloadError):
            self.builder.build_missions(plan, self.approved_request)

    def test_descriptive_payload_strings_allowed(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "Note",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {"note": "use bash as an example, do not execute"},
            }
        ]
        plan = self._plan(steps)
        missions = self.builder.build_missions(plan, self.approved_request)
        self.assertEqual(len(missions), 1)
        self.assertIn("note", missions[0]["payload"])  # not rejected

    def test_deterministic_mission_identifiers(self) -> None:
        # Two independent steps, ids should be in generator order
        id_gen = make_id_generator(["X1", "X2"])
        builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=id_gen,
            clock=make_clock(self.clock_value),
        )
        steps = [
            {
                "step_id": "a",
                "title": "t1",
                "description": "d1",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "b",
                "title": "t2",
                "description": "d2",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        missions = builder.build_missions(plan, self.approved_request)
        self.assertEqual([m["mission_id"] for m in missions], ["X1", "X2"])

    def test_deterministic_dependency_conversion(self) -> None:
        # a depends on b and c; dependencies must convert to mission_ids and be sorted lexicographically
        id_gen = make_id_generator(["MA", "MB", "MC"])  # generated in a, b, c order
        builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=id_gen,
            clock=make_clock(self.clock_value),
        )
        steps = [
            {
                "step_id": "a",
                "title": "A",
                "description": "D",
                "dependencies": ["c", "b"],  # out of order
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "b",
                "title": "B",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "c",
                "title": "C",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        missions = builder.build_missions(plan, self.approved_request)
        # After conversion, dependencies of mission for step a are [MB, MC] sorted
        a_mission = [m for m in missions if m["step_id"] == "a"][0]
        self.assertEqual(a_mission["dependencies"], ["MB", "MC"])  # MB < MC lexicographically

    def test_deterministic_topological_ordering(self) -> None:
        # a -> b -> c chain
        id_gen = make_id_generator(["M1", "M2", "M3"])
        builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=id_gen,
            clock=make_clock(self.clock_value),
        )
        steps = [
            {
                "step_id": "a",
                "title": "A",
                "description": "D",
                "dependencies": [],
                "priority": 5,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "b",
                "title": "B",
                "description": "D",
                "dependencies": ["a"],
                "priority": 5,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "c",
                "title": "C",
                "description": "D",
                "dependencies": ["b"],
                "priority": 5,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        missions = builder.build_missions(plan, self.approved_request)
        self.assertEqual([m["mission_id"] for m in missions], ["M1", "M2", "M3"])  # dependencies respected

    def test_priority_tie_breaking(self) -> None:
        # independent, different priorities: lower integer first
        id_gen = make_id_generator(["P1", "P2"])  # assigned to beta then alpha
        builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=id_gen,
            clock=make_clock(self.clock_value),
        )
        steps = [
            {  # will receive P1
                "step_id": "beta",
                "title": "B",
                "description": "D",
                "dependencies": [],
                "priority": 2,  # lower priority (higher number)
                "task_type": "analysis",
                "payload": {},
            },
            {  # will receive P2
                "step_id": "alpha",
                "title": "A",
                "description": "D",
                "dependencies": [],
                "priority": 1,  # higher priority (lower number)
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        missions = builder.build_missions(plan, self.approved_request)
        # alpha (P2) should come before beta (P1) due to priority rule
        self.assertEqual([m["mission_id"] for m in missions], ["P2", "P1"])

    def test_step_id_tie_breaking(self) -> None:
        # equal priority; order by step_id asc
        id_gen = make_id_generator(["S1", "S2"])  # assigned beta then alpha
        builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=id_gen,
            clock=make_clock(self.clock_value),
        )
        steps = [
            {
                "step_id": "beta",
                "title": "B",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "alpha",
                "title": "A",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        missions = builder.build_missions(plan, self.approved_request)
        # alpha (S2) should come before beta (S1) due to step_id tiebreaker
        self.assertEqual([m["mission_id"] for m in missions], ["S2", "S1"])

    def test_dependency_before_dependant_ordering(self) -> None:
        id_gen = make_id_generator(["R", "S"])  # r then s
        builder = PlanValidatorMissionBuilder(
            supported_task_types=self.supported,
            id_generator=id_gen,
            clock=make_clock(self.clock_value),
        )
        steps = [
            {  # dependant defined before dependency intentionally
                "step_id": "r",
                "title": "R",
                "description": "D",
                "dependencies": ["s"],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
            {
                "step_id": "s",
                "title": "S",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            },
        ]
        plan = self._plan(steps)
        missions = builder.build_missions(plan, self.approved_request)
        # s must appear before r => [S, R]
        self.assertEqual([m["mission_id"] for m in missions], ["S", "R"])

    def test_result_redaction(self) -> None:
        steps = [
            {
                "step_id": "secure",
                "title": "Secrets",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {
                    "password": "supersecret",
                    "TOKEN": "abc",
                    "nested": [
                        {
                            "Authorization": "Bearer xyz",
                            "detail": "ok",
                            "Deep": {"Private_Key": "-----BEGIN"},
                        }
                    ],
                },
            }
        ]
        plan = self._plan(steps)
        missions = self.builder.build_missions(plan, self.approved_request)
        payload = missions[0]["payload"]
        self.assertEqual(payload["password"], "[redacted]")
        self.assertEqual(payload["TOKEN"], "[redacted]")
        self.assertEqual(payload["nested"][0]["Authorization"], "[redacted]")
        self.assertEqual(payload["nested"][0]["Deep"]["Private_Key"], "[redacted]")

    def test_unrelated_inputs_remain_unchanged(self) -> None:
        steps = [
            {
                "step_id": "a",
                "title": "T",
                "description": "D",
                "dependencies": ["b"],
                "priority": 1,
                "task_type": "analysis",
                "payload": {"note": "unchanged"},
            },
            {
                "step_id": "b",
                "title": "T2",
                "description": "D2",
                "dependencies": [],
                "priority": 2,
                "task_type": "analysis",
                "payload": {"note": "unchanged2"},
            },
        ]
        plan = self._plan(steps)
        original_plan = deepcopy(plan)
        _ = self.builder.build_missions(plan, self.approved_request)
        self.assertEqual(plan, original_plan)  # ensure no mutation of input plan

    def test_supported_task_type_enforcement(self) -> None:
        # Create builder that only supports 'analysis'; request uses 'plan' -> should fail approved request
        builder = PlanValidatorMissionBuilder(
            supported_task_types={"analysis"},
            id_generator=make_id_generator(["Z1"]),
            clock=make_clock(self.clock_value),
        )
        steps = [
            {
                "step_id": "a",
                "title": "T",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {},
            }
        ]
        plan = self._plan(steps)
        with self.assertRaises(InvalidApprovedRequestError):
            builder.build_missions(plan, self.approved_request)

    def test_json_unsafe_payload_rejection(self) -> None:
        class NonJSON:
            pass
        steps = [
            {
                "step_id": "a",
                "title": "T",
                "description": "D",
                "dependencies": [],
                "priority": 1,
                "task_type": "analysis",
                "payload": {"obj": NonJSON()},
            }
        ]
        plan = self._plan(steps)
        with self.assertRaises(UnsafePayloadError):
            self.builder.build_missions(plan, self.approved_request)


if __name__ == "__main__":
    unittest.main()
