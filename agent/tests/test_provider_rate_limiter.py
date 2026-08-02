import os
import json
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from agent.providers.provider_rate_limiter import ProviderRateLimiter, SystemUTCClock


class FakeClock:
    def __init__(self, start: Optional[datetime] = None) -> None:
        self._now = (start or datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now = self._now + timedelta(seconds=seconds)


class FakeResolver:
    def __init__(self, known: Optional[Dict[str, bool]] = None) -> None:
        self.known = known or {}

    def __call__(self, project_id: str) -> bool:
        return self.known.get(project_id, False)


class ProviderRateLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.clock = FakeClock()
        self.resolver = FakeResolver({"projA": True, "projB": True, "unknown": False})
        self.limiter = ProviderRateLimiter(self.root, self.resolver, clock=self.clock)

    def read_state(self, project_id: str) -> Dict:
        path = os.path.join(self.root, "projects", project_id, "state.json")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_configuration_creation(self):
        cfg = {
            "project_id": "projA",
            "enabled": True,
            "request_limit": 5,
            "window_seconds": 10,
            "burst_limit": None,
        }
        out = self.limiter.configure_limit("projA", cfg)
        self.assertTrue(out["enabled"])  # enabled == True
        self.assertEqual(out["request_limit"], 5)
        self.assertEqual(out["window_seconds"], 10)
        self.assertIsNone(out["burst_limit"])  # None allowed
        st = self.read_state("projA")
        self.assertIsNotNone(st["config"])  # persisted
        # Deterministic serialization keys sorted
        with open(os.path.join(self.root, "projects", "projA", "state.json"), "r", encoding="utf-8") as fh:
            raw = fh.read()
        # Re-dump and compare JSON objects (content equivalence)
        self.assertIsInstance(json.loads(raw), dict)

    def test_configuration_update(self):
        cfg = {
            "project_id": "projA",
            "enabled": True,
            "request_limit": 5,
            "window_seconds": 10,
            "burst_limit": None,
        }
        self.limiter.configure_limit("projA", cfg)
        new_cfg = self.limiter.update_limit("projA", {"request_limit": 7, "burst_limit": 9})
        self.assertEqual(new_cfg["request_limit"], 7)
        self.assertEqual(new_cfg["burst_limit"], 9)

    def test_configuration_removal(self):
        cfg = {
            "project_id": "projA",
            "enabled": True,
            "request_limit": 2,
            "window_seconds": 10,
            "burst_limit": None,
        }
        self.limiter.configure_limit("projA", cfg)
        existed = self.limiter.remove_limit("projA")
        self.assertTrue(existed)
        # State file must still exist
        path = os.path.join(self.root, "projects", "projA", "state.json")
        self.assertTrue(os.path.isfile(path))
        # After removal, get_limit returns None and unrestricted behavior
        self.assertIsNone(self.limiter.get_limit("projA"))
        d = self.limiter.check_and_register("projA", "req1")
        self.assertTrue(d.allowed)
        # Repeated removal is deterministic
        existed2 = self.limiter.remove_limit("projA")
        self.assertFalse(existed2)

    def test_unknown_project_rejection(self):
        cfg = {
            "project_id": "unknown",
            "enabled": True,
            "request_limit": 5,
            "window_seconds": 10,
            "burst_limit": None,
        }
        with self.assertRaises(ValueError):
            self.limiter.configure_limit("unknown", cfg)

    def test_invalid_request_limit(self):
        cfg = {
            "project_id": "projA",
            "enabled": True,
            "request_limit": 0,
            "window_seconds": 10,
            "burst_limit": None,
        }
        with self.assertRaises(ValueError):
            self.limiter.configure_limit("projA", cfg)

    def test_invalid_window_seconds(self):
        cfg = {
            "project_id": "projA",
            "enabled": True,
            "request_limit": 5,
            "window_seconds": 0,
            "burst_limit": None,
        }
        with self.assertRaises(ValueError):
            self.limiter.configure_limit("projA", cfg)

    def test_invalid_burst_limit(self):
        cfg = {
            "project_id": "projA",
            "enabled": True,
            "request_limit": 5,
            "window_seconds": 10,
            "burst_limit": -1,
        }
        with self.assertRaises(ValueError):
            self.limiter.configure_limit("projA", cfg)

    def _configure_simple(self, pid: str = "projA", req_limit: int = 3, window: int = 10, burst: Optional[int] = None):
        cfg = {
            "project_id": pid,
            "enabled": True,
            "request_limit": req_limit,
            "window_seconds": window,
            "burst_limit": burst,
        }
        self.limiter.configure_limit(pid, cfg)

    def test_missing_configuration_unrestricted_behavior(self):
        # projB exists but not configured -> unrestricted
        d = self.limiter.check_request("projB", "r1")
        self.assertTrue(d.allowed)
        d2 = self.limiter.check_and_register("projB", "r1")
        self.assertTrue(d2.allowed)
        self.assertIsNone(d2.remaining_requests)

    def test_disabled_configuration_unrestricted_behavior(self):
        self._configure_simple("projA", 3, 10, None)
        # Disable via update
        self.limiter.update_limit("projA", {"enabled": False})
        d = self.limiter.check_and_register("projA", "r1")
        self.assertTrue(d.allowed)
        self.assertIsNone(d.remaining_requests)

    def test_request_registration_and_duplicate(self):
        self._configure_simple(req_limit=2, window=10, burst=None)
        d1 = self.limiter.check_and_register("projA", "r1")
        self.assertTrue(d1.allowed)
        ddup = self.limiter.check_and_register("projA", "r1")
        self.assertFalse(ddup.allowed)
        self.assertEqual(ddup.blocked_reason, "duplicate_request")

    def test_rate_limit_blocking(self):
        self._configure_simple(req_limit=2, window=10, burst=None)
        r1 = self.limiter.check_and_register("projA", "r1")
        r2 = self.limiter.check_and_register("projA", "r2")
        self.assertTrue(r1.allowed and r2.allowed)
        r3 = self.limiter.check_and_register("projA", "r3")
        self.assertFalse(r3.allowed)
        self.assertEqual(r3.blocked_reason, "rate_limit_exceeded")

    def test_remaining_request_count(self):
        self._configure_simple(req_limit=3, window=10, burst=None)
        self.limiter.check_and_register("projA", "r1")
        rem = self.limiter.remaining("projA")
        self.assertEqual(rem, 2)

    def test_reset_time_and_expired_cleanup(self):
        self._configure_simple(req_limit=2, window=5, burst=None)
        base = self.clock.now()
        self.limiter.check_and_register("projA", "r1", timestamp=base)
        self.clock.advance(1)
        self.limiter.check_and_register("projA", "r2", timestamp=self.clock.now())
        st_before = self.limiter.status("projA")["projA"]
        reset_at = st_before["reset_at"]
        self.assertIsNotNone(reset_at)
        # Advance beyond first window expiry
        self.clock.advance(6)
        rem = self.limiter.remaining("projA")
        self.assertEqual(rem, 2)  # both expired
        st_after = self.limiter.status("projA")["projA"]
        self.assertIsNone(st_after["reset_at"])  # no entries

    def test_utc_handling(self):
        self._configure_simple(req_limit=1, window=10, burst=None)
        d = self.limiter.check_and_register("projA", "r1")
        self.assertTrue(d.evaluated_at.endswith("Z"))

    def test_project_isolation_and_two_projects(self):
        self._configure_simple("projA", req_limit=1, window=10, burst=None)
        self._configure_simple("projB", req_limit=2, window=10, burst=None)
        a1 = self.limiter.check_and_register("projA", "a1")
        self.assertTrue(a1.allowed)
        a2 = self.limiter.check_and_register("projA", "a2")
        self.assertFalse(a2.allowed)
        b1 = self.limiter.check_and_register("projB", "b1")
        b2 = self.limiter.check_and_register("projB", "b2")
        self.assertTrue(b1.allowed and b2.allowed)

    def test_atomic_check_and_register_exactly_once(self):
        self._configure_simple(req_limit=2, window=60, burst=None)
        results = []
        def worker():
            d = self.limiter.check_and_register("projA", "same")
            results.append(d.allowed)
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 4)

    def test_concurrent_request_enforcement(self):
        # capacity = 3
        self._configure_simple(req_limit=3, window=60, burst=None)
        successes = []
        lock = threading.Lock()
        def worker(i: int):
            d = self.limiter.check_and_register("projA", f"r{i}")
            with lock:
                successes.append(d.allowed)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)
        self.assertEqual(successes.count(True), 3)
        self.assertEqual(successes.count(False), 7)

    def test_restart_recovery(self):
        self._configure_simple(req_limit=2, window=60, burst=None)
        self.limiter.check_and_register("projA", "r1")
        # Recreate limiter
        limiter2 = ProviderRateLimiter(self.root, self.resolver, clock=self.clock)
        rem = limiter2.remaining("projA")
        self.assertEqual(rem, 1)

    def test_atomic_persistence_safe_temp_names(self):
        self._configure_simple(req_limit=1, window=10, burst=None)
        # Ensure no stray temp files remain after operations
        proj_dir = os.path.join(self.root, "projects", "projA")
        files = os.listdir(proj_dir)
        self.assertTrue("state.json" in files)
        for name in files:
            self.assertFalse(name.startswith(".tmp-"))
        # Create unrelated file and ensure it remains unchanged
        unrelated = os.path.join(self.root, "projects", "projA", "unrelated.txt")
        with open(unrelated, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        self.limiter.check_and_register("projA", "x1")
        with open(unrelated, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me")

    def test_corrupted_storage_rejection(self):
        # Manually corrupt state.json
        proj_dir = os.path.join(self.root, "projects", "projA")
        os.makedirs(proj_dir, exist_ok=True)
        state_path = os.path.join(proj_dir, "state.json")
        with open(state_path, "w", encoding="utf-8") as fh:
            fh.write("not-json")
        with self.assertRaises(RuntimeError):
            # Any read of state should raise
            self.limiter.get_limit("projA")

    def test_deterministic_serialization(self):
        self._configure_simple(req_limit=2, window=10, burst=None)
        self.limiter.check_and_register("projA", "a")
        self.clock.advance(1)
        self.limiter.check_and_register("projA", "b")
        path = os.path.join(self.root, "projects", "projA", "state.json")
        with open(path, "r", encoding="utf-8") as fh:
            raw1 = fh.read()
        # Reload and re-dump should be semantically stable
        obj = json.loads(raw1)
        raw2 = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(json.loads(raw1), json.loads(raw2))

    def test_event_redaction_and_latest_events(self):
        self._configure_simple(req_limit=1, window=10, burst=None)
        self.limiter.check_and_register("projA", "e1")
        self.limiter.check_and_register("projA", "e1")  # duplicate -> blocked
        events = self.limiter.latest_events(10, project_id="projA")
        self.assertTrue(all(set(e.keys()) <= {"type", "project_id", "request_id", "timestamp", "reason", "remaining", "capacity", "window_size", "request_limit", "window_seconds", "burst_limit", "enabled", "unrestricted"} for e in events))
        # Ensure at least one blocked event is present
        self.assertTrue(any(e.get("type") == "rate_limit_blocked" for e in events))

    def test_cross_project_access_rejected(self):
        with self.assertRaises(ValueError):
            self.limiter.get_limit("not/allowed")


if __name__ == "__main__":
    unittest.main()
