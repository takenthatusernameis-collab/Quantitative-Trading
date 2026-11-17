## What changed (this session)

- Extended `_tree_generate_signals_annotation_mismatches` in `tests/test_repository_integrity.py` to also enforce the canonical parameter signature `(self, data)` for every `generate_signals` override outside the base `Strategy` class:
  - Reports a mismatch when `len(item.args.args) != 2` (wrong parameter count).
  - Reports a mismatch when the first parameter name is not `self`.
  - Reports a mismatch when the second parameter name is not `data`.
  - Short-circuits annotation checks when the parameter count is wrong (avoids indexing a missing second arg).
- Extended `test_generate_signals_overrides_return_list_signal` with synthetic negative controls for first-parameter drift (`cls` instead of `self`), second-parameter drift (`market_data` instead of `data`), and wrong parameter count (3 args), keeping the canonical positive control and the existing return/data-annotation controls.

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py -q` -> `46 passed`.
- `python -m ruff check tests/test_repository_integrity.py` -> `All checks passed!`
- `python -m black --check tests/test_repository_integrity.py` -> `1 file would be left unchanged`.
- Working diff: `tests/test_repository_integrity.py` only.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed; workflow files are controller-managed and cannot be persisted by an agent session.
- The broader test suite was not rerun this session (only the integrity test file changed; prior handoff recorded `4005 passed, 142 deselected`).

## Approaches that already failed and why (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.
- Extending `See Also:`/`References:` guards to validate referenced-name resolution remains low value here: no `See Also:`/`References:` sections exist anywhere in `quant_trading/` or `examples/`, so such a guard would pass vacuously (only synthetic controls would exercise it).

## One precise next task

- Extend the same structural-guard style to `test_validate_parameters_overrides_annotated_none` (`tests/test_repository_integrity.py:164`): require every `validate_parameters` override outside the base `Strategy` class to have exactly one parameter named `self` (matching the base signature `validate_parameters(self) -> None` at `quant_trading/strategies/base.py:324`). Add synthetic negative controls (wrong first-parameter name, wrong parameter count of 0 or 2) and keep the canonical positive control, then rerun `python -m pytest tests/test_repository_integrity.py -q`, `ruff check`, and `black --check` on the modified test file. Expected: zero real-tree violations and the integrity suite stays green.
