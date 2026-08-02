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

Additional Acceptance Criteria

- Treat secret-like filenames as critical risk regardless of file status.
- Secret-like filenames include .env, .env.*, *.pem, *.key, id_rsa, id_ed25519, credentials.*, secrets.*, and files containing token, secret, password, or credential in the filename.
- Secret detection must inspect the basename and full repository-relative path case-insensitively.
- A changed, added, deleted, or renamed secret-like file must produce risk level critical.
- Secret-like file detection must not read or expose file contents.
- All existing and newly generated unittest tests must pass.

Security Test Constraints

- Do not include the literal text exec( or eval( anywhere in generated source code, tests, comments, fixtures, or string literals.
- Test dangerous command detection using harmless symbolic names rather than executable code fragments.
- Do not call or reference Python exec, eval, os.system, subprocess.Popen, or shell=True.
- All generated files must pass the Mission Runner forbidden-content policy.

Git Ref Validation Acceptance Criteria

- Valid Git refs must allow common branch and tag formats such as main, feature/login, release/1.0, v1.0.0, hotfix-123, and refs/heads/main.
- Dots and forward slashes are valid when used in normal Git ref positions.
- Reject refs containing whitespace, control characters, backslashes, shell metacharacters, @{, .., consecutive slashes, leading slash, trailing slash, trailing dot, or a .lock suffix.
- Reject refs beginning with a hyphen.
- Reject empty refs.
- Ref validation must follow Git naming rules closely without being more restrictive than necessary.
- Tests must include valid branch names, valid semantic-version tags, and malformed unsafe refs.
- All existing and newly generated unittest tests must pass.
