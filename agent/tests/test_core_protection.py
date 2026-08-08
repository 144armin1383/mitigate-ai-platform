import os
import tempfile
import json
import unittest
from pathlib import Path

from agent.policies import core_protection as cp

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCoreProtectionPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = cp.load_core_lock_manifest()
        cls.core_marker = cls.config.core_maintenance_marker
        cls.test_marker = cls.config.test_contract_maintenance_marker

    def test_01_normal_mission_cannot_modify_agent_ai(self):
        d = cp.validate_mission_write("agent/ai/mission_runner.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")
        self.assertEqual(d.kind, cp.ProtectionKind.PROTECTED_CORE)

    def test_02_normal_mission_cannot_modify_agent_runtime(self):
        d = cp.validate_mission_write("agent/runtime/core.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")
        self.assertEqual(d.kind, cp.ProtectionKind.PROTECTED_CORE)

    def test_03_normal_mission_cannot_modify_agent_autonomy(self):
        d = cp.validate_mission_write("agent/autonomy/plan.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")

    def test_04_normal_mission_cannot_modify_agent_memory(self):
        d = cp.validate_mission_write("agent/memory/example.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")

    def test_05_normal_mission_cannot_modify_agent_bootstrap(self):
        d = cp.validate_mission_write("agent/bootstrap/env.example", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")

    def test_06_normal_mission_cannot_modify_agent_policies(self):
        d = cp.validate_mission_write("agent/policies/new_policy.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")

    def test_07_normal_mission_cannot_modify_canonical_recovery_test(self):
        d = cp.validate_mission_write("agent/tests/test_portable_agent_recovery.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CANONICAL_TEST_LOCKED")
        self.assertEqual(d.kind, cp.ProtectionKind.CANONICAL_TEST)

    def test_08_non_core_path_remains_allowed(self):
        d = cp.validate_mission_write("project/site/feature_module.py", "", self.config)
        self.assertTrue(d.allowed)
        self.assertEqual(d.kind, cp.ProtectionKind.UNPROTECTED)

    def test_09_core_marker_permits_protected_core_path(self):
        mission = f"Feature update.\n{self.core_marker}\n"
        d = cp.validate_mission_write("agent/ai/engine.py", mission, self.config)
        self.assertTrue(d.allowed)
        self.assertEqual(d.kind, cp.ProtectionKind.PROTECTED_CORE)
        self.assertTrue(d.manual_merge_required)
        self.assertTrue(d.full_suite_required)
        self.assertTrue(d.recovery_gate_required)

    def test_10_core_marker_alone_does_not_permit_canonical_test(self):
        mission = f"Refactor tests. {self.core_marker}"
        d = cp.validate_mission_write("agent/tests/test_portable_agent_recovery.py", mission, self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CANONICAL_TEST_LOCKED")

    def test_11_test_contract_marker_alone_does_not_permit_canonical_test(self):
        mission = f"Refactor tests. {self.test_marker}"
        d = cp.validate_mission_write("agent/tests/test_portable_agent_recovery.py", mission, self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CANONICAL_TEST_LOCKED")

    def test_12_both_markers_permit_canonical_test_modification(self):
        mission = f"Hotfix.\n{self.core_marker}\n{self.test_marker}\n"
        d = cp.validate_mission_write("agent/tests/test_portable_agent_recovery.py", mission, self.config)
        self.assertTrue(d.allowed)
        self.assertEqual(d.kind, cp.ProtectionKind.CANONICAL_TEST)
        self.assertTrue(d.manual_merge_required)
        self.assertTrue(d.full_suite_required)
        self.assertTrue(d.recovery_gate_required)

    def test_13_traversal_cannot_bypass_protection(self):
        d = cp.validate_mission_write("site/../agent/ai/mission_runner.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")

    def test_14_dot_slash_normalization_cannot_bypass(self):
        d = cp.validate_mission_write("./agent/ai/mission_runner.py", "", self.config)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, "CORE_PATH_LOCKED")

    def test_15_unknown_manifest_fields_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            data = {
                "schema_version": "1.0",
                "protected_core_paths": ["agent/ai/"],
                "canonical_test_paths": ["agent/tests/test_portable_agent_recovery.py"],
                "core_maintenance_marker": "CORE_MAINTENANCE_APPROVED",
                "test_contract_maintenance_marker": "TEST_CONTRACT_MAINTENANCE_APPROVED",
                "manual_merge_required_for_core_changes": True,
                "full_suite_required_for_core_changes": True,
                "recovery_gate_required_for_core_changes": True,
                "unknown_field": 123
            }
            p.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(cp.ManifestValidationError):
                cp.load_core_lock_manifest(p)

    def test_16_malformed_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            data = {
                # missing schema_version
                "protected_core_paths": "not-a-list",  # wrong type
                "canonical_test_paths": [123],          # wrong type inside
                "core_maintenance_marker": 1,           # wrong type
                "test_contract_maintenance_marker": "TEST_CONTRACT_MAINTENANCE_APPROVED",
                "manual_merge_required_for_core_changes": True,
                "full_suite_required_for_core_changes": True,
                "recovery_gate_required_for_core_changes": True
            }
            p.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(cp.ManifestValidationError):
                cp.load_core_lock_manifest(p)

    def test_17_deterministic_classification(self):
        path1 = "agent/ai/mission_runner.py"
        path2 = "agent/ai/./mission_runner.py"
        path3 = "agent\\ai\\mission_runner.py"  # mixed separators
        k1 = cp.classify_protected_path(path1, self.config)
        k2 = cp.classify_protected_path(path2, self.config)
        k3 = cp.classify_protected_path(path3, self.config)
        self.assertEqual(k1, cp.ProtectionKind.PROTECTED_CORE)
        self.assertEqual(k2, k1)
        self.assertEqual(k3, k1)

    def test_18_inputs_not_mutated(self):
        mission = "some mission text without markers"
        path = "agent/ai/file.py"
        orig_mission = mission[:]
        orig_path = path[:]
        cfg = self.config
        pre_core_paths = cfg.protected_core_paths
        d = cp.validate_mission_write(path, mission, cfg)
        self.assertFalse(d.allowed)
        self.assertEqual(mission, orig_mission)
        self.assertEqual(path, orig_path)
        self.assertIs(cfg, self.config)
        self.assertIs(pre_core_paths, self.config.protected_core_paths)

    def test_19_no_env_var_bypass(self):
        os.environ[self.core_marker] = "1"
        try:
            d = cp.validate_mission_write("agent/ai/file.py", "no markers here", self.config)
            self.assertFalse(d.allowed)
            self.assertEqual(d.code, "CORE_PATH_LOCKED")
        finally:
            os.environ.pop(self.core_marker, None)

    def test_20_normal_behavior_outside_protected_paths_unchanged(self):
        d1 = cp.validate_mission_write("README.md", "", self.config)
        d2 = cp.validate_mission_write("docs/guide.md", "", self.config)
        self.assertTrue(d1.allowed)
        self.assertTrue(d2.allowed)
        self.assertEqual(d1.kind, cp.ProtectionKind.UNPROTECTED)
        self.assertEqual(d2.kind, cp.ProtectionKind.UNPROTECTED)


if __name__ == "__main__":
    unittest.main()


class TestCoreProtectionHardening(unittest.TestCase):
    def setUp(self):
        self.config = cp.load_core_lock_manifest(
            REPO_ROOT / "agent/policies/core_lock_manifest.json"
        )

    def test_marker_inside_sentence_does_not_authorize_core_change(self):
        mission = (
            "This mission does not contain "
            "CORE_MAINTENANCE_APPROVED authorization."
        )
        result = cp.validate_mission_write(
            "agent/ai/mission_runner.py",
            mission,
            self.config,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, "CORE_PATH_LOCKED")

    def test_exact_core_marker_line_authorizes_core_change(self):
        mission = (
            "Mission: approved maintenance\n\n"
            "CORE_MAINTENANCE_APPROVED\n\n"
            "Perform approved maintenance."
        )
        result = cp.validate_mission_write(
            "agent/core/example.py",
            mission,
            self.config,
        )
        self.assertTrue(result.allowed)

    def test_marker_with_extra_text_does_not_authorize(self):
        mission = "CORE_MAINTENANCE_APPROVED please proceed"
        result = cp.validate_mission_write(
            "agent/services/example.py",
            mission,
            self.config,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, "CORE_PATH_LOCKED")

    def test_core_directory_is_protected(self):
        result = cp.validate_mission_write(
            "agent/core/example.py",
            "normal mission",
            self.config,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, "CORE_PATH_LOCKED")

    def test_services_directory_is_protected(self):
        result = cp.validate_mission_write(
            "agent/services/example.py",
            "normal mission",
            self.config,
        )
        self.assertFalse(result.allowed)

    def test_providers_directory_is_protected(self):
        result = cp.validate_mission_write(
            "agent/providers/example.py",
            "normal mission",
            self.config,
        )
        self.assertFalse(result.allowed)

    def test_deploy_directory_is_protected(self):
        result = cp.validate_mission_write(
            "agent/deploy/example.sh",
            "normal mission",
            self.config,
        )
        self.assertFalse(result.allowed)

    def test_test_contract_marker_in_prose_does_not_authorize(self):
        mission = (
            "CORE_MAINTENANCE_APPROVED\n"
            "This text mentions TEST_CONTRACT_MAINTENANCE_APPROVED "
            "but is not an approval line."
        )
        result = cp.validate_mission_write(
            "agent/tests/test_portable_agent_recovery.py",
            mission,
            self.config,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, "CANONICAL_TEST_LOCKED")

    def test_both_exact_marker_lines_authorize_canonical_test(self):
        mission = (
            "CORE_MAINTENANCE_APPROVED\n"
            "TEST_CONTRACT_MAINTENANCE_APPROVED\n"
        )
        result = cp.validate_mission_write(
            "agent/tests/test_portable_agent_recovery.py",
            mission,
            self.config,
        )
        self.assertTrue(result.allowed)
