# Copyright (c) MITIGATE
# Lightweight structured retry observability component.
# Provider-independent. No network I/O. No global mutable state.

from __future__ import annotations

from typing import Callable, Dict, Mapping, Optional, Union
import time as _time
from agent.resilience.retry_classification import RetryCategory


class RetryMetrics:
    """
    Structured event builder for retry attempts/outcomes.

    Returns serialization-safe dictionaries only (ints, floats, strings, None, dicts).
    No external dependencies, no side effects.
    """

    __slots__ = ("_time",)

    _ALLOWED_CLASSIFICATIONS = {
        RetryCategory.RETRYABLE.value,
        RetryCategory.NON_RETRYABLE.value,
        RetryCategory.CANCELLED.value,
        RetryCategory.DEADLINE_EXCEEDED.value,
        RetryCategory.EXHAUSTED.value,
    }

    # heuristics to prevent accidental secret-bearing labels
    _FORBIDDEN_LABEL_SUBSTRINGS = (
        "secret", "token", "password", "passwd", "authorization",
        "api_key", "apikey", "access_key", "client_secret", "private_key",
    )

    def __init__(self, *, time_provider: Callable[[], float] | None = None) -> None:
        self._time: Callable[[], float] = time_provider or _time.time

    def attempt_event(
        self,
        *,
        attempt: int,
        classification: Union[RetryCategory, str],
        budget_remaining: Optional[int] = None,
        backoff_seconds: Optional[float] = None,
        jitter_seconds: Optional[float] = None,
        circuit_state: Optional[str] = None,
        mission_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        labels: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, object]:
        """
        Build a deterministic structured event for a retry attempt.
        - attempt numbers start at 1 for the first execution attempt by convention.
        """
        cls = self._normalize_classification(classification)
        att = self._validate_attempt(attempt)
        bud = self._validate_optional_int("budget_remaining", budget_remaining)
        back = self._validate_optional_float("backoff_seconds", backoff_seconds)
        jit = self._validate_optional_float("jitter_seconds", jitter_seconds)
        circ = self._validate_optional_str("circuit_state", circuit_state)
        mid = self._validate_optional_str("mission_id", mission_id)
        eid = self._validate_optional_str("execution_id", execution_id)
        lbl = self._sanitize_labels(labels)

        # deterministic key insertion order
        event: Dict[str, object] = {
            "type": "retry_attempt",
            "timestamp": float(self._time()),
            "attempt": att,
            "classification": cls,
            "budget_remaining": bud,
            "backoff_delay": back,
            "jittered_delay": jit,
            "circuit_state": circ,
            "mission_id": mid,
            "execution_id": eid,
        }
        if lbl is not None and len(lbl) > 0:
            event["labels"] = lbl
        return event

    # ----- validators -----
    def _normalize_classification(self, c: Union[RetryCategory, str]) -> str:
        if isinstance(c, RetryCategory):
            return c.to_wire()
        if not isinstance(c, str):
            raise TypeError("classification must be a RetryCategory or str")
        v = c.strip().lower()
        if v not in self._ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f"classification must be one of {sorted(self._ALLOWED_CLASSIFICATIONS)}"
            )
        return v

    @staticmethod
    def _validate_attempt(attempt: int) -> int:
        if isinstance(attempt, bool):
            raise TypeError("attempt must be int >= 1, not bool")
        if not isinstance(attempt, int):
            raise TypeError("attempt must be int >= 1")
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        return attempt

    @staticmethod
    def _validate_optional_int(name: str, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            raise TypeError(f"{name} must be a non-negative int or None, not bool")
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative int or None")
        return value

    @staticmethod
    def _validate_optional_float(name: str, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool):
            raise TypeError(f"{name} must be a float >= 0 or None, not bool")
        if not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a float >= 0 or None")
        v = float(value)
        if v < 0 or not (v == v):  # v==v filters NaN
            raise ValueError(f"{name} must be a finite number >= 0")
        return v

    @staticmethod
    def _validate_optional_str(name: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a str or None")
        s = value.strip()
        return s if s else None

    def _sanitize_labels(self, labels: Optional[Mapping[str, str]]) -> Optional[Mapping[str, str]]:
        if labels is None:
            return None
        clean: Dict[str, str] = {}
        for k, v in labels.items():
            if k is None:
                continue
            ks = str(k)
            ls = ks.lower()
            if any(substr in ls for substr in self._FORBIDDEN_LABEL_SUBSTRINGS):
                raise ValueError("secret-bearing label keys are not allowed in retry metrics")
            # values as strings only
            vs = "" if v is None else str(v)
            clean[ks] = vs
        return clean


__all__ = ["RetryMetrics"]
