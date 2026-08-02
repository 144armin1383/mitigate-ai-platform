import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional

from agent.providers.provider_budget_limit_evaluator import ProviderBudgetLimitEvaluator


class FakeBudgetStore:
    def __init__(self, budgets: Optional[Dict[str, Mapping[str, Any]]] = None) -> None:
        self._budgets = budgets or {}

    def get_project_budget(self, project_id: str) -> Optional[Mapping[str, Any]]:
        return self._budgets.get(project_id)


class FakeUsageLedger:
    def __init__(self) -> None:
        # Usage figures per project
        self.daily_tokens: Dict[str, int] = {}
        self.monthly_tokens: Dict[str, int] = {}
        self.daily_cost: Dict[str, float] = {}
        self.monthly_cost: Dict[str, float] = {}
        self.call_count: int = 0

    def usage_summary(self, project_id: str, start: datetime, end: datetime) -> Mapping[str, Optional[float | int]]:
        # We consider a 'daily' period if it spans exactly 1 day; otherwise monthly
        self.call_count += 1
        if (end - start) == timedelta(days=1):
            return {
                "tokens": self.daily_tokens.get(project_id),
                "cost": self.daily_cost.get(project_id),
            }
        else:
            return {
                "tokens": self.monthly_tokens.get(project_id),
                "cost": self.monthly_cost.get(project_id),
            }


class FakeProjectResolver:
    def __init__(self, known: Optional[Dict[str, bool]] = None) -> None:
        self._known = known or {}

    def is_known_project(self, project_id: str) -> bool:
        return self._known.get(project_id, False)

    def is_valid_reference(self, project_id: str, request: Mapping[str, Any]) -> bool:
        # For tests: reject if request_id embeds another project prefix like "other:"
        rid = str(request.get("request_id", ""))
        return not rid.startswith("other:")


class FakeModelResolver:
    def __init__(self, providers_models: Optional[Dict[str, set[str]]] = None) -> None:
        # mapping provider -> set(models)
        self._pm = providers_models or {}

    def is_valid_provider(self, provider_id: str) -> bool:
        return provider_id in self._pm

    def is_valid_model(self, provider_id: str, model_id: str) -> bool:
        return provider_id in self._pm and model_id in self._pm[provider_id]


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def make_request(
    project_id: str,
    request_id: str,
    provider_id: str = "prov",
    model_id: str = "m1",
    est_in: int = 10,
    req_out: int = 10,
    est_cost: Optional[float] = 1.0,
    ts: Optional[datetime] = None,
) -> Mapping[str, Any]:
    return {
        "project_id": project_id,
        "request_id": request_id,
        "task_type": "chat",
        "provider_id": provider_id,
        "model_id": model_id,
        "estimated_input_tokens": est_in,
        "requested_output_tokens": req_out,
        "estimated_cost": est_cost,
        "cost_currency": "USD",
        "request_timestamp": ts or datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    }


class TestProviderBudgetLimitEvaluator(unittest.TestCase):
    def setUp(self) -> None:
        self.base_time = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        self.clock = FixedClock(self.base_time)
        self.ledger = FakeUsageLedger()
        self.project_resolver = FakeProjectResolver({"p1": True, "p2": True})
        self.model_resolver = FakeModelResolver({"prov": {"m1", "m2"}})

    def test_missing_configuration_allowed_result(self) -> None:
        store = FakeBudgetStore({})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r1", est_cost=0.5, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertTrue(decision["allowed"])  # missing config must allow
        self.assertIsNone(decision["blocked_reason"])  # no block reason
        self.assertTrue(decision["pricing_known"])  # cost provided
        # Remaining fields should be None when not configured
        self.assertIsNone(decision["remaining_daily_tokens"])
        self.assertIsNone(decision["remaining_monthly_tokens"])
        self.assertIsNone(decision["remaining_daily_budget"])
        self.assertIsNone(decision["remaining_monthly_budget"])

    def test_per_request_input_token_block(self) -> None:
        store = FakeBudgetStore({
            "p1": {"per_request": {"max_input_tokens": 100}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r2", est_in=101, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "per_request_input_token_limit_exceeded")

    def test_per_request_output_token_block(self) -> None:
        store = FakeBudgetStore({
            "p1": {"per_request": {"max_output_tokens": 50}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r3", req_out=51, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "per_request_output_token_limit_exceeded")

    def test_per_request_budget_block(self) -> None:
        store = FakeBudgetStore({
            "p1": {"per_request": {"max_cost": 1.0}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r4", est_cost=1.01, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "per_request_budget_exceeded")

    def test_daily_token_block(self) -> None:
        self.ledger.daily_tokens["p1"] = 900
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 1000}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # Request would add 150 tokens -> 1050 > 1000
        req = make_request("p1", "r5", est_in=100, req_out=50, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "daily_token_limit_exceeded")

    def test_monthly_token_block(self) -> None:
        self.ledger.daily_tokens["p1"] = 100  # ensure daily would pass
        self.ledger.monthly_tokens["p1"] = 9950
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 5000}, "monthly": {"token_limit": 10000}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # Request adds 100 -> 9950 + 100 = 10050 > 10000
        req = make_request("p1", "r6", est_in=70, req_out=30, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "monthly_token_limit_exceeded")

    def test_daily_budget_block(self) -> None:
        self.ledger.daily_cost["p1"] = 9.5
        store = FakeBudgetStore({
            "p1": {"daily": {"budget_limit": 10.0}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r7", est_cost=1.0, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "daily_budget_limit_exceeded")

    def test_monthly_budget_block(self) -> None:
        self.ledger.monthly_cost["p1"] = 99.9
        store = FakeBudgetStore({
            "p1": {"monthly": {"budget_limit": 100.0}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r8", est_cost=0.2, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # block
        self.assertEqual(decision["blocked_reason"], "monthly_budget_limit_exceeded")

    def test_unknown_pricing_allow(self) -> None:
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 10000}, "unknown_pricing_policy": "allow"},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r9", est_cost=None, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertTrue(decision["allowed"])  # allowed per policy
        self.assertFalse(decision["warning"])  # no warning on allow policy
        self.assertFalse(decision["pricing_known"])  # unknown pricing

    def test_unknown_pricing_warn(self) -> None:
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 10000}, "unknown_pricing_policy": "warn"},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r10", est_cost=None, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertTrue(decision["allowed"])  # permitted
        self.assertTrue(decision["warning"])  # warned per policy
        self.assertFalse(decision["pricing_known"])  # still unknown

    def test_unknown_pricing_block(self) -> None:
        store = FakeBudgetStore({
            "p1": {"unknown_pricing_policy": "block"},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r11", est_cost=None, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # blocked
        self.assertEqual(decision["blocked_reason"], "unknown_pricing_blocked")

    def test_exact_decision_order(self) -> None:
        # Multiple possible blocks: per-request input and daily token. Must block at per-request input first.
        self.ledger.daily_tokens["p1"] = 999999  # would also fail daily with any add
        store = FakeBudgetStore({
            "p1": {
                "per_request": {"max_input_tokens": 1},
                "daily": {"token_limit": 10},
            }
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # estimated_input_tokens=2 exceeds per-request limit first in order
        req = make_request("p1", "r12", est_in=2, req_out=1, est_cost=0.1, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertEqual(decision["blocked_reason"], "per_request_input_token_limit_exceeded")

    def test_deterministic_blocked_reasons(self) -> None:
        # Craft a scenario where monthly budget and daily token could both be issues but order enforces token checks before budget checks
        self.ledger.daily_tokens["p1"] = 990
        self.ledger.monthly_tokens["p1"] = 100
        self.ledger.daily_cost["p1"] = 0.0
        store = FakeBudgetStore({
            "p1": {
                "daily": {"token_limit": 1000, "budget_limit": 1.0},
                "monthly": {"token_limit": 10000, "budget_limit": 100.0},
            }
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r13", est_in=8, req_out=5, est_cost=1.01, ts=self.base_time)  # tokens would be 1003 -> block on daily token before budget
        decision = ev.check_request("p1", req)
        self.assertEqual(decision["blocked_reason"], "daily_token_limit_exceeded")

    def test_soft_warning_behavior(self) -> None:
        # Soft warning at 80% threshold
        self.ledger.daily_tokens["p1"] = 750
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 1000}, "soft_warning_percent": 80.0},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # projected = 750 + 50 = 800 which is 80% of 1000 -> warning only, not blocked
        req = make_request("p1", "r14", est_in=25, req_out=25, est_cost=0.1, ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertTrue(decision["allowed"])  # soft warning must not block
        self.assertTrue(decision["warning"])  # must warn
        self.assertIsNone(decision["blocked_reason"])  # not blocked

    def test_preflight_does_not_record_usage(self) -> None:
        self.ledger.daily_tokens["p1"] = 100
        self.ledger.monthly_tokens["p1"] = 1000
        calls_before = self.ledger.call_count
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 10000}, "monthly": {"token_limit": 20000}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r15", est_in=10, req_out=5, est_cost=0.1, ts=self.base_time)
        decision1 = ev.check_request("p1", req)
        decision2 = ev.check_request("p1", req)
        self.assertGreaterEqual(self.ledger.call_count, calls_before)
        # Usage should not have been deducted/recorded; remainings the same across calls
        self.assertEqual(decision1["remaining_daily_tokens"], decision2["remaining_daily_tokens"])
        self.assertEqual(decision1["remaining_monthly_tokens"], decision2["remaining_monthly_tokens"])

    def test_utc_daily_and_monthly_boundaries(self) -> None:
        # Request at end of month/day must use correct UTC boundaries
        ts = datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
        self.ledger.daily_tokens["p1"] = 100
        self.ledger.monthly_tokens["p1"] = 500
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 1000}, "monthly": {"token_limit": 10000}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, FixedClock(ts))
        req = make_request("p1", "r16", est_in=10, req_out=10, est_cost=0.2, ts=ts)
        decision = ev.check_request("p1", req)
        # Remaining should be computed against provided usage and not negative
        self.assertEqual(decision["remaining_daily_tokens"], 900)
        self.assertEqual(decision["remaining_monthly_tokens"], 9500)

    def test_project_isolation(self) -> None:
        # Configure p1; p2 usage must not impact p1
        self.ledger.daily_tokens["p1"] = 100
        self.ledger.monthly_tokens["p2"] = 999999  # irrelevant to p1
        store = FakeBudgetStore({
            "p1": {"daily": {"token_limit": 1000}},
            "p2": {"daily": {"token_limit": 10}},
        })
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req1 = make_request("p1", "r17", ts=self.base_time)
        decision1 = ev.check_request("p1", req1)
        self.assertTrue(decision1["allowed"])  # allowed for p1
        self.assertEqual(decision1["remaining_daily_tokens"], 900)

    def test_provider_and_model_validation(self) -> None:
        # Unknown provider or model must be rejected when resolver configured
        store = FakeBudgetStore({"p1": {"daily": {"token_limit": 10000}}})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # Invalid provider
        req_bad_provider = make_request("p1", "r18", provider_id="unknown", model_id="mX", ts=self.base_time)
        decision_p = ev.check_request("p1", req_bad_provider)
        self.assertFalse(decision_p["allowed"])  # blocked
        self.assertEqual(decision_p["blocked_reason"], "invalid_provider_or_model")
        # Invalid model for known provider
        req_bad_model = make_request("p1", "r19", provider_id="prov", model_id="nope", ts=self.base_time)
        decision_m = ev.check_request("p1", req_bad_model)
        self.assertFalse(decision_m["allowed"])  # blocked
        self.assertEqual(decision_m["blocked_reason"], "invalid_provider_or_model")

    def test_negative_estimate_rejection(self) -> None:
        store = FakeBudgetStore({"p1": {"daily": {"token_limit": 10000}}})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # Negative tokens
        req_neg_tokens = make_request("p1", "r20", est_in=-1, ts=self.base_time)
        decision_t = ev.check_request("p1", req_neg_tokens)
        self.assertFalse(decision_t["allowed"])  # invalid
        self.assertEqual(decision_t["blocked_reason"], "invalid_token_estimate")
        # Negative cost
        req_neg_cost = make_request("p1", "r21", est_cost=-0.1, ts=self.base_time)
        decision_c = ev.check_request("p1", req_neg_cost)
        self.assertFalse(decision_c["allowed"])  # invalid
        self.assertEqual(decision_c["blocked_reason"], "invalid_estimated_cost")

    def test_unknown_field_rejection(self) -> None:
        store = FakeBudgetStore({"p1": {"daily": {"token_limit": 10000}}})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p1", "r22", ts=self.base_time)
        # Inject an unknown field
        req = dict(req)
        req["unexpected"] = True
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # invalid
        self.assertEqual(decision["blocked_reason"], "unknown_fields")

    def test_deterministic_result_serialization(self) -> None:
        # Ensure stable JSON serialization and evaluated_at equals fixed clock
        store = FakeBudgetStore({"p1": {"daily": {"token_limit": 10000}}})
        fixed_now = datetime(2027, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
        clock = FixedClock(fixed_now)
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, clock)
        req = make_request("p1", "r23", ts=fixed_now)
        decision = ev.check_request("p1", req)
        # JSON serialize roundtrip
        s = json.dumps(decision, sort_keys=True)
        obj = json.loads(s)
        self.assertEqual(obj["evaluated_at"], fixed_now.isoformat())
        self.assertEqual(obj["project_id"], "p1")
        self.assertEqual(obj["request_id"], "r23")

    def test_timestamp_validation_must_be_utc_aware(self) -> None:
        store = FakeBudgetStore({"p1": {"daily": {"token_limit": 10000}}})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # Naive timestamp
        naive_ts = datetime(2026, 1, 15, 12, 0, 0)
        req = make_request("p1", "r24", ts=naive_ts)  # type: ignore[arg-type]
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # invalid
        self.assertEqual(decision["blocked_reason"], "invalid_timestamp")

    def test_unknown_project_blocked_when_resolver_configured(self) -> None:
        # p3 is not known by resolver
        store = FakeBudgetStore({"p3": {"daily": {"token_limit": 10000}}})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        req = make_request("p3", "r25", ts=self.base_time)
        decision = ev.check_request("p3", req)
        self.assertFalse(decision["allowed"])  # blocked by unknown project
        self.assertEqual(decision["blocked_reason"], "unknown_project")

    def test_cross_project_reference_rejection(self) -> None:
        store = FakeBudgetStore({"p1": {"daily": {"token_limit": 10000}}})
        ev = ProviderBudgetLimitEvaluator(store, self.ledger, self.project_resolver, self.model_resolver, self.clock)
        # project_id mismatch
        req = make_request("p2", "r26", ts=self.base_time)
        decision = ev.check_request("p1", req)
        self.assertFalse(decision["allowed"])  # invalid
        self.assertEqual(decision["blocked_reason"], "cross_project_reference")
        # resolver explicit reference invalidation
        req2 = make_request("p1", "other:r27", ts=self.base_time)
        decision2 = ev.check_request("p1", req2)
        self.assertFalse(decision2["allowed"])  # invalid per resolver
        self.assertEqual(decision2["blocked_reason"], "cross_project_reference")


if __name__ == "__main__":
    unittest.main()
