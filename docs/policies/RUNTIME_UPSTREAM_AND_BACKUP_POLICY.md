# MITIGATE Runtime Upstream and GitHub Backup Policy

## Authority

MITIGATE AI remains the control plane and canonical authority. OpenHands, OpenClaw, Ruflo, and future external runtimes are replaceable capability providers only.

## Upstream updates

- Production never follows an upstream `latest` channel automatically.
- Tested versions remain pinned in `agent/config/external-runtimes.json`.
- A scheduled GitHub workflow checks stable package registries daily.
- A newer upstream version creates or refreshes a GitHub issue for review.
- Promotion requires disposable compatibility testing, MITIGATE contract tests, a rollback point, and the normal approval path.
- Beta, alpha, dev, and moving-main channels are not production upgrade sources.
- Upstream source should not be forked or patched unless an adapter cannot provide the required isolation.

## GitHub continuity

- GitHub remains the portable source of truth for MITIGATE code, runtime adapters, bootstrap assets, policies, tests, architecture records, and machine-readable configuration.
- Every successful `main` update runs the main integrity workflow.
- After integrity checks pass, `backup/rolling-main` is updated to the verified main commit.
- Each verified main run also creates an immutable backup tag.
- Manual pre-change backup branches remain appropriate before major runtime or Core transitions.

## Failure policy

A failed integrity test must prevent the backup pointer from advancing. A failed upstream compatibility test must never modify production pins or external runtime installations automatically.

## Portability

External runtime installations are intentionally outside the MITIGATE production virtual environment. A fresh server should be recoverable from GitHub plus configuration/secrets by running the repository bootstrap procedures and reinstalling tested external runtime pins.
