# Ruflo Version and Upgrade Policy

## Goal

Use current Ruflo capabilities without allowing Ruflo's release velocity or breaking changes to destabilize MITIGATE AI production.

## Production rule: never follow moving targets

Production must never depend directly on:

- `main`/`master`;
- an unpinned Git reference;
- `latest`;
- a floating semver range that can silently install a new incompatible release.

Production uses an exact, reviewed version or immutable commit/digest recorded in MITIGATE configuration/lockfiles.

## Current-version discovery

Before initial adoption and before every upgrade, automation must query authoritative upstream release/package metadata and identify the newest stable candidate. A version written in this document is informational only and must never be treated as permanently current.

At the time this policy was introduced (2026-08-11), upstream Ruflo was releasing frequently. Therefore MITIGATE must assume the integration surface can evolve quickly.

## Candidate → certified → production

Ruflo versions move through three states:

1. **Candidate** — newest suitable upstream stable version discovered for evaluation.
2. **Certified** — passes MITIGATE compatibility, security, migration, performance, and fallback tests.
3. **Production** — explicitly promoted after certification; production remains pinned to this exact version until the next promotion.

The newest release is not automatically the production release.

## Compatibility suite

Before promotion, CI must validate at least:

- adapter startup and version detection;
- capability negotiation;
- swarm/agent lifecycle used by MITIGATE;
- task submission/status/result contracts;
- error/timeout/cancellation behavior;
- correlation IDs and observability;
- enabled memory/RAG operations;
- native fallback behavior;
- no mutation of MITIGATE canonical state outside defined interfaces;
- representative end-to-end project mission;
- restart/recovery behavior;
- security boundaries and permission scoping.

## Upgrade workflow

1. Detect a newer stable upstream release.
2. Record release notes and relevant breaking/security changes.
3. Create an isolated upgrade branch.
4. Update only the Ruflo candidate pin and adapter changes required for compatibility.
5. Run Ruflo adapter unit/contract tests.
6. Run the full MITIGATE test suite.
7. Run production-like end-to-end smoke tests without production write authority.
8. Verify fallback with Ruflo disabled/unavailable.
9. Review diff and risk classification.
10. Promote the exact certified version.
11. Roll out in a controlled manner.
12. Verify production health and retain immediate rollback to the previous certified version.

## Update cadence

MITIGATE may automatically check upstream for new Ruflo releases, but it must not automatically install them in production.

Security-critical releases should be evaluated immediately. Normal releases should be batched and evaluated on a controlled cadence to avoid continuous production churn.

## Deprecation handling

The adapter should maintain a small compatibility matrix for the currently certified release and, when practical, the immediately previous certified release. Deprecated integration calls must be removed deliberately after migration rather than accumulating indefinitely.

## Fork handling

If MITIGATE temporarily uses a Ruflo fork, the production pin must reference an immutable fork commit. Upstream updates are merged/rebased only on an isolated upgrade branch and must pass the same certification process.

Do not diverge into an independent Ruflo product unless there is a strong architectural reason. Prefer contributing fixes upstream and keeping MITIGATE-specific behavior in the MITIGATE adapter/core.

## Rollback

Every Ruflo production upgrade must record the previous certified pin. Rollback must not require reverting MITIGATE durable memory or project state. Schema/data migrations introduced for optional Ruflo features must therefore be backward-safe or independently reversible.

## Future self-update automation

MITIGATE's self-maintenance agent may:

- detect upstream Ruflo releases;
- summarize release notes;
- open an upgrade mission/branch;
- run compatibility and full tests;
- prepare a risk report;
- recommend promotion.

It may not silently promote a new Ruflo version to production until the platform's configured upgrade policy authorizes that risk class.
