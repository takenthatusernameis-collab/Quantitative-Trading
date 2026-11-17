## What changed (this session)

- Extended the AST-only `generate_signals` override guard in `tests/test_repository_integrity.py` to pin the `data` parameter annotation to `dict[str, pd.DataFrame]` in addition to the existing `-> list[Signal]` return annotation:
  - Added `_normalize_generate_signals_data_annotation` (recognizes only `dict[str, pd.DataFrame]` / `Dict[str, pd.DataFrame]` with `pd.DataFrame` attribute form).
  - Extended `_tree_generate_signals_annotation_mismatches` to validate the second positional parameter (`data`) and report drift as `<Class>.generate_signals data parameter is ...` (or `untyped`).
  - Updated `_documented_generate_signals_annotation_mismatches` and `test_generate_signals_overrides_return_list_signal` to reflect full-signature guarding.
  - Test now includes negative controls for return drift (`-> list[int]`) and data-annotation drift (`data: dict`), plus a canonical-signature positive control and real-tree assertion.
- Mirrors the Strategy base signature `(self, data: dict[str, pd.DataFrame]) -> list[Signal]` to prevent future parameter-annotation drift.

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py::test_generate_signals_overrides_return_list_signal -q` -> `1 passed`.
- `python -m pytest tests/test_repository_integrity.py -q` -> `46 passed`.
- `python -m ruff check tests/test_repository_integrity.py` -> `All checks passed!`
- `python -m black --check tests/test_repository_integrity.py` -> `1 file would be left unchanged`.
- `git diff --check` -> clean.
- Working diff: `tests/test_repository_integrity.py` and `HANDOFF_NEXT_AGENT.md` only.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed; workflow files are controller-managed and cannot be persisted by an agent session.
- The broader test suite was not rerun this session (only `tests/test_repository_integrity.py` changed; prior handoff recorded `4005 passed, 142 deselected`).

## Approaches that already failed and why (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.
- Extending `See Also:`/`References:` guards to validate referenced-name resolution remains low value here: no `See Also:`/`References:` sections exist anywhere in `quant_trading/` or `examples/`, so such a guard would pass vacuously (only synthetic controls would exercise it).

## One precise next task

- Extend the same `generate_signals` structural guard to also require the first parameter name to be `self` and the second to be `data` for every override outside the base `Strategy` class (matching the canonical signature). In `tests/test_repository_integrity.py`, update `_tree_generate_signals_annotation_mismatches` to record mismatches when `len(item.args.args) != 2` or parameter names differ, add synthetic negative controls (e.g. `def generate_signals(self, market_data: ...)` / wrong arg count) and keep the canonical positive control, then rerun `python -m pytest tests/test_repository_integrity.py -q`, `ruff check`, and `black --check` on the modified test file. Expected: zero real-tree violations and the integrity suite stays green.
