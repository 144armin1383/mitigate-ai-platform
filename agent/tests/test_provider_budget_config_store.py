import json
import os
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from agent.providers.provider_budget_config_store import (
    ProviderBudgetConfigStore,
    StorageCorruptionError,
)


class FakeResolver:
    def __init__(self, projects):
        self._projects = set(projects)

    def is_valid(self, project_id):
        return project_id in self._projects


class FakeClock:
    def __init__(self, start: datetime):
        self._current = start

    def __call__(self) -> datetime:
        # Advance by 1 second per call to ensure monotonicity deterministically
        c = self._current
        self._current = c + timedelta(seconds=1)
        return c.replace(tzinfo=timezone.utc)


def read(path):
    with open(path, 'r', encoding='ascii') as f:
        return f.read()


class TestProviderBudgetConfigStore(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.resolver = FakeResolver({"p1", "p2"})
        self.clock = FakeClock(datetime(2025, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc))
        self.store = ProviderBudgetConfigStore(self.base, self.resolver, clock=self.clock, lock_timeout=1.0)

        self.valid_config = {
            "enabled": True,
            "daily_budget": 1.0,
            "monthly_budget": 10.0,
            "per_request_budget": 0.5,
            "daily_token_limit": 1000,
            "monthly_token_limit": 20000,
            "per_request_input_token_limit": 200,
            "per_request_output_token_limit": 300,
            "soft_warning_percent": 80,
            "hard_limit_enabled": True,
            "currency": "USD",
            "unknown_pricing_policy": "warn"
        }

    def _get_paths(self):
        cfg = os.path.join(self.base, ProviderBudgetConfigStore.CONFIG_FILENAME)
        ev = os.path.join(self.base, ProviderBudgetConfigStore.EVENTS_FILENAME)
        return cfg, ev

    # Test configuration creation
    def test_configuration_creation(self):
        out = self.store.configure_budget('p1', dict(self.valid_config))
        self.assertEqual(out['project_id'], 'p1')
        self.assertEqual(out['currency'], 'USD')
        self.assertTrue(out['enabled'])
        self.assertIn('created_at', out)
        self.assertIn('updated_at', out)
        # Ensure persisted
        cfg_path, _ = self._get_paths()
        self.assertTrue(os.path.exists(cfg_path))

    # Test configuration update
    def test_configuration_update(self):
        c1 = self.store.configure_budget('p1', dict(self.valid_config))
        created_at = c1['created_at']
        upd = self.store.update_budget('p1', {"daily_budget": 2.0, "soft_warning_percent": 50})
        self.assertEqual(upd['daily_budget'], 2.0)
        self.assertEqual(upd['soft_warning_percent'], 50)
        self.assertEqual(upd['created_at'], created_at)
        self.assertNotEqual(upd['updated_at'], created_at)

    # Test configuration removal
    def test_configuration_removal(self):
        self.store.configure_budget('p1', dict(self.valid_config))
        removed = self.store.remove_budget('p1')
        self.assertTrue(removed)
        with self.assertRaises(KeyError):
            self.store.get_budget('p1')

    # Test duplicate configuration behavior
    def test_duplicate_configuration_rejected(self):
        self.store.configure_budget('p1', dict(self.valid_config))
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', dict(self.valid_config))

    # Test unknown project rejection
    def test_unknown_project_rejection(self):
        with self.assertRaises(PermissionError):
            self.store.configure_budget('unknown', dict(self.valid_config))

    # Test negative monetary value rejection
    def test_negative_monetary_rejection(self):
        bad = dict(self.valid_config)
        bad['daily_budget'] = -1.0
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', bad)

    # Test negative token limit rejection
    def test_negative_token_limit_rejection(self):
        bad = dict(self.valid_config)
        bad['daily_token_limit'] = -5
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', bad)

    # Test invalid soft-warning percentage
    def test_invalid_soft_warning_percent(self):
        bad = dict(self.valid_config)
        bad['soft_warning_percent'] = 120
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', bad)

    # Test invalid currency
    def test_invalid_currency(self):
        bad = dict(self.valid_config)
        bad['currency'] = 'usd'
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', bad)

    # Test invalid unknown-pricing policy
    def test_invalid_unknown_pricing_policy(self):
        bad = dict(self.valid_config)
        bad['unknown_pricing_policy'] = 'maybe'
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', bad)

    # Test unknown-field rejection
    def test_unknown_field_rejection(self):
        bad = dict(self.valid_config)
        bad['extra_field'] = 1
        with self.assertRaises(ValueError):
            self.store.configure_budget('p1', bad)

    # Test project isolation
    def test_project_isolation(self):
        c1 = dict(self.valid_config)
        c2 = dict(self.valid_config)
        c2['currency'] = 'EUR'
        self.store.configure_budget('p1', c1)
        self.store.configure_budget('p2', c2)
        self.store.update_budget('p1', {'daily_budget': 3.0})
        b1 = self.store.get_budget('p1')
        b2 = self.store.get_budget('p2')
        self.assertEqual(b1['daily_budget'], 3.0)
        self.assertEqual(b2['daily_budget'], 1.0)
        self.assertEqual(b2['currency'], 'EUR')

    # Test deterministic listing
    def test_deterministic_listing(self):
        c1 = dict(self.valid_config)
        c2 = dict(self.valid_config)
        self.store.configure_budget('p2', c2)
        self.store.configure_budget('p1', c1)
        lst = self.store.list_budgets()
        self.assertEqual([x['project_id'] for x in lst], ['p1', 'p2'])

    # Test atomic persistence (no leftover temp files after normal ops)
    def test_atomic_persistence_and_no_temp_leftovers(self):
        self.store.configure_budget('p1', dict(self.valid_config))
        names = set(os.listdir(self.base))
        for n in names:
            self.assertFalse(n.endswith('.tmp'), msg=f"Leftover temp file found: {n}")

    # Test restart recovery
    def test_restart_recovery(self):
        self.store.configure_budget('p1', dict(self.valid_config))
        # Recreate store with same base
        store2 = ProviderBudgetConfigStore(self.base, self.resolver, clock=self.clock, lock_timeout=1.0)
        got = store2.get_budget('p1')
        self.assertEqual(got['project_id'], 'p1')

    # Test corrupted storage rejection
    def test_corrupted_storage_rejection(self):
        cfg_path, _ = self._get_paths()
        with open(cfg_path, 'w', encoding='ascii') as f:
            f.write('not json')
        with self.assertRaises(StorageCorruptionError):
            ProviderBudgetConfigStore(self.base, self.resolver, clock=self.clock, lock_timeout=1.0)

    # Test temporary filenames acceptance (leftover temp files should be ignored)
    def test_temporary_filenames_acceptance(self):
        # Create valid config first
        self.store.configure_budget('p1', dict(self.valid_config))
        # Create leftover temp files that should be ignored on load
        cfg_temp = os.path.join(self.base, f".{ProviderBudgetConfigStore.CONFIG_FILENAME}.tmp-123")
        ev_temp = os.path.join(self.base, f".{ProviderBudgetConfigStore.EVENTS_FILENAME}.tmp-456")
        for p in (cfg_temp, ev_temp):
            with open(p, 'w', encoding='ascii') as f:
                f.write('garbage')
        store2 = ProviderBudgetConfigStore(self.base, self.resolver, clock=self.clock, lock_timeout=1.0)
        got = store2.get_budget('p1')
        self.assertEqual(got['project_id'], 'p1')

    # Test deterministic serialization
    def test_deterministic_serialization(self):
        self.store.configure_budget('p1', dict(self.valid_config))
        cfg_path, _ = self._get_paths()
        raw1 = read(cfg_path)
        # The content should equal json.dumps(parsed, deterministic params)
        parsed = json.loads(raw1)
        canon = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.assertEqual(raw1, canon)
        # Re-open store; content must be identical
        store2 = ProviderBudgetConfigStore(self.base, self.resolver, clock=self.clock, lock_timeout=1.0)
        raw2 = read(cfg_path)
        self.assertEqual(raw1, raw2)

    # Test event redaction
    def test_event_redaction(self):
        self.store.configure_budget('p1', dict(self.valid_config))
        self.store.update_budget('p1', {"daily_budget": 2.0, "soft_warning_percent": 50})
        # Inspect events file for presence of only field names
        _, ev_path = self._get_paths()
        with open(ev_path, 'r', encoding='ascii') as f:
            events = json.load(f)
        self.assertGreaterEqual(len(events), 2)
        for e in events:
            self.assertIn(e['type'], ('budget_configured', 'budget_updated', 'budget_removed'))
            self.assertIsInstance(e['details'], dict)
            for k, v in e['details'].items():
                if k.endswith('_fields'):
                    self.assertIsInstance(v, list)
                    for name in v:
                        self.assertIsInstance(name, str)
                else:
                    # No values should be embedded
                    self.assertNotIsInstance(v, (dict, list))

    # Test unrelated files remain unchanged
    def test_unrelated_files_remain_unchanged(self):
        other_path = os.path.join(self.base, 'unrelated.txt')
        with open(other_path, 'w', encoding='utf-8') as f:
            f.write('keep')
        self.store.configure_budget('p1', dict(self.valid_config))
        self.store.update_budget('p1', {"daily_budget": 2.0})
        self.store.get_budget('p1')
        self.store.list_budgets()
        with open(other_path, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'keep')


if __name__ == '__main__':
    unittest.main()
