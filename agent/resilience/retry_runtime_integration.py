from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, Protocol, Tuple, Mapping, cast
import copy
import json


# Public integration result types
@dataclass(frozen=True)
class ClassificationResult:
    retryable: bool
    category: str
    reason: str
    provider: str = "none"


@dataclass(frozen=True)
class BudgetProjection:
    exhausted: bool
    remaining_attempts: Optional[int]
    provider: str = "none"


@dataclass(frozen=True)
class NormalizedLifecycle:
    outcome: str  # expected values: ok | error | cancelled | deadline_exceeded | unknown
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    transient_hint: Optional[bool] = None


@dataclass(frozen=True)
class IntegrationAuthority:
    retry_state_authority: str = "MissionQueue"
    retry_execution_authority: str = "existing_runtime_controller"
    grant: bool = False  # This integration never grants retry authority


@dataclass(frozen=True)
class IntegrationProjection:
    mission_id: str
    execution_id: str
    attempt: int
    checkpoint_id: Optional[str]
    lifecycle: NormalizedLifecycle
    classification: ClassificationResult
    budget: BudgetProjection
    recommended_action: str  # controller_decides | retry_possible | do_not_retry | cancelled | deadline_exceeded | none
    authority: IntegrationAuthority = field(default_factory=IntegrationAuthority)
    metrics_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic, JSON-serializable payload
        # Avoid relying on asdict for nested dataclasses order; build manually in a stable order
        return {
            "mission_id": self.mission_id,
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "checkpoint_id": self.checkpoint_id,
            "lifecycle": {
                "outcome": self.lifecycle.outcome,
                "error_code": self.lifecycle.error_code,
                "error_class": self.lifecycle.error_class,
                "transient_hint": self.lifecycle.transient_hint,
            },
            "classification": {
                "retryable": self.classification.retryable,
                "category": self.classification.category,
                "reason": self.classification.reason,
                "provider": self.classification.provider,
            },
            "budget": {
                "exhausted": self.budget.exhausted,
                "remaining_attempts": self.budget.remaining_attempts,
                "provider": self.budget.provider,
            },
            "recommended_action": self.recommended_action,
            "authority": {
                "retry_state_authority": self.authority.retry_state_authority,
                "retry_execution_authority": self.authority.retry_execution_authority,
                "grant": self.authority.grant,
            },
            "metrics_payload": copy.deepcopy(self.metrics_payload),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


# Provider protocols (injected or auto-detected)
class ClassificationProvider(Protocol):
    def classify(self, lifecycle: NormalizedLifecycle) -> ClassificationResult:  # pragma: no cover - protocol only
        ...


class BudgetProjectionProvider(Protocol):
    def project(self, mission_id: str, mission_queue_view: Mapping[str, Any]) -> BudgetProjection:  # pragma: no cover
        ...


class ExecutionAdapter(Protocol):
    def adapt(self, lifecycle_event: Mapping[str, Any]) -> NormalizedLifecycle:  # pragma: no cover
        ...


class MetricsSink(Protocol):
    def emit(self, payload: Mapping[str, Any]) -> None:  # pragma: no cover
        ...


# Safe, provider-independent defaults
class _NullClassifier:
    def classify(self, lifecycle: NormalizedLifecycle) -> ClassificationResult:
        # Fail-closed: unknown classification => not retryable
        return ClassificationResult(
            retryable=False,
            category="unknown",
            reason="no-classifier",
            provider="none",
        )


class _NullBudgetProjector:
    def project(self, mission_id: str, mission_queue_view: Mapping[str, Any]) -> BudgetProjection:
        # Fail-closed: do not assert availability if uncertainty
        # Try to infer remaining attempts deterministically without side-effects
        remaining: Optional[int] = None
        exhausted = False
        try:
            attempts_done = mission_queue_view.get("attempts_done")  # type: ignore[assignment]
            max_attempts = mission_queue_view.get("max_attempts")  # type: ignore[assignment]
            if isinstance(attempts_done, int) and isinstance(max_attempts, int):
                remaining_calc = max(0, max_attempts - attempts_done)
                remaining = remaining_calc
                exhausted = remaining_calc <= 0
        except Exception:
            # Keep fail-closed defaults
            remaining = None
            exhausted = False
        return BudgetProjection(exhausted=exhausted, remaining_attempts=remaining, provider="none")


class _NullExecutionAdapter:
    def adapt(self, lifecycle_event: Mapping[str, Any]) -> NormalizedLifecycle:
        # Minimal, deterministic normalization
        event = dict(lifecycle_event or {})
        outcome = str(event.get("outcome", "unknown")).lower()
        if outcome not in {"ok", "error", "cancelled", "deadline_exceeded"}:
            # Try common mappings
            status = str(event.get("status", "")).lower()
            if status in {"success", "ok"}:
                outcome = "ok"
            elif status in {"error", "failed", "failure"}:
                outcome = "error"
            elif status in {"cancelled", "canceled"}:
                outcome = "cancelled"
            elif status in {"deadline_exceeded", "timeout", "timed_out"}:
                outcome = "deadline_exceeded"
            else:
                outcome = "unknown"
        return NormalizedLifecycle(
            outcome=outcome,
            error_code=(event.get("error_code") if isinstance(event.get("error_code"), str) else None),
            error_class=(event.get("error_class") if isinstance(event.get("error_class"), str) else None),
            transient_hint=(event.get("transient_hint") if isinstance(event.get("transient_hint"), bool) else None),
        )


class _NoopMetricsSink:
    def __init__(self) -> None:
        self._last: Optional[Dict[str, Any]] = None

    def emit(self, payload: Mapping[str, Any]) -> None:
        # Best-effort, never-raise, never-block
        try:
            self._last = copy.deepcopy(dict(payload))
        except Exception:
            self._last = {"error": "metrics-serialization-failed"}

    @property
    def last(self) -> Optional[Dict[str, Any]]:
        return self._last


@dataclass(frozen=True)
class IntegrationContext:
    mission_id: str
    execution_id: str
    attempt: int
    checkpoint_id: Optional[str]
    mission_queue_view: Mapping[str, Any]


@dataclass
class RetryRuntimeIntegration:
    classifier: ClassificationProvider = field(default_factory=_NullClassifier)
    budget_projector: BudgetProjectionProvider = field(default_factory=_NullBudgetProjector)
    execution_adapter: ExecutionAdapter = field(default_factory=_NullExecutionAdapter)
    metrics_sink: MetricsSink = field(default_factory=_NoopMetricsSink)

    def project_lifecycle(self, lifecycle_event: Mapping[str, Any], ctx: IntegrationContext) -> IntegrationProjection:
        # Defensive copies to guarantee no mutation of inputs
        lifecycle_event_copy = copy.deepcopy(dict(lifecycle_event or {}))
        mission_queue_view_copy = copy.deepcopy(dict(ctx.mission_queue_view or {}))

        # Step 1: normalize lifecycle via adapter
        try:
            normalized = self.execution_adapter.adapt(lifecycle_event_copy)
        except Exception:
            # Fail-closed normalization
            normalized = NormalizedLifecycle(outcome="unknown")

        # Step 2: classification
        classification = ClassificationResult(retryable=False, category="unknown", reason="not-evaluated", provider="none")
        try:
            classification = self.classifier.classify(normalized)
            # Enforce deterministic shape in case providers return unexpected values
            if not isinstance(classification.retryable, bool):
                classification = ClassificationResult(
                    retryable=False, category=str(getattr(classification, "category", "unknown")), reason="invalid-classifier", provider=str(getattr(classification, "provider", "external")),
                )
        except Exception:
            classification = ClassificationResult(retryable=False, category="unknown", reason="classification-error", provider="none")

        # Step 3: budget projection from MissionQueue (read-only)
        budget = BudgetProjection(exhausted=False, remaining_attempts=None, provider="none")
        try:
            budget = self.budget_projector.project(ctx.mission_id, mission_queue_view_copy)
            # Ensure known-safe keys
            budget = BudgetProjection(
                exhausted=bool(getattr(budget, "exhausted", False)),
                remaining_attempts=(
                    int(getattr(budget, "remaining_attempts")) if isinstance(getattr(budget, "remaining_attempts", None), int) else None
                ),
                provider=str(getattr(budget, "provider", "external")),
            )
        except Exception:
            budget = BudgetProjection(exhausted=False, remaining_attempts=None, provider="none")

        # Step 4: derive recommended action without granting authority
        recommended_action = self._derive_action(normalized, classification, budget)

        # Step 5: metrics payload (never throws)
        metrics_payload = self._build_metrics_payload(
            ctx=ctx,
            lifecycle=normalized,
            classification=classification,
            budget=budget,
            recommended_action=recommended_action,
        )
        try:
            self.metrics_sink.emit(metrics_payload)
        except Exception:
            # Explicitly ignore metrics issues to fail-closed
            pass

        # Step 6: build projection result
        projection = IntegrationProjection(
            mission_id=ctx.mission_id,
            execution_id=ctx.execution_id,
            attempt=ctx.attempt,
            checkpoint_id=ctx.checkpoint_id,
            lifecycle=normalized,
            classification=classification,
            budget=budget,
            recommended_action=recommended_action,
            authority=IntegrationAuthority(),
            metrics_payload=metrics_payload,
        )
        return projection

    @staticmethod
    def _derive_action(lifecycle: NormalizedLifecycle, classification: ClassificationResult, budget: BudgetProjection) -> str:
        # Controller remains the authority; we only provide advisory projection
        # Priority: terminal reasons override retryability
        if lifecycle.outcome == "cancelled":
            return "cancelled"
        if lifecycle.outcome == "deadline_exceeded":
            # Retry policy may apply later, but we do not assert authority here
            return "deadline_exceeded"
        if lifecycle.outcome == "ok":
            return "controller_decides"

        # For errors/unknown: only signal possibility, never grant
        try:
            if classification.retryable and not budget.exhausted:
                return "retry_possible"
            # Non-retryable or exhausted
            if (not classification.retryable) or budget.exhausted:
                return "do_not_retry"
        except Exception:
            # Fail-closed, avoid suggesting retries
            return "none"
        # Default
        return "none"

    @staticmethod
    def _build_metrics_payload(
        ctx: IntegrationContext,
        lifecycle: NormalizedLifecycle,
        classification: ClassificationResult,
        budget: BudgetProjection,
        recommended_action: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "mission_id": ctx.mission_id,
            "execution_id": ctx.execution_id,
            "attempt": ctx.attempt,
            "checkpoint_id": ctx.checkpoint_id,
            "lifecycle_outcome": lifecycle.outcome,
            "classification_retryable": classification.retryable,
            "classification_category": classification.category,
            "classification_provider": classification.provider,
            "budget_exhausted": budget.exhausted,
            "budget_remaining_attempts": budget.remaining_attempts,
            "budget_provider": budget.provider,
            "recommended_action": recommended_action,
            # Static invariants for observability
            "retry_state_authority": "MissionQueue",
            "retry_execution_authority": "existing_runtime_controller",
            "provider_independence_preserved": True,
        }
        # Guarantee JSON-serializable (defensive copy with basic types only)
        try:
            json.dumps(payload)
        except Exception:
            # Last resort: coerce non-serializable fields
            for k, v in list(payload.items()):
                try:
                    json.dumps({k: v})
                except Exception:
                    payload[k] = str(v)
        return payload


__all__ = [
    "ClassificationResult",
    "BudgetProjection",
    "NormalizedLifecycle",
    "IntegrationAuthority",
    "IntegrationProjection",
    "IntegrationContext",
    "RetryRuntimeIntegration",
]
