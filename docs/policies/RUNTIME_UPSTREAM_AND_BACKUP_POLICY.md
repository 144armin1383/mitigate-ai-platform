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

## Installed-version evidence

- Production compatibility checks read versions from the isolated runtime installation under `/srv/mitigate/external-runtimes`.
- npm registry queries are not accepted as evidence of the version actually executable by MITIGATE.
- Python versions are resolved with the isolated external runtime interpreter.
- npm versions are resolved from installed package metadata, with the isolated CLI as a fallback.
- Ruflo remains benchmark-only even when its tested pin matches production.

## Security monitoring

- Exact tested external-runtime pins receive a recurring non-destructive GitHub security audit.
- Security findings create/refresh a review issue; they never mutate production automatically.
- `npm audit fix --force`, blind dependency upgrades, and registry-latest promotion are forbidden production maintenance actions.
- Security remediation must preserve MITIGATE adapter boundaries and pass disposable compatibility tests before promotion.

## GitHub continuity

- GitHub remains the portable source of truth for MITIGATE code, runtime adapters, bootstrap assets, policies, tests, architecture records, and machine-readable configuration.
- Every successful `main` update runs the main integrity workflow.
- After integrity checks pass, `backup/rolling-main` is updated to the verified main commit.
- Each verified main run also creates an immutable backup tag.
- Manual pre-change backup branches remain appropriate before major runtime or Core transitions.

## Verified deployment gate

- Production deployment is allowed only when `origin/main` equals `origin/backup/rolling-main`.
- `agent/bootstrap/deploy_verified_main.sh` enforces that GitHub verification gate, runs local contract tests, restarts the consolidated worker, runs the runtime doctor, and rolls back the server checkout if validation fails.
- The deployment helper never pushes from production and never changes GitHub authority.

## Failure policy

A failed integrity test must prevent the backup pointer from advancing. A failed upstream compatibility test must never modify production pins or external runtime installations automatically.

## Portability

External runtime installations are intentionally outside the MITIGATE production virtual environment. A fresh server should be recoverable from GitHub plus configuration/secrets by running the repository bootstrap procedures and reinstalling tested external runtime pins.
