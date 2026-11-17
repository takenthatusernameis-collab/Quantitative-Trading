## What changed (this session)

- Extended the `validate_parameters` structural guard in `tests/test_repository_integrity.py`:
  - Added `_tree_validate_parameters_override_mismatches` and `_documented_validate_parameters_override_mismatches`.
  - Guard now enforces the canonical override signature `(self) -> None` for every `validate_parameters` override outside the base `Strategy` class (rejects wrong first-parameter name and wrong parameter counts 0 or 2; still enforces `-> None`).
  - Replaced `test_validate_parameters_overrides_annotated_none` to use the helpers and include synthetic negative controls (wrong first-parameter name `cls`, 0 params, 2 params) plus a canonical positive control.

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py -q` -> `46 passed` (after change and after formatting).
- `python -m ruff check tests/test_repository_integrity.py` -> `All checks passed!`
- `python -m black --check tests/test_repository_integrity.py` -> `1 file would be left unchanged`.
- `python -m black tests/test_repository_integrity.py` applied once to satisfy formatting.
- `git diff -- tests/test_repository_integrity.py` shows only the intended guard/test changes.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed; workflow files are controller-managed and cannot be persisted by an agent session.
- The broader test suite was not rerun this session (only `tests/test_repository_integrity.py` changed; prior handoff recorded `4005 passed, 142 deselected`).
- No source modules under `quant_trading/` or `examples/` required fixes (tree scan found zero `validate_parameters` signature violations).

## Approaches that already failed and why (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.
- Extending `See Also:`/`References:` guards to validate referenced-name resolution remains low value here: no `See Also:`/`References:` sections exist anywhere in `quant_trading/` or `examples/`, so such a guard would pass vacuously (only synthetic controls would exercise it).

## One precise next task

- Extend the structural-guard style to `Strategy.update_positions` overrides (`quant_trading/strategies/base.py:342` declares `(self, positions: dict[str, Position]) -> None`): add an AST helper/test in `tests/test_repository_integrity.py` requiring every `update_positions` override outside the base `Strategy` class to have exactly 2 parameters named `(self, positions)`, a `positions` annotation matching `dict[str, Position]`, and return `-> None`. Include synthetic negative controls (wrong first/second param name, wrong param count, wrong `positions` annotation, wrong/missing return) and a canonical positive control, then rerun `python -m pytest tests/test_repository_integrity.py -q`, `ruff check`, and `black --check` on the modified test file. If any real-tree violations appear, fix them with the smallest compatible change and verify focused tests for the affected modules.
