Mission: Build Production Validation Engine

Goal

Implement a production-grade Validation Engine for the MITIGATE AI platform.

Requirements

- Validate Python syntax using py_compile
- Validate JSON files
- Validate Markdown files exist and are readable
- Execute unittest discovery
- Collect validation results into a structured report
- Return pass/fail status
- Support validation of selected files and full repository
- Produce detailed logs
- Python 3.12 compatible
- English only

Rules

- Never modify repository files during validation.
- Never install dependencies.
- Never modify requirements.txt.
- Never execute shell commands outside the repository.
- Never merge into main.
- Work on an isolated Git branch.
- Commit and push only if all tests pass.

Deliverables

agent/validators/validation_engine.py
agent/tests/test_validation_engine.py

Additional Acceptance Criteria

- Unittest execution results must correctly report total, passed, failed, and error counts.
- Parse unittest result counts reliably from the unittest result object, not by fragile text matching.
- Successful test runs with one discovered test must report total=1, passed=1, failed=0, errors=0.
- Failed test runs with one discovered failing test must report total=1 and the correct failed or error count.
- Validation reports must remain structured and deterministic.
- All existing and newly generated unittest tests must pass.
