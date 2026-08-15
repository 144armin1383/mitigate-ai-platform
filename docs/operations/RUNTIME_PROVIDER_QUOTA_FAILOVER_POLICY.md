# Runtime Provider Quota Failover Policy

MITIGATE treats an LLM provider quota exhaustion as a provider-specific availability failure, not as a governance, approval, permission, credential, or scope failure.

## Required behavior

When an execution adapter returns a provider-specific quota exhaustion result (for example `openhands_llm_quota_exhausted` or `insufficient_quota`), the Runtime Router MAY continue to the next healthy runtime candidate in a fresh disposable workspace.

Failover MUST NOT bypass:

- missing/invalid credentials;
- permission failures;
- protected-path or authorized-scope violations;
- canonical repository cleanliness requirements;
- manual approval requirements;
- policy blocks.

Each provider attempt must remain recorded in execution evidence. The next provider must receive a newly allocated disposable workspace. Git publication and approval governance remain owned by MITIGATE Core.

## Rationale

Quota exhaustion is temporary capacity/billing state of one provider. Treating it as terminal makes a multi-runtime system unnecessarily unavailable even when another configured runtime is healthy. This policy preserves governance while allowing provider substitution.
