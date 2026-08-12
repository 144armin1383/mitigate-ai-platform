# Copyright (c) MITIGATE
# Native retry budget abstraction for deterministic and bounded retry accounting.
# This module is provider-independent and has no side effects.

from __future__ import annotations

from typing import Callable, Optional
import math
import time


class RetryBudget:
    """
    Deterministic retry budget accounting.

    Features:
    - Configurable maximum retry consumption (token-based, not attempt execution)
    - Optional monotonic deadline budget
    - Deterministic remaining-budget calculation
    - Explicit can_retry/consume semantics
    - No sleeping, threading, network, or queue mutation
    - Fail-closed validation
    - Safe unlimited compatibility mode when created with no limits

    Notes:
    - max_retries counts retry tokens only (0 means no retries permitted).
    - Deadline is tracked in a monotonic time domain provided by time_provider.
    - If both max_retries and deadline are None, the budget is unlimited.
    """

    __slots__ = ("_max_retries", "_deadline", "_time", "_consumed")

    def __init__(
        self,
        *,
        max_retries: Optional[int] | None = None,
        deadline_seconds: Optional[float] | None = None,
        time_provider: Optional[Callable[[], float]] = None,
    ) -> None:
        # Validate max_retries
        if isinstance(max_retries, bool):  # fail-closed on bool edge cases
            raise TypeError("max_retries must be an int or None, not bool")
        if max_retries is not None:
            if not isinstance(max_retries, int):
                raise TypeError("max_retries must be an int or None")
            if max_retries < 0:
                raise ValueError("max_retries must be >= 0")

        # Validate deadline_seconds
        if isinstance(deadline_seconds, bool):  # fail-closed on bool edge cases
            raise TypeError("deadline_seconds must be a float or None, not bool")
        if deadline_seconds is not None:
            if not isinstance(deadline_seconds, (int, float)):
                raise TypeError("deadline_seconds must be a number or None")
            if not math.isfinite(deadline_seconds) or deadline_seconds < 0:
                raise ValueError("deadline_seconds must be a finite number >= 0")

        self._time: Callable[[], float] = time_provider or time.monotonic
        self._max_retries: Optional[int] = max_retries
        if deadline_seconds is None:
            self._deadline: Optional[float] = None
        else:
            now = self._time()
            self._deadline = now + float(deadline_seconds)
        self._consumed: int = 0

    # ----- Constructors -----
    @classmethod
    def unlimited(cls) -> "RetryBudget":
        """Unlimited/no-op compatibility mode: no attempt or time limits."""
        return cls(max_retries=None, deadline_seconds=None)

    @classmethod
    def with_time_budget(
        cls, *, seconds: float, time_provider: Optional[Callable[[], float]] = None
    ) -> "RetryBudget":
        """Create a budget limited only by time (unlimited attempts until deadline)."""
        return cls(max_retries=None, deadline_seconds=seconds, time_provider=time_provider)

    # ----- Query API -----
    def can_retry(self, now: Optional[float] = None) -> bool:
        """
        Check if a retry token can be consumed at this moment.
        Does not mutate internal state.
        """
        if self._is_deadline_exceeded(now):
            return False
        if self._max_retries is None:
            return True  # unlimited attempts (subject to deadline if any)
        return self._consumed < self._max_retries

    def consume(self, now: Optional[float] = None) -> bool:
        """
        Attempt to consume a single retry token.
        Returns True if consumed, False if exhausted (by attempts or deadline).
        """
        if not self.can_retry(now):
            return False
        # consume only attempts budget; time budget is gate only
        if self._max_retries is not None:
            self._consumed += 1
        else:
            # Track consumption for introspection even when unlimited attempts.
            self._consumed += 1
        return True

    # ----- Introspection -----
    @property
    def remaining_retries(self) -> Optional[int]:
        """
        Remaining retry tokens if attempts are bounded; otherwise None.
        Never negative.
        """
        if self._max_retries is None:
            return None
        remaining = self._max_retries - self._consumed
        return remaining if remaining >= 0 else 0

    @property
    def consumed_retries(self) -> int:
        return self._consumed

    @property
    def deadline(self) -> Optional[float]:
        """Absolute monotonic deadline or None if not time-bounded."""
        return self._deadline

    def time_remaining(self, now: Optional[float] = None) -> Optional[float]:
        """
        Seconds remaining until deadline; None if not time-limited. Returns 0 when expired.
        """
        if self._deadline is None:
            return None
        t = self._time() if now is None else float(now)
        remaining = self._deadline - t
        return remaining if remaining > 0 else 0.0

    @property
    def is_unlimited(self) -> bool:
        """
        True when there is neither attempts nor time constraint.
        """
        return self._max_retries is None and self._deadline is None

    @property
    def is_exhausted(self) -> bool:
        return not self.can_retry()

    def exhaustion_reason(self, now: Optional[float] = None) -> Optional[str]:
        """
        If exhausted, returns 'deadline' or 'attempts' to indicate the binding limit.
        Returns None if not exhausted.
        """
        if not self.can_retry(now):
            if self._is_deadline_exceeded(now):
                return "deadline"
            return "attempts"
        return None

    # ----- Internals -----
    def _is_deadline_exceeded(self, now: Optional[float]) -> bool:
        if self._deadline is None:
            return False
        t = self._time() if now is None else float(now)
        return t >= self._deadline


__all__ = ["RetryBudget"]
