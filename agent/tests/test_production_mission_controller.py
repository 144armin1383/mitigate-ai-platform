import unittest
from pathlib import Path

from agent.runtime.production_mission_controller import (
    ProductionMissionController,
    find_project_root,
    resolve_architecture_path,
)


class TestProductionMissionController(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = ProductionMissionController()

    def test_package_dir_is_agent(self) -> None:
        pkg_dir = self.controller.package_path()
        self.assertTrue(pkg_dir.is_dir(), f"Package path is not a directory: {pkg_dir}")
        # This controller lives under the 'agent' package; ensure resolution reflects that.
        self.assertEqual(pkg_dir.name, "agent")

    def test_project_root_contains_docs_and_agent(self) -> None:
        root = self.controller.project_root()
        self.assertTrue((root / "docs").is_dir(), f"Missing docs directory at: {root / 'docs'}")
        self.assertTrue((root / "agent").is_dir(), f"Missing agent package at: {root / 'agent'}")

    def test_can_resolve_and_load_architecture_json(self) -> None:
        name = "controller-package-path-fix"
        path_from_controller = self.controller.architecture_json_path(name)
        expected_path = resolve_architecture_path(name, self.controller.project_root())
        self.assertEqual(path_from_controller.resolve(), expected_path.resolve())
        self.assertTrue(path_from_controller.is_file(), f"Expected architecture JSON missing at: {path_from_controller}")

        data = self.controller.load_architecture_json(name)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("id"), name)
        self.assertEqual(data.get("component"), "production_mission_controller")

    def test_find_project_root_function_matches_controller(self) -> None:
        # Verify the helper function returns the same root as the controller method
        root_func = find_project_root(self.controller.package_path())
        root_ctrl = self.controller.project_root()
        self.assertEqual(root_func.resolve(), root_ctrl.resolve())


if __name__ == "__main__":
    unittest.main()
