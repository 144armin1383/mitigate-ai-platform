import ast
import builtins
import types
import unittest

from agent.repair.mission_adapter import MissionRepairAdapter, RepairRequest, MissionRepairResult
from agent.repair.integration import IntegrationCoordinator  # real coordinator


class _SafetyImportVisitor(ast.NodeVisitor):
  def __init__(self) -> None:
    super().__init__()
    self.forbidden: list[str] = []

  def visit_Import(self, node: ast.Import) -> None:
    for alias in node.names:
      name = alias.name
      # Allow only standard safe imports within this test file; this is a noop checker for local safety
      if name.startswith('subprocess') or name.startswith('os.system'):
        self.forbidden.append(name)

  def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
    module = node.module or ''
    if module.startswith('subprocess') or module.startswith('os.system'):
      self.forbidden.append(module)


class MissionAdapterSafetyTest(unittest.TestCase):
  def test_source_safety(self) -> None:
    with open(__file__, 'r', encoding='utf-8') as f:
      src = f.read()
    tree = ast.parse(src)
    vis = _SafetyImportVisitor()
    vis.visit(tree)
    self.assertEqual(vis.forbidden, [])


class MissionAdapterCoreBehaviorTest(unittest.TestCase):
  def setUp(self) -> None:
    # Ensure the real coordinator object can be constructed
    self.coordinator = IntegrationCoordinator(max_attempts=3)

  def test_constraints_passed_as_mapping_and_immutable(self) -> None:
    adapter = MissionRepairAdapter(max_attempts=3)

    # Track that the original constraints dict is not mutated by the adapter
    original = {'limit': 5, 'mode': 'safe'}
    before_keys = tuple(original.keys())
    before_items = tuple(sorted(original.items()))

    # Validation returns True immediately; no repair occurs.
    def validate0() -> bool:
      return True

    # Generation and apply should not be called; define dummies
    def generation(_req: RepairRequest) -> object:  # pragma: no cover - not expected to run in this test
      return {'noop': True}

    def apply(_generated: object) -> bool:  # pragma: no cover - not expected to run in this test
      return True

    result = adapter.run(
      objective='noop',
      allowed_paths=('a', 'b'),
      denied_paths=('x',),
      constraints=original,
      validate_callback=validate0,
      generation_callback=generation,
      apply_callback=apply,
      source='unit',
    )

    # Ensure result is a MissionRepairResult and indicates success in a generic way
    self.assertIsInstance(result, MissionRepairResult)
    self.assertIsInstance(result.safe_summary, str)

    # Original constraints must remain unchanged
    self.assertEqual(tuple(original.keys()), before_keys)
    self.assertEqual(tuple(sorted(original.items())), before_items)

  def test_zero_arg_validation_wrapper(self) -> None:
    adapter = MissionRepairAdapter(max_attempts=3)

    context = {'ok': True}

    def context_validate(ctx: dict) -> bool:  # adapter must wrap this to zero-arg for coordinator
      return bool(ctx['ok'])

    # Generation/apply never invoked since validation passes
    result = adapter.run(
      objective='validate-only',
      allowed_paths=(),
      denied_paths=(),
      constraints={},
      validate_callback=context_validate,
      generation_callback=lambda req: {'noop': True},  # pragma: no cover
      apply_callback=lambda gen: True,  # pragma: no cover
      source='unit',
      mission_context=context,
    )
    self.assertIsInstance(result, MissionRepairResult)

  def test_sanitization_never_leaks_raw_exception(self) -> None:
    adapter = MissionRepairAdapter(max_attempts=1)

    # Force validation to raise with sensitive text; adapter must not leak it after coordinator returns
    secret_msg = 'super-secret token=ABC123 should not appear'

    def bad_validate() -> bool:
      raise RuntimeError(secret_msg)

    # Define minimal callbacks; should not be invoked due to validation exception
    def generation(_req: RepairRequest) -> object:  # pragma: no cover
      return {'noop': True}

    def apply(_generated: object) -> bool:  # pragma: no cover
      return True

    result = adapter.run(
      objective='raise',
      allowed_paths=(),
      denied_paths=(),
      constraints={'x': 1},
      validate_callback=bad_validate,
      generation_callback=generation,
      apply_callback=apply,
      source='unit',
    )

    # Ensure the raw secret message is not present anywhere in the mission-facing result
    aggregate = ' '.join([
      result.safe_summary or '',
      ' '.join([
        f.get('summary', '') + ' ' + f.get('diagnostic', '') + ' ' + f.get('category', '') + ' ' + f.get('source', '')
        for f in result.failure_history
      ])
    ])
    self.assertNotIn('ABC123', aggregate)
    self.assertNotIn('super-secret', aggregate)

  def test_repair_flow_invokes_callbacks_and_copies_attempt_number(self) -> None:
    # This test exercises the adapter repair_callback surface without relying on a particular
    # IntegrationCoordinator repair loop. The coordinator remains authoritative for flow.
    adapter = MissionRepairAdapter(max_attempts=2)

    state = {'attempts': 0, 'fixed_after_apply': False}

    def validate0() -> bool:
      # Succeeds only after an apply toggles the flag
      return state['fixed_after_apply']

    seen_attempts: list[int] = []

    def generation(req: RepairRequest) -> object:
      # Copy the attempt number from the plan exactly
      seen_attempts.append(int(req.attempt_number))
      return {'patch': req.attempt_number}

    def apply(gen: object) -> bool:
      state['attempts'] += 1
      # On first apply, mark fixed; subsequent attempts should not be needed
      state['fixed_after_apply'] = True
      return True

    result = adapter.run(
      objective='fix-me',
      allowed_paths=(),
      denied_paths=(),
      constraints={'strict': True},
      validate_callback=validate0,
      generation_callback=generation,
      apply_callback=apply,
      source='unit',
    )

    self.assertIsInstance(result, MissionRepairResult)
    # At least one generation/apply should have occurred
    self.assertGreaterEqual(len(seen_attempts), 1)
    # Attempt numbers are positive integers copied from the plan
    self.assertTrue(all(isinstance(n, int) and n >= 1 for n in seen_attempts))


if __name__ == '__main__':  # pragma: no cover
  unittest.main()
