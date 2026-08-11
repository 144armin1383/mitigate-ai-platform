# MITIGATE Technology Watcher

## Purpose

The Technology Watcher is a MITIGATE-owned intelligence subsystem.

It observes technology intelligence from injected Technology Sources,
records changes in the MITIGATE Technology Registry, and identifies
evaluation candidates.

It does not execute missions, install packages, deploy software,
or create external runtime dependencies.

## Architecture

```text
External Technology World
        |
        v
Technology Sources
        |
        v
MITIGATE Technology Watcher
        |
        +--> Change Detection
        |
        +--> Deterministic Scoring
        |
        v
MITIGATE Technology Registry
        |
        v
Evaluation Candidate
        |
        v
Future normal MITIGATE mission pipeline
Core principles

Discovery is not adoption.

Evaluation is not adoption.

Adoption is not dependency.

Assimilation means MITIGATE owns the resulting capability.

External technologies may provide intelligence or acceleration, but
MITIGATE must remain operational without them.

Phase 1 limitations

Phase 1 intentionally performs:

no live network acquisition
no GitHub API access
no package registry access
no subprocess execution
no mission enqueue
no deployment
no automatic certification
no automatic assimilation

All observations are supplied through injected TechnologySource
implementations.

Future phases may add controlled source adapters behind the same
TechnologySource contract.
