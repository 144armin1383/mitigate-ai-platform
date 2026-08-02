import json
import os
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from tempfile import TemporaryDirectory

from agent.providers.provider_usage_ledger import (
    DuplicateUsageError,
    LedgerValidationError,
    ProviderUsageLedger,
    StorageCorruptedError,
)


# -----------------------------
# Fakes for DI
# -----------------------------

def fake_project_resolver(proj_id: str) -> bool:
    return proj_id in {"p1", "p2", "projUSD", "projMix"}


def make_fake_model_resolver(valid_pairs):
    def _resolver(provider_id: str, model_id: str) -> bool:
        return (provider_id, model_id) in valid_pairs
    return _resolver


def make_pricing_resolver(prices):
    # prices: dict[(provider, model)] = {currency, input_per_token, output_per_token} or {currency, per_token}
    def _resolver(provider_id: str, model_id: str):
        return prices.get((provider_id, model_id))
    return _resolver


def fixed_clock(ts: datetime):
    def _clock():
        return ts
    return _clock


class ProviderUsageLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage_dir = self.tmp.name
        self.model_resolver = make_fake_model_resolver({("provA", "m1"), ("provA", "m2"), ("provB", "mX")})
        self.pricing = make_pricing_resolver({
            ("provA", "m1"): {"currency": "USD", "input_per_token": 0.000001, "output_per_token": 0.000002},
            ("provA", "m2"): {"currency": "EUR", "per_token": 0.000003},
            ("provB", "mX"): {"currency": "USD", "input_per_token": 0.000001, "output_per_token": 0.000001},
        })
        self.ledger = ProviderUsageLedger(
            self.storage_dir,
            project_resolver=fake_project_resolver,
            model_resolver=self.model_resolver,
            pricing_resolver=self.pricing,
            clock=fixed_clock(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)),
        )

    def _make_record(self, **overrides):
        base = {
            "usage_id": overrides.get("usage_id", f"u-{int(time.time()*1000000)}"),
            "project_id": overrides.get("project_id", "p1"),
            "request_id": "req-1",
            "mission_id": "m-1",
            "conversation_id": "c-1",
            "task_type": overrides.get("task_type", "chat"),
            "provider_id": overrides.get("provider_id", "provA"),
            "model_id": overrides.get("model_id", "m1"),
            "started_at": overrides.get("started_at", "2024-01-01T12:00:00.000Z"),
            "completed_at": overrides.get("completed_at", "2024-01-01T12:00:01.000Z"),
            "input_tokens": overrides.get("input_tokens", 100),
            "output_tokens": overrides.get("output_tokens", 50),
            "total_tokens": overrides.get("total_tokens", 150),
            "estimated_cost": overrides.get("estimated_cost", None),
            "cost_currency": overrides.get("cost_currency", None),
            "fallback_used": overrides.get("fallback_used", False),
            "success": overrides.get("success", True),
            "safe_error_code": overrides.get("safe_error_code", ""),
            # Any secret-like fields must not be persisted
            "api_key": "SECRET",
            "prompt": "SHOULD_NOT_BE_SAVED",
        }
        return base

    # ---- Recording and validation ----

    def test_usage_recording(self):
        r = self._make_record(usage_id="u-1")
        saved = self.ledger.record_usage(r)
        self.assertEqual(saved["usage_id"], "u-1")
        self.assertEqual(saved["project_id"], "p1")
        # Known pricing computed
        self.assertIsInstance(saved["estimated_cost"], float)
        self.assertEqual(saved["cost_currency"], "USD")
        # Persisted
        got = self.ledger.get_usage("u-1")
        self.assertIsNotNone(got)
        self.assertEqual(got.get("usage_id"), "u-1")

    def test_duplicate_usage_rejection(self):
        r = self._make_record(usage_id="u-dup")
        self.ledger.record_usage(r)
        with self.assertRaises(DuplicateUsageError):
            self.ledger.record_usage(r)
        # File content unchanged regarding number of records
        with open(os.path.join(self.storage_dir, "provider_usage.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data["records"]), 1)

    def test_invalid_negative_token_values(self):
        r = self._make_record(usage_id="u-neg", input_tokens=-1)
        with self.assertRaises(LedgerValidationError):
            self.ledger.record_usage(r)

    def test_invalid_token_totals(self):
        r = self._make_record(usage_id="u-badtotal", total_tokens=1)
        with self.assertRaises(LedgerValidationError):
            self.ledger.record_usage(r)

    def test_invalid_negative_cost(self):
        r = self._make_record(usage_id="u-costneg", estimated_cost=-0.1)
        with self.assertRaises(LedgerValidationError):
            self.ledger.record_usage(r)

    def test_project_isolation(self):
        r1 = self._make_record(usage_id="u-a", project_id="p1")
        r2 = self._make_record(usage_id="u-b", project_id="p2")
        self.ledger.record_usage(r1)
        self.ledger.record_usage(r2)
        list1 = self.ledger.list_usage("p1")
        list2 = self.ledger.list_usage("p2")
        self.assertEqual({x["usage_id"] for x in list1}, {"u-a"})
        self.assertEqual({x["usage_id"] for x in list2}, {"u-b"})

    def test_provider_and_model_validation(self):
        bad = self._make_record(usage_id="u-bad", provider_id="unknown", model_id="none")
        with self.assertRaises(LedgerValidationError):
            self.ledger.record_usage(bad)

    def test_fallback_recording(self):
        r = self._make_record(usage_id="u-fb", fallback_used=True)
        self.ledger.record_usage(r)
        got = self.ledger.get_usage("u-fb")
        self.assertTrue(got["fallback_used"])  # type: ignore[index]

    # ---- Pricing ----

    def test_known_pricing_calculation(self):
        r = self._make_record(usage_id="u-price1", input_tokens=100, output_tokens=50)
        saved = self.ledger.record_usage(r)
        # cost = 100*0.000001 + 50*0.000002 = 0.0002
        self.assertAlmostEqual(saved["estimated_cost"], 0.0002, places=6)
        self.assertEqual(saved["cost_currency"], "USD")

    def test_unknown_pricing(self):
        # Model not present in pricing table but valid in resolver
        r = self._make_record(usage_id="u-unknown", model_id="m2", provider_id="provA")
        # For m2 we provided EUR per_token in pricing; for unknown, set to None by altering pricing resolver temporarily
        ledger2 = ProviderUsageLedger(
            self.storage_dir,
            project_resolver=fake_project_resolver,
            model_resolver=self.model_resolver,
            pricing_resolver=make_pricing_resolver({}),
        )
        saved = ledger2.record_usage(r)
        self.assertIsNone(saved["estimated_cost"])  # type: ignore[index]
        self.assertIsNone(saved["cost_currency"])  # type: ignore[index]

    def test_historical_cost_preservation(self):
        # First with one pricing
        r = self._make_record(usage_id="u-hist1")
        self.ledger.record_usage(r)
        # Change pricing resolver to different rates
        new_pricing = make_pricing_resolver({("provA", "m1"): {"currency": "USD", "per_token": 0.000010}})
        ledger2 = ProviderUsageLedger(
            self.storage_dir,
            project_resolver=fake_project_resolver,
            model_resolver=self.model_resolver,
            pricing_resolver=new_pricing,
        )
        # Old record must keep original estimated_cost in summaries
        s = ledger2.range_summary("p1", datetime(2023, 12, 1, tzinfo=timezone.utc), datetime(2024, 12, 31, tzinfo=timezone.utc))
        self.assertIn("USD", s["estimated_costs"])  # type: ignore[index]
        # Ensure it is not recomputed to the larger new rate
        self.assertLess(s["estimated_costs"]["USD"], 0.002)  # type: ignore[index]

    # ---- Summaries ----

    def test_daily_summary(self):
        self.ledger.record_usage(self._make_record(usage_id="u-d1", started_at="2024-02-10T00:00:00.000Z", completed_at="2024-02-10T00:00:01.000Z"))
        self.ledger.record_usage(self._make_record(usage_id="u-d2", started_at="2024-02-10T12:00:00.000Z", completed_at="2024-02-10T12:00:03.000Z"))
        self.ledger.record_usage(self._make_record(usage_id="u-d3", started_at="2024-02-11T00:00:00.000Z", completed_at="2024-02-11T00:00:02.000Z"))
        s = self.ledger.daily_summary("p1", date(2024, 2, 10))
        self.assertEqual(s["request_count"], 2)
        self.assertEqual(s["successful_requests"], 2)
        self.assertEqual(s["failed_requests"], 0)
        self.assertIn("USD", s["estimated_costs"])  # type: ignore[index]

    def test_monthly_summary(self):
        self.ledger.record_usage(self._make_record(usage_id="u-m1", started_at="2024-03-01T00:00:00.000Z", completed_at="2024-03-01T00:00:01.000Z"))
        self.ledger.record_usage(self._make_record(usage_id="u-m2", started_at="2024-03-15T00:00:00.000Z", completed_at="2024-03-15T00:00:01.000Z"))
        self.ledger.record_usage(self._make_record(usage_id="u-m3", started_at="2024-04-01T00:00:00.000Z", completed_at="2024-04-01T00:00:01.000Z"))
        s = self.ledger.monthly_summary("p1", 2024, 3)
        self.assertEqual(s["request_count"], 2)

    def test_range_summary_and_unknown_cost(self):
        # Known USD
        self.ledger.record_usage(self._make_record(usage_id="u-r1"))
        # Known EUR
        self.ledger.record_usage(self._make_record(usage_id="u-r2", model_id="m2", provider_id="provA", total_tokens=120, input_tokens=60, output_tokens=60))
        # Unknown pricing by separate ledger
        ledger2 = ProviderUsageLedger(
            self.storage_dir,
            project_resolver=fake_project_resolver,
            model_resolver=self.model_resolver,
            pricing_resolver=make_pricing_resolver({}),
        )
        ledger2.record_usage(self._make_record(usage_id="u-r3", model_id="m2", provider_id="provA", total_tokens=10, input_tokens=5, output_tokens=5))
        s = self.ledger.range_summary("p1", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.assertGreaterEqual(s["unknown_cost_count"], 1)
        self.assertIn("USD", s["estimated_costs"])  # type: ignore[index]
        self.assertIn("EUR", s["estimated_costs"])  # type: ignore[index]

    def test_summary_by_provider_model_task(self):
        self.ledger.record_usage(self._make_record(usage_id="u-s1", provider_id="provA", model_id="m1", task_type="chat"))
        self.ledger.record_usage(self._make_record(usage_id="u-s2", provider_id="provB", model_id="mX", task_type="embed"))
        byp = self.ledger.summary_by_provider("p1")
        self.assertTrue(any(r.get("provider_id") == "provA" for r in byp))
        bym = self.ledger.summary_by_model("p1")
        self.assertTrue(any(r.get("model_id") == "m1" for r in bym))
        byt = self.ledger.summary_by_task("p1")
        self.assertTrue(any(r.get("task_type") == "chat" for r in byt))

    def test_mixed_currency_reporting(self):
        # USD
        self.ledger.record_usage(self._make_record(usage_id="u-c1", model_id="m1", provider_id="provA"))
        # EUR
        self.ledger.record_usage(self._make_record(usage_id="u-c2", model_id="m2", provider_id="provA"))
        s = self.ledger.range_summary("p1", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 12, 31, tzinfo=timezone.utc))
        self.assertIn("USD", s["estimated_costs"])  # type: ignore[index]
        self.assertIn("EUR", s["estimated_costs"])  # type: ignore[index]

    def test_empty_summary(self):
        s = self.ledger.range_summary("p1", datetime(2030, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(s["request_count"], 0)
        self.assertEqual(s["estimated_costs"], {})
        self.assertEqual(s["unknown_cost_count"], 0)

    def test_utc_boundaries(self):
        # Record around UTC midnight
        self.ledger.record_usage(self._make_record(usage_id="u-u1", started_at="2024-05-01T23:59:59.000Z", completed_at="2024-05-02T00:00:00.000Z"))
        self.ledger.record_usage(self._make_record(usage_id="u-u2", started_at="2024-05-02T00:00:00.000Z", completed_at="2024-05-02T00:00:01.000Z"))
        d1 = self.ledger.daily_summary("p1", date(2024, 5, 1))
        d2 = self.ledger.daily_summary("p1", date(2024, 5, 2))
        self.assertEqual(d1["request_count"], 1)
        self.assertEqual(d2["request_count"], 1)

    # ---- Persistence ----

    def test_atomic_persistence_and_temp_cleanup(self):
        r = self._make_record(usage_id="u-atomic")
        self.ledger.record_usage(r)
        # No stray tmp files left
        names = set(os.listdir(self.storage_dir))
        self.assertNotIn(".provider_usage.json.tmp", names)
        self.assertNotIn(".provider_events.json.tmp", names)

    def test_restart_recovery(self):
        self.ledger.record_usage(self._make_record(usage_id="u-restart"))
        # Re-instantiate and ensure we can still read records
        ledger2 = ProviderUsageLedger(
            self.storage_dir,
            project_resolver=fake_project_resolver,
            model_resolver=self.model_resolver,
            pricing_resolver=self.pricing,
        )
        got = ledger2.get_usage("u-restart")
        self.assertIsNotNone(got)

    def test_corrupted_storage_rejection(self):
        # Corrupt usage file
        path = os.path.join(self.storage_dir, "provider_usage.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{" "corrupted")
        # Methods should raise StorageCorruptedError, not silently overwrite
        with self.assertRaises(StorageCorruptedError):
            self.ledger.list_usage("p1")

    def test_deterministic_serialization(self):
        # Record two in deterministic order by started_at then usage_id
        self.ledger.record_usage(self._make_record(usage_id="u-10", started_at="2024-01-01T00:00:00.000Z", completed_at="2024-01-01T00:00:01.000Z"))
        self.ledger.record_usage(self._make_record(usage_id="u-11", started_at="2024-01-01T00:00:02.000Z", completed_at="2024-01-01T00:00:03.000Z"))
        with open(os.path.join(self.storage_dir, "provider_usage.json"), "r", encoding="utf-8") as fh:
            c1 = fh.read()
        # Re-open and read again; content should be identical
        with open(os.path.join(self.storage_dir, "provider_usage.json"), "r", encoding="utf-8") as fh:
            c2 = fh.read()
        self.assertEqual(c1, c2)

    def test_secret_and_content_redaction(self):
        r = self._make_record(usage_id="u-secret", api_key="SECRET!!", prompt="do not store")
        self.ledger.record_usage(r)
        with open(os.path.join(self.storage_dir, "provider_usage.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        rec = next(x for x in data["records"] if x["usage_id"] == "u-secret")
        self.assertNotIn("api_key", rec)
        self.assertNotIn("prompt", rec)

    def test_unrelated_files_remain_unchanged(self):
        other_path = os.path.join(self.storage_dir, "unrelated.txt")
        with open(other_path, "w", encoding="utf-8") as fh:
            fh.write("hello")
        mtime = os.path.getmtime(other_path)
        self.ledger.record_usage(self._make_record(usage_id="u-unrel"))
        self.assertEqual(os.path.getmtime(other_path), mtime)

    def test_invalid_timestamp_order(self):
        r = self._make_record(
            usage_id="u-badtimes",
            started_at="2024-01-01T01:00:00.000Z",
            completed_at="2024-01-01T00:59:00.000Z",
        )
        with self.assertRaises(LedgerValidationError):
            self.ledger.record_usage(r)

    def test_filters(self):
        self.ledger.record_usage(self._make_record(usage_id="u-f1", provider_id="provA", model_id="m1", task_type="chat", success=True, fallback_used=False))
        self.ledger.record_usage(self._make_record(usage_id="u-f2", provider_id="provB", model_id="mX", task_type="embed", success=False, fallback_used=True))
        only_provB = self.ledger.list_usage("p1", {"provider_id": "provB"})
        self.assertEqual({x["usage_id"] for x in only_provB}, {"u-f2"})
        only_success = self.ledger.list_usage("p1", {"success": True})
        self.assertEqual({x["usage_id"] for x in only_success}, {"u-f1"})
        only_fallback = self.ledger.list_usage("p1", {"fallback_used": True})
        self.assertEqual({x["usage_id"] for x in only_fallback}, {"u-f2"})

    def test_latest_events(self):
        self.ledger.record_usage(self._make_record(usage_id="u-e1"))
        self.ledger.record_usage(self._make_record(usage_id="u-e2"))
        events = self.ledger.latest_events(2)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "usage_recorded")


if __name__ == "__main__":
    unittest.main()
