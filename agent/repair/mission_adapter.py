from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType, SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

# Do not modify the IntegrationCoordinator or its module.
from agent.repair.integration import IntegrationCoordinator  # type: ignore


@dataclass(frozen=True)
class RepairRequest:
  """Immutable repair request passed to the mission-level generation callback.

  This object is intentionally simple and immutable to prevent side-effects.
  The adapter copies the RepairPlan.attempt_number exactly as provided by the
  IntegrationCoordinator.
  """

  objective: Any
  source: Optional[str]
  constraints: Mapping[str, Any]
  attempt_number: int
  plan: Any


@dataclass
class MissionRepairResult:
  """Mission-facing sanitized result translated from IntegrationResult.

  This structure avoids leaking raw exception diagnostics through any of its
  string-bearing fields and preserves a blocked_condition when applicable.
  """

  final_state: str
  safe_summary: str
  failure_history: List[Dict[str, Any]]
  blocked_condition: Optional[str] = None
  attempts: Optional[int] = None
  raw: Optional[Any] = None  # Non-serialized reference to the original IntegrationResult for internal auditing only.


class MissionRepairAdapter:
  """Adapter bridging mission-facing callbacks to IntegrationCoordinator.

  Responsibilities:
  - Preserve caller immutability for allowed/denied paths and constraints.
  - Defensively snapshot constraints as a dict before passing to coordinator.
  - Wrap mission validation into a zero-argument closure for coordinator.
  - Implement repair callback that creates an immutable RepairRequest, invokes
    mission generation and then apply callbacks, returning a minimal
    success/failure object recognized by the coordinator loop.
  - Sanitize translated IntegrationResult history so raw exception messages do
    not leak through the mission-facing boundary.
  - Do not perform independent retries; coordinator remains authoritative.
  """

  def __init__(self, *, max_attempts: int = 3) -> None:
    if max_attempts < 1:
      raise ValueError("max_attempts must be >= 1")
    self._max_attempts = int(max_attempts)

  def run(
    self,
    objective: Any,
    *,
    allowed_paths: Optional[Sequence[str]] = None,
    denied_paths: Optional[Sequence[str]] = None,
    constraints: Optional[Mapping[str, Any]] = None,
    validate_callback: Callable[[], Any] | Callable[[Any], Any],
    generation_callback: Callable[[RepairRequest], Any],
    apply_callback: Callable[[Any], bool],
    source: Optional[str] = None,
    mission_context: Optional[Mapping[str, Any]] = None,
  ) -> MissionRepairResult:
    # Defensive snapshots; do not mutate caller inputs
    safe_allowed_paths = tuple(allowed_paths or ())
    safe_denied_paths = tuple(denied_paths or ())

    # Coordinator requires Mapping supporting .items(); must not pass tuple/list
    safe_constraints: Dict[str, Any] = dict(constraints or {})

    # Zero-arg validation wrapper; capture only immutable/copied mission context
    validate0 = self._wrap_zero_arg_validate(validate_callback, mission_context)

    # Coordinator owns retries. Adapter repair-callback has no loop.
    coordinator = IntegrationCoordinator(max_attempts=self._max_attempts)

    def repair_callback(plan: Any) -> Any:
      attempt_number = getattr(plan, "attempt_number", 0)
      # Immutable request with constraints wrapped as read-only mapping
      request = RepairRequest(
        objective=objective,
        source=source,
        constraints=MappingProxyType(dict(safe_constraints)),
        attempt_number=int(attempt_number),
        plan=plan,
      )

      # 1. generation
      try:
        generated = generation_callback(request)
      except Exception:
        # Return a minimal result recognized by coordinator-style flow
        # without leaking sensitive diagnostics.
        return SimpleNamespace(success=False, category="generation-exception", summary="generation exception")

      if not generated:
        # Treat falsy generation as a failed generation without exceptions.
        return SimpleNamespace(success=False, category="generation-failed", summary="generation failed")

      # 2. apply
      try:
        applied = apply_callback(generated)
      except Exception:
        return SimpleNamespace(success=False, category="apply-exception", summary="apply exception")

      if not applied:
        return SimpleNamespace(success=False, category="apply-failed", summary="apply failed")

      # Success path
      return SimpleNamespace(success=True)

    # Execute the coordinator with correct mapping-typed constraints
    integration_result = coordinator.run(
      objective,
      allowed_paths=safe_allowed_paths,
      denied_paths=safe_denied_paths,
      constraints=dict(safe_constraints),  # ensure Mapping-compatible dict
      validate_callback=validate0,
      repair_callback=repair_callback,
      source=source,
    )

    # Sanitize and translate to mission-facing result
    mission_result = self._translate_and_sanitize_result(integration_result)
    return mission_result

  @staticmethod
  def _wrap_zero_arg_validate(
    validate_callback: Callable[..., Any],
    mission_context: Optional[Mapping[str, Any]],
  ) -> Callable[[], Any]:
    # The coordinator requires a zero-argument validation function.
    # If the provided callback expects a context, this closure supplies it.
    def _validate0() -> Any:
      try:
        # Preferred: context-aware signature
        return validate_callback(mission_context)
      except TypeError:
        # Fallback: zero-arg callable
        return validate_callback()

    return _validate0

  @staticmethod
  def _sanitize_text(value: Any, *, default: str = "") -> str:
    # Convert any value to a conservative single-line safe string.
    if value is None:
      return default
    text = str(value)
    # Replace control chars and collapse whitespace
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text

  @staticmethod
  def _sanitize_failure_record(fr: Any) -> Dict[str, Any]:
    # Extract with getattr to avoid coupling to a strict schema
    category = getattr(fr, "category", None)
    summary = getattr(fr, "summary", None)
    diagnostic = getattr(fr, "diagnostic", None)
    source = getattr(fr, "source", None)
    blocking_condition = getattr(fr, "blocking_condition", None)

    cat_text = MissionRepairAdapter._sanitize_text(category, default="unknown")

    # Never leak raw exception text. Use bounded canonical phrases for known exception categories.
    if cat_text == "validation-exception":
      diag_text = "validation exception"
    elif cat_text == "generation-exception":
      diag_text = "generation exception"
    elif cat_text == "apply-exception":
      diag_text = "apply exception"
    else:
      diag_text = MissionRepairAdapter._sanitize_text(diagnostic, default="")

    # Summary and source are sanitized to single-line safe strings
    sum_text = MissionRepairAdapter._sanitize_text(summary, default="")
    src_text = MissionRepairAdapter._sanitize_text(source, default="")

    rec: Dict[str, Any] = {
      "category": cat_text,
      "summary": sum_text,
      "diagnostic": diag_text,
    }
    if src_text:
      rec["source"] = src_text
    if blocking_condition is not None:
      # If the coordinator provided a blocking condition, sanitize but preserve its content
      rec["blocking_condition"] = MissionRepairAdapter._sanitize_text(blocking_condition, default="")
    return rec

  @staticmethod
  def _derive_blocked_condition(final_state: str, failure_history: List[Dict[str, Any]]) -> Optional[str]:
    if final_state != "blocked" or not failure_history:
      return None

    # Attempt to derive the most relevant blocked condition from the latest failure record
    last = failure_history[-1]
    bc = last.get("blocking_condition")
    if isinstance(bc, str) and bc:
      return bc

    # Fallback: preserve the exact category when it matches a blocked-like category
    category = last.get("category")
    if isinstance(category, str) and category:
      return category
    return None

  def _translate_and_sanitize_result(self, integration_result: Any) -> MissionRepairResult:
    final_state = self._sanitize_text(getattr(integration_result, "final_state", None), default="unknown")
    safe_summary = self._sanitize_text(getattr(integration_result, "safe_summary", None), default=final_state)

    # History may be a list of FailureRecord-like objects
    raw_history: Iterable[Any] = getattr(integration_result, "failure_history", []) or []
    sanitized_history: List[Dict[str, Any]] = [self._sanitize_failure_record(fr) for fr in raw_history]

    blocked_condition = self._derive_blocked_condition(final_state, sanitized_history)

    attempts = getattr(integration_result, "attempts", None)
    try:
      attempts_int = int(attempts) if attempts is not None else None
    except Exception:
      attempts_int = None

    # Return mission-facing sanitized snapshot; retain a non-serialized raw reference for internal audit if needed
    return MissionRepairResult(
      final_state=final_state,
      safe_summary=safe_summary,
      failure_history=sanitized_history,
      blocked_condition=blocked_condition,
      attempts=attempts_int,
      raw=integration_result,
    )
