# Autonomous Controller

## Objective

Build the top-level controller that coordinates the complete autonomous development lifecycle.

The controller must execute missions using the following pipeline:

Mission
↓
Planning
↓
Repository Scan
↓
Code Generation
↓
Patch Generation
↓
Patch Application
↓
Validation
↓
Retry (if retryable)
↓
Git Review
↓
Commit
↓
Push

The controller becomes the single entry point for autonomous development.

---

## Requirements

- Coordinate every existing engine.
- No duplicated logic.
- Retry Engine decides whether another attempt is allowed.
- Validation Engine decides whether generated code is acceptable.
- Git Review decides final safety.
- Patch Engine applies only validated patches.
- Every stage writes structured logs.
- Every stage produces deterministic JSON reports.
- Abort immediately on security violations.
- Never merge to main.
- Never bypass Validation Engine.
- Never bypass Git Review.
- Never bypass Retry Engine.

---

## Deliverables

agent/ai/autonomous_controller.py

agent/tests/test_autonomous_controller.py

---

## Acceptance Criteria

- Successful missions complete automatically.
- Retryable failures are retried automatically.
- Non-retryable failures abort immediately.
- Validation failures prevent commits.
- Git Review failures prevent commits.
- Retry state survives internal exceptions.
- Existing missions continue working.
- All unittest tests pass.
