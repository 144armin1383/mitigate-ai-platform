# Copyright (c) MITIGATE
# Deterministic native retry classification contract.
# Provider-independent. No side effects.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Dict
import asyncio


class RetryCategory(str, Enum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    EXHAUSTED = "exhausted"

    def to_wire(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ClassificationResult:
    category: RetryCategory
    reason: Optional[str] = None
    metadata: Optional[Mapping[str, str]] = None

    def to_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "classification": self.category.to_wire(),
        }
        if self.reason is not None:
            out["reason"] = self.reason
        if self.metadata is not None and len(self.metadata) > 0:
            # ensure plain str->str mapping for serialization safety
            out["metadata"] = {str(k): str(v) for k, v in self.metadata.items()}
        return out


class RetryClassifier:
    """
    Deterministic classifier for retry outcomes.

    Rules (applied in order):
    - exhausted=True -> EXHAUSTED
    - cancelled=True or asyncio.CancelledError -> CANCELLED
    - deadline_exceeded=True or built-in TimeoutError -> DEADLINE_EXCEEDED
    - retryable_hint in {True, False} determines RETRYABLE vs NON_RETRYABLE
    - otherwise, fail-closed to NON_RETRYABLE

    The classifier accepts optional provider-neutral metadata. No provider-specific
    dependencies are introduced here.
    """

    __slots__ = ()

    def classify(
        self,
        error: Optional[BaseException],
        *,
        exhausted: bool = False,
        cancelled: bool = False,
        deadline_exceeded: bool = False,
        retryable_hint: Optional[bool] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> ClassificationResult:
        if error is None and not (exhausted or cancelled or deadline_exceeded or isinstance(retryable_hint, bool)):
            raise ValueError("Nothing to classify: provide an error or classification flags")

        # Resolution order is deterministic and explicit
        if exhausted:
            return ClassificationResult(RetryCategory.EXHAUSTED, reason or "budget_exhausted")

        if cancelled or isinstance(error, asyncio.CancelledError):
            return ClassificationResult(RetryCategory.CANCELLED, reason or "cancelled")

        if deadline_exceeded or isinstance(error, TimeoutError):
            return ClassificationResult(RetryCategory.DEADLINE_EXCEEDED, reason or "deadline_exceeded")

        if isinstance(retryable_hint, bool):
            if retryable_hint:
                return ClassificationResult(RetryCategory.RETRYABLE, reason or "hint_retryable", self._sanitize_meta(metadata))
            return ClassificationResult(RetryCategory.NON_RETRYABLE, reason or "hint_non_retryable", self._sanitize_meta(metadata))

        # Default: fail-closed to NON_RETRYABLE; attach neutral metadata if present
        return ClassificationResult(RetryCategory.NON_RETRYABLE, reason or "non_retryable", self._sanitize_meta(metadata))

    # ----- internals -----
    @staticmethod
    def _sanitize_meta(metadata: Optional[Mapping[str, object]]) -> Optional[Mapping[str, str]]:
        if metadata is None:
            return None
        # Ensure deterministic, provider-neutral serialization to str->str
        clean: Dict[str, str] = {}
        for k, v in metadata.items():
            ks = str(k)
            vs = "" if v is None else str(v)
            clean[ks] = vs
        return clean


__all__ = ["RetryCategory", "ClassificationResult", "RetryClassifier"]
