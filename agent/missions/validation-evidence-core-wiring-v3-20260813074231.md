# MITIGATE Validation Evidence Core Wiring V3

Mission ID: validation-evidence-core-wiring-v3-20260813074231
Request ID: validation-evidence-core-wiring-v3-20260813074231
Task Type: backend

CORE_MAINTENANCE_APPROVED

## Objective

Implement the minimum safe Core wiring required so bounded autonomous
Self-Healing receives useful sanitized validation evidence from failed
Python compilation and unittest subprocesses.

The current runtime already contains:

- bounded Self-Healing
- MissionRepairAdapter
- IntegrationCoordinator
- retry authority
- validation failure categories
- diagnostic sanitization infrastructure
- Core protection
- deliverable allowlists

Do not redesign these systems.

## Confirmed Root Cause

agent/ai/mission_runner.py currently executes validation subprocesses with
check=True but without capturing stdout/stderr.

CalledProcessError therefore does not provide useful captured validation
evidence to the repair lifecycle.

The initial validation failure is reduced to a generic safe_summary.

The validation callback subsequently raises the subprocess exception and the
IntegrationCoordinator converts str(exc) into a generic validation-exception.

As a result, repair generation does not receive the concrete sanitized
compiler or unittest failure required to make an informed correction.

## Authorized Core Scope

The only protected Core production file authorized for modification is:

- agent/ai/mission_runner.py

Do not modify any other protected Core production path.

## Deliverables

- agent/ai/mission_runner.py
- agent/tests/test_mission_runner_self_healing.py
- docs/architecture/validation-evidence-core-wiring-v3.json


## Required Implementation

Make the smallest possible patch.

### Validation subprocess evidence

Update validation subprocess execution so failed validation can expose:

- return code
- stdout
- stderr

Use captured text output.

Do not expose environment variables, credentials, tokens, secrets, or
unrelated process state.

### Sanitization

Validation diagnostic evidence passed into the repair lifecycle must be
bounded and sanitized.

Reuse existing repository sanitization infrastructure where practical.

Do not create an unrestricted logging or evidence channel.

### Structured validation result

The Self-Healing validation callback must provide the existing repair
integration layer with useful structured validation information rather than
only allowing CalledProcessError to collapse into a generic exception.

Preserve the existing IntegrationCoordinator retry authority.

Preserve:

- bounded retry count
- blocked conditions
- allowlists
- denied paths
- Core protection
- repair audit behavior

### Repair context

Repair generation must receive enough sanitized evidence to identify the
actual compilation or unittest failure.

Do not send raw unrestricted subprocess output to the model.

### Initial failure

Preserve the category distinction between:

- python compilation failure
- unittest failure
- generic generated validation failure

Where compatible with existing contracts, include sanitized diagnostic
evidence and return code from the initial validation failure.

## Regression Protection

Do not rewrite agent/ai/mission_runner.py.

Do not remove or replace unrelated functions.

Do not change:

- mission queue semantics
- branch creation
- Git commit/push behavior
- repository recovery behavior
- provider selection
- systemd configuration
- retry budgets
- IntegrationCoordinator authority
- MissionRepairAdapter authority
- Core protection policy

## Tests

Create focused unittest coverage in:

agent/tests/test_mission_runner_self_healing.py

Tests must verify at minimum:

1. failed validation captures useful subprocess evidence;
2. diagnostic evidence is sanitized/bounded before repair use;
3. return code is preserved where supported;
4. compilation failure remains correctly classified;
5. unittest failure remains correctly classified;
6. validation callback provides structured useful failure evidence;
7. successful validation still returns normally;
8. retry authority remains with the existing repair integration layer;
9. unrelated mission_runner behavior is preserved.

Use Python standard-library unittest only.

Do not use pytest.

## Architecture Report

Create:

docs/architecture/validation-evidence-core-wiring-v3.json

The report must state:

- root cause
- exact files changed
- validation evidence flow before the fix
- validation evidence flow after the fix
- sanitization boundary
- retry authority preserved
- Core protection preserved
- tests executed
- test results

Do not claim success unless validation actually succeeds.

## Acceptance Criteria

Mission succeeds only if:

- exact deliverable allowlist is respected;
- mission_runner receives only a minimal targeted patch;
- validation subprocess evidence is captured;
- diagnostic evidence is sanitized and bounded;
- repair lifecycle receives actionable validation evidence;
- retry authority is unchanged;
- Core protection is unchanged;
- targeted tests pass;
- repository unittest validation passes.

No automatic merge to main.

Push the successful Agent branch for final human review.
