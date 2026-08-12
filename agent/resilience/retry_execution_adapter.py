"""
Retry Execution Projection Adapter (Phase B2.2 V2)

Purpose
- Deterministic, provider-neutral projection layer for retry execution events.
- Consumes read-only classification and RetryBudget/MissionQueue projections.
- Produces JSON-serializable, bounded, structured data for observability/metrics/runtime.

Critical Constraints (non-exhaustive; strictly enforced by design):
- No retry loops, no backoff, no sleep, no thread creation.
- No execution of user functions, no network I/O, no runtime state mutation.
- Do not mutate MissionQueue or mission records; do not own retry state.
- Do not increment attempts_done or decrement budgets.
- Inputs are treated as read-only; outputs are purely derived projections.

Integration Notes
- Classification must come from existing RetryClassifier contract (already validated upstream).
- RetryBudget projection must be read-only from retry_budget_queue_adapter (compatibility preserved).
- MissionQueue remains the sole retry_state_authority.

Security / Data Rules Enforcement
- No arbitrary exception reprs, tracebacks, secrets/tokens, or arbitrary bodies are retained.
- Metadata is sanitized to bounded, JSON-safe structures only.

This module intentionally avoids importing or calling any external systems.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

__all__ = [
    "project_retry_execution_event",
    "RetryExecutionAdapterError",
]


class RetryExecutionAdapterError(ValueError):
    """Raised when required inputs are invalid for projection."""


# ------------------------------
# Public API
# ------------------------------

def project_retry_execution_event(
    *,
    mission_id: str,
    execution_id: str,
    # The attempt index or counter as provided by the caller (read-only).
    # This adapter never changes attempts, it only projects what was given.
    attempt: Optional[int],
    # Classification result produced by the existing RetryClassifier.
    classification_result: Mapping[str, Any],
    # Read-only projection (dict-like) from retry_budget_queue_adapter.
    retry_budget_projection: Optional[Mapping[str, Any]] = None,
    # Optional, read-only mission queue projection (status snapshot only).
    mission_queue_projection: Optional[Mapping[str, Any]] = None,
    # Optional checkpoint correlation fields.
    checkpoint_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    # Optional, provider-neutral metadata with strict sanitization.
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a deterministic, JSON-serializable projection for retry execution events.

    This function never mutates inputs and never performs any side effects.

    Parameters
    - mission_id: Required mission identity string (preserved verbatim).
    - execution_id: Required execution identity string (preserved verbatim).
    - attempt: Optional attempt index; this adapter does not change it.
    - classification_result: Mapping from the upstream RetryClassifier contract.
    - retry_budget_projection: Mapping from retry_budget_queue_adapter (read-only).
    - mission_queue_projection: Mapping representing a read-only MissionQueue state snapshot.
    - checkpoint_id: Optional checkpoint correlation id.
    - idempotency_key: Optional idempotent execution key.
    - metadata: Optional safe metadata to include after sanitization.

    Returns
    - Deterministic dict suitable for metrics/observability/runtime correlation.

    Raises
    - RetryExecutionAdapterError if required fields are missing/invalid.
    """
    _validate_identity(mission_id, execution_id)

    if not isinstance(classification_result, Mapping):
        raise RetryExecutionAdapterError("classification_result must be a mapping")

    normalized_classification = _normalize_classification(classification_result)
    normalized_budget = (
        _normalize_budget(retry_budget_projection) if retry_budget_projection is not None else None
    )
    sanitized_queue = (
        _sanitize_projection(mission_queue_projection, max_depth=2) if mission_queue_projection is not None else None
    )
    sanitized_metadata = _sanitize_metadata(metadata) if metadata is not None else {}

    # Metrics labels are provided to integrate with existing retry_metrics module
    # without invoking it here. Consumers may forward these labels to metrics sinks.
    metrics_labels = _build_metrics_labels(
        mission_id=mission_id,
        execution_id=execution_id,
        classification=normalized_classification,
        budget=normalized_budget,
        authority="MissionQueue",
    )

    # Assemble final projection deterministically (ordered construction).
    projection: Dict[str, Any] = {
        "mission": {
            "id": mission_id,
        },
        "execution": {
            "id": execution_id,
        },
        "retry": {
            "authority": "MissionQueue",
            "classification": normalized_classification,
        },
        "observability": {
            "metrics_compatible": True,
            "metrics_labels": metrics_labels,
        },
        "integration": {
            "retry_classification_integrated": True,
            "retry_budget_projection_integrated": normalized_budget is not None,
            "retry_metrics_compatible": True,
            "retry_state_authority": "MissionQueue",
        },
        "safe_metadata": sanitized_metadata,
    }

    # Conditional fields preserved deterministically if provided.
    if attempt is not None:
        projection["execution"]["attempt"] = int(attempt)
    if checkpoint_id is not None:
        projection["checkpoint"] = {"id": str(checkpoint_id)}
    if idempotency_key is not None:
        projection.setdefault("execution", {})["idempotency_key"] = str(idempotency_key)
    if sanitized_queue is not None:
        projection["retry"]["mission_queue_projection"] = sanitized_queue
    if normalized_budget is not None:
        projection["retry"]["budget"] = normalized_budget

    # Ensure JSON-serializable by construction; all values are primitives/containers.
    return projection


# ------------------------------
# Internal helpers (pure)
# ------------------------------

_DEF_MAX_STR = 256
_DEF_MAX_ITEMS = 20


def _validate_identity(mission_id: Any, execution_id: Any) -> None:
    if not isinstance(mission_id, str) or not mission_id:
        raise RetryExecutionAdapterError("mission_id must be a non-empty string")
    if not isinstance(execution_id, str) or not execution_id:
        raise RetryExecutionAdapterError("execution_id must be a non-empty string")


def _normalize_classification(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Map various upstream classification shapes to a normalized, bounded dict.

    Expected keys (any subset):
    - kind or decision: "retryable" | "non_retryable" | "exhausted" | "cancelled" | "deadline_exceeded"
    - retryable: bool
    - exhausted, cancelled, deadline_exceeded: bool flags
    - reason/category/code: descriptive bounded values
    """
    # Extract lower-cased strings from common keys if present
    kind_raw = _coerce_lower_str(result.get("kind")) or _coerce_lower_str(result.get("decision"))

    # Interpret booleans if kind is not explicitly present
    retryable_flag = _coerce_bool(result.get("retryable"))
    exhausted_flag = _coerce_bool(result.get("exhausted"))
    cancelled_flag = _coerce_bool(result.get("cancelled"))
    deadline_flag = _coerce_bool(result.get("deadline_exceeded"))

    kind: str
    if kind_raw in {
        "retryable",
        "non_retryable",
        "exhausted",
        "cancelled",
        "deadline_exceeded",
    }:
        kind = kind_raw  # type: ignore[assignment]
    else:
        if exhausted_flag:
            kind = "exhausted"
        elif cancelled_flag:
            kind = "cancelled"
        elif deadline_flag:
            kind = "deadline_exceeded"
        elif retryable_flag is True:
            kind = "retryable"
        elif retryable_flag is False:
            kind = "non_retryable"
        else:
            kind = "unknown"

    is_retryable = kind == "retryable"

    reason = _sanitize_short_text(
        result.get("reason")
        or result.get("error_kind")
        or result.get("error_code")
        or result.get("category")
        or result.get("code"),
        max_len=64,
    )

    category = _sanitize_short_text(result.get("category"), max_len=48)

    normalized: Dict[str, Any] = {
        "kind": kind,
        "retryable": bool(is_retryable),
    }
    if reason is not None:
        normalized["reason"] = reason
    if category is not None:
        normalized["category"] = category

    # Include a bounded numeric code, if present
    code_val = result.get("code")
    if isinstance(code_val, (int, float)):
        try:
            normalized["code"] = int(code_val)
        except (ValueError, OverflowError):
            pass
    elif isinstance(code_val, str):
        code_text = _sanitize_short_text(code_val, max_len=32)
        if code_text is not None:
            normalized["code"] = code_text

    return normalized


def _normalize_budget(budget: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize RetryBudget projection compatibly with queue adapter output.

    Recognized inputs (any subset), read-only:
    - eligible | can_retry | has_budget -> bool
    - remaining | remaining_attempts -> int >= 0
    - limit | max_attempts | capacity -> int >= 0
    - exhausted -> bool
    - reason -> str (bounded)
    """
    eligible = _coerce_bool(
        budget.get("eligible",
                    budget.get("can_retry", budget.get("has_budget")))
    )

    remaining_raw = (
        budget.get("remaining") if "remaining" in budget else budget.get("remaining_attempts")
    )
    remaining = _coerce_non_negative_int(remaining_raw)

    limit_raw = (
        budget.get("limit")
        if "limit" in budget
        else budget.get("max_attempts", budget.get("capacity"))
    )
    limit = _coerce_non_negative_int(limit_raw)

    exhausted_flag = _coerce_bool(budget.get("exhausted"))

    # If eligibility is specified, prefer it; otherwise infer from remaining.
    if eligible is None:
        if exhausted_flag is True:
            eligible_val = False
        elif remaining is not None:
            eligible_val = remaining > 0
        else:
            eligible_val = None
    else:
        eligible_val = eligible

    reason = _sanitize_short_text(budget.get("reason"), max_len=64)

    normalized: Dict[str, Any] = {
        "source": "RetryBudgetQueueAdapter",
    }

    if eligible_val is not None:
        normalized["eligible"] = bool(eligible_val)
    if remaining is not None:
        normalized["remaining"] = remaining
    if limit is not None:
        normalized["limit"] = limit

    # Exhausted if explicit or inferred from remaining/eligibility.
    exhausted: Optional[bool]
    if exhausted_flag is True:
        exhausted = True
    elif eligible_val is False:
        exhausted = True if remaining == 0 or remaining is None else False
    elif remaining is not None:
        exhausted = remaining <= 0
    else:
        exhausted = None

    if exhausted is not None:
        normalized["exhausted"] = bool(exhausted)

    if reason is not None:
        normalized["reason"] = reason

    return normalized


def _build_metrics_labels(
    *,
    mission_id: str,
    execution_id: str,
    classification: Mapping[str, Any],
    budget: Optional[Mapping[str, Any]],
    authority: str,
) -> Dict[str, Any]:
    kind = _coerce_lower_str(classification.get("kind")) or "unknown"
    retryable = bool(_coerce_bool(classification.get("retryable")) is True)
    exhausted = bool(_coerce_bool(classification.get("exhausted")) is True)
    if not exhausted and budget is not None:
        exhausted = bool(_coerce_bool(budget.get("exhausted")) is True)

    labels: Dict[str, Any] = {
        "mission_id": mission_id,
        "execution_id": execution_id,
        "classification_kind": kind,
        "retryable": retryable,
        "authority": authority,
        "budget_exhausted": exhausted,
    }
    if budget is not None and "remaining" in budget:
        labels["budget_remaining"] = budget.get("remaining")
    return labels


# ------------------------------
# Sanitization helpers (pure)
# ------------------------------

def _sanitize_projection(value: Any, *, max_depth: int = 2) -> Any:
    """Sanitize arbitrary mapping/sequence into a bounded JSON-safe structure.

    - Limits depth and item counts.
    - Converts tuples/sets to lists, drops unknown objects.
    - Truncates strings.
    - Removes sensitive keys.
    - Does not mutate the original input.
    """
    return _scrub(value, depth=max_depth)


def _sanitize_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    # Shallow copy through sanitizer to avoid mutation.
    sanitized: Dict[str, Any] = {}
    for k, v in metadata.items():
        if not _is_safe_key(k):
            # Skip unsafe/suspicious keys entirely.
            continue
        if _is_sensitive_key(k):
            # Explicitly drop sensitive data by key semantics.
            continue
        cleaned_val = _scrub(v, depth=2)
        if cleaned_val is not None:
            sanitized[str(k)] = cleaned_val
    return sanitized


def _scrub(value: Any, *, depth: int) -> Any:
    if depth < 0:
        return None

    # Primitive safe types
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _truncate_str(value)

    # Avoid exception/traceback or binary-like payloads
    if isinstance(value, BaseException):
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None

    # Mapping: sanitize keys and values, bound size
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        count = 0
        for k, v in value.items():
            if count >= _DEF_MAX_ITEMS:
                break
            key_str = str(k)
            if not _is_safe_key(key_str) or _is_sensitive_key(key_str):
                continue
            sv = _scrub(v, depth=depth - 1)
            if sv is not None:
                out[key_str] = sv
                count += 1
        return out

    # Sequence-like: convert tuple/set to list; limit size.
    if isinstance(value, (list, tuple, set)):
        out_list = []
        for i, item in enumerate(value):
            if i >= _DEF_MAX_ITEMS:
                break
            si = _scrub(item, depth=depth - 1)
            if si is not None:
                out_list.append(si)
        return out_list

    # Unknown objects -> drop
    return None


def _truncate_str(s: str, *, max_len: int = _DEF_MAX_STR) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "\u2026"  # ellipsis to indicate truncation deterministically


def _sanitize_short_text(value: Any, *, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _truncate_str(str(value), max_len=max_len)
    if isinstance(value, str):
        return _truncate_str(value, max_len=max_len)
    return None


def _is_safe_key(key: str) -> bool:
    # Allow alphanum and limited separators to keep provider-neutral keys.
    for ch in key:
        if ch.isalnum() or ch in {"_", "-", "."}:
            continue
        return False
    return len(key) > 0


def _is_sensitive_key(key: str) -> bool:
    kl = key.lower()
    sensitive_tokens = (
        "exception",
        "traceback",
        "token",
        "secret",
        "password",
        "authorization",
        "auth",
        "request",
        "response",
        "headers",
        "body",
        "stack",
        "exc",
        "refresh_token",
        "access_token",
        "id_token",
        "client_secret",
        "api_key",
        "cookie",
        "set-cookie",
    )
    return any(t in kl for t in sensitive_tokens)


def _coerce_lower_str(v: Any) -> Optional[str]:
    if isinstance(v, str):
        return v.strip().lower() or None
    return None


def _coerce_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if v == 0:
            return False
        if v == 1:
            return True
    if isinstance(v, str):
        lv = v.strip().lower()
        if lv in {"true", "yes", "1"}:
            return True
        if lv in {"false", "no", "0"}:
            return False
    return None


def _coerce_non_negative_int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int,)):
        return max(0, int(v))
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        if v < 0:
            return 0
        return int(v)
    if isinstance(v, str):
        try:
            n = int(v.strip())
            return max(0, n)
        except (ValueError, TypeError):
            return None
    return None
