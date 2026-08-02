Mission: Build Production Git Review Engine

Goal

Implement a production-grade Git Review Engine for the MITIGATE AI platform.

Requirements

- Review Git differences between two refs or branches
- Produce a structured review report
- List changed, added, deleted, and renamed files
- Calculate insertions and deletions
- Detect high-risk file categories
- Detect changes to secrets, environment files, permissions, deployment files, database migrations, and dependency manifests
- Summarize the change set
- Report validation and testing recommendations
- Return a deterministic risk level: low, medium, high, or critical
- Return a merge recommendation: approve, manual_review, or reject
- Support repository-relative operation only
- Never modify Git state
- Never commit, merge, reset, clean, checkout, or push
- Python 3.12 compatible
- Fully typed Python
- English only
- Use Python standard library unittest only
- Do not add new dependencies
- Produce detailed logs

Security Rules

- Never read or expose secret values
- Never read .env file contents
- Never execute arbitrary shell commands
- Git subprocess calls must use fixed argument lists
- Validate all Git refs before use
- Reject unsafe or malformed refs
- Treat deletion of security, authentication, payment, deployment, or database files as high or critical risk
- Treat secret-like filenames as critical risk
- Do not automatically merge any branch

Deliverables

agent/git/review_engine.py
agent/tests/test_git_review_engine.py
