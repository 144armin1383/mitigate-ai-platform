import json
import unittest

from agent.ai.ai_planner import AIPlanner


class TestAIPlannerDeterminism(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = AIPlanner()
        self.request = (
            "Build a user dashboard page that allows users to view and update their "
            "profile, including saving changes to the database, and expose an API "
            "for the mobile app. Add authentication. Prepare deployment pipeline "
            "and document the feature."
        )

    def test_plan_is_deterministic(self):
        plan1 = self.planner.plan(self.request)
        plan2 = self.planner.plan(self.request)
        self.assertEqual(plan1, plan2)

        json1 = self.planner.to_json(plan1)
        json2 = self.planner.to_json(plan2)
        self.assertEqual(json1, json2)

    def test_mission_ordering_is_stable(self):
        plan = self.planner.plan(self.request)
        # IDs must be strictly increasing by position and unique
        ids = [m["id"] for m in plan["missions"]]
        self.assertEqual(len(ids), len(set(ids)))
        for i, mid in enumerate(ids, start=1):
            self.assertEqual(mid, f"M{i}")

    def test_dependencies_reference_earlier_missions(self):
        plan = self.planner.plan(self.request)
        id_to_index = {m["id"]: i for i, m in enumerate(plan["missions"]) }
        for i, mission in enumerate(plan["missions"]):
            for dep in mission.get("depends_on", []):
                self.assertIn(dep, id_to_index)
                self.assertLess(id_to_index[dep], i)

    def test_no_duplicate_categories(self):
        plan = self.planner.plan(self.request)
        categories = [m["category"] for m in plan["missions"]]
        self.assertEqual(len(categories), len(set(categories)))


class TestAIPlannerExpectedDependencies(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = AIPlanner()
        self.request = (
            "Build a user dashboard page that allows users to view and update their "
            "profile, including saving changes to the database, and expose an API "
            "for the mobile app. Add authentication. Prepare deployment pipeline "
            "and document the feature."
        )

    def _map_by_category(self, plan):
        by_cat = {}
        for m in plan["missions"]:
            by_cat[m["category"]] = m
        return by_cat

    def test_expected_dependencies_present(self):
        plan = self.planner.plan(self.request)
        by_cat = self._map_by_category(plan)

        # Ensure required categories exist for a full-stack request
        self.assertIn("database", by_cat)
        self.assertIn("api", by_cat)
        self.assertIn("frontend", by_cat)
        self.assertIn("security", by_cat)
        self.assertIn("testing", by_cat)
        self.assertIn("deployment", by_cat)
        self.assertIn("documentation", by_cat)

        # Build a helper mapping id -> category and category -> id
        cat_to_id = {m["category"]: m["id"] for m in plan["missions"]}

        # Frontend must depend on API (consumes backend functionality)
        self.assertIn(cat_to_id["api"], by_cat["frontend"]["depends_on"])  # type: ignore[index]

        # API must depend on Database when persistence is required
        self.assertIn(cat_to_id["database"], by_cat["api"]["depends_on"])  # type: ignore[index]

        # Security depends on API and Database when present
        self.assertIn(cat_to_id["api"], by_cat["security"]["depends_on"])  # type: ignore[index]
        self.assertIn(cat_to_id["database"], by_cat["security"]["depends_on"])  # type: ignore[index]

        # Testing depends on all implementation missions it validates
        for impl in ("database", "api", "frontend", "security"):
            self.assertIn(cat_to_id[impl], by_cat["testing"]["depends_on"])  # type: ignore[index]

        # Deployment depends on testing
        self.assertIn(cat_to_id["testing"], by_cat["deployment"]["depends_on"])  # type: ignore[index]

        # Documentation depends on testing
        self.assertIn(cat_to_id["testing"], by_cat["documentation"]["depends_on"])  # type: ignore[index]

    def test_json_output_is_deterministic(self):
        # The JSON output must be deterministic for the same input
        plan = self.planner.plan(self.request)
        s1 = self.planner.to_json(plan)
        s2 = self.planner.to_json(self.planner.plan(self.request))
        self.assertEqual(s1, s2)


class TestAIPlannerBackendFallback(unittest.TestCase):
    def test_frontend_depends_on_backend_when_no_api(self):
        planner = AIPlanner()
        req = (
            "Create a settings page UI that submits data to the backend service. "
            "Ensure data is persisted in the database."
        )
        plan = planner.plan(req)
        by_cat = {m["category"]: m for m in plan["missions"]}

        self.assertIn("backend", by_cat)
        self.assertIn("frontend", by_cat)
        self.assertIn("database", by_cat)

        # Frontend depends on backend (not API in this case)
        backend_id = by_cat["backend"]["id"]
        self.assertIn(backend_id, by_cat["frontend"]["depends_on"])  # type: ignore[index]

        # Backend depends on database since persistence is required
        db_id = by_cat["database"]["id"]
        self.assertIn(db_id, by_cat["backend"]["depends_on"])  # type: ignore[index]

        # Testing should depend on implementation missions
        testing_deps = set(by_cat["testing"]["depends_on"])  # type: ignore[index]
        self.assertTrue({backend_id, db_id}.issubset(testing_deps))


if __name__ == "__main__":
    unittest.main()
