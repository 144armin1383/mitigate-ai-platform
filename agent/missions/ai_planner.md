# AI Planner

## Objective

Build an AI Planner that converts a high-level development request into an ordered execution plan composed of multiple autonomous missions.

The planner becomes the entry point before Mission Queue.

---

## Requirements

- Accept a high-level feature request.
- Break the request into independent missions.
- Detect mission dependencies.
- Order missions correctly.
- Assign priorities.
- Produce deterministic JSON output.
- Never generate duplicate missions.
- Never execute missions.
- Only create execution plans.

---

## Deliverables

agent/ai/ai_planner.py

agent/tests/test_ai_planner.py

---

## Acceptance Criteria

- Plans are deterministic.
- Mission ordering is stable.
- Dependencies are preserved.
- Duplicate missions are removed.
- JSON output is deterministic.
- Existing tests continue to pass.
- New planner tests pass.

Mandatory Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never use pytest fixtures, decorators, raises, monkeypatch, parametrize, or tmp_path.
- Never add pytest or any new test dependency.
- Never modify requirements.txt.
- Generated tests must be compatible with unittest discovery.
- The literal statement import pytest must never appear in generated files.
- Every generated Python file must pass py_compile.
- All existing and newly generated unittest tests must pass.

Mission Classification and Dependency Requirements

- The planner must detect backend, frontend, database, API, testing, security, deployment, and documentation work when these areas are implied by the request.
- A request describing a user-facing feature, dashboard, form, page, interface, admin panel, or visual workflow must include a frontend mission.
- A request requiring data persistence must include a database mission.
- A request requiring server-side behavior must include a backend or API mission.
- Frontend missions must depend on the relevant API or backend mission when frontend work consumes backend functionality.
- API or backend missions must depend on the relevant database mission when persistence is required.
- Testing missions must depend on all implementation missions they validate.
- Deployment missions must depend on validation and testing missions.
- Dependencies must reference valid mission identifiers that exist in the generated plan.
- Every dependency must point to an earlier mission in the ordered execution plan.
- The planner must never omit an expected frontend mission from a full-stack or user-interface request.
- The test_expected_dependencies_present unittest must pass.
- All existing and newly generated unittest tests must pass.
