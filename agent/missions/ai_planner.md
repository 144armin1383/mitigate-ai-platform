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
