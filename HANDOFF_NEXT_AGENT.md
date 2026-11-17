## What changed (this session)

- Added a new AST-only docstring/signature guard in `tests/test_repository_integrity.py` that pins every `generate_signals` override (outside the base `Strategy` class) to the base-class return annotation `-> list[Signal]`:
  - `_normalize_generate_signals_annotation` (recognizes only `list[Signal]` / `List[Signal]`, returns None otherwise)
  - `_tree_generate_signals_annotation_mismatches` (synthetic-tree-testable helper; skips the base `Strategy` declaration)
  - `_documented_generate_signals_annotation_mismatches` (scans `quant_trading` and `examples`)
  - `test_generate_signals_overrides_return_list_signal` (negative control: `-> list[int]` flagged; positive control: `-> list[Signal]` passes; real-tree assertion)
- Mirrors the existing `test_validate_parameters_overrides_annotated_none` guard (line ~164) for the other half of the Strategy override contract.

## What was actually verified (evidence)

- New guard: `python -m pytest tests/test_repository_integrity.py::test_generate_signals_overrides_return_list_signal -q` -> passes.
- Full integrity suite: `python -m pytest tests/test_repository_integrity.py -q` -> `46 passed` (was 45).
- `python -m ruff check tests/test_repository_integrity.py` -> `All checks passed!`.
- `python -m black --check tests/test_repository_integrity.py` -> `1 file would be left unchanged`.
- `python -m mypy tests/test_repository_integrity.py` -> `Success: no issues found in 1 source file` (unused-section notes are pre-existing for other modules).
- `git diff --check` passed.
- Diff: `tests/test_repository_integrity.py` only, 98 insertions, 0 deletions.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed; workflow files are controller-managed and cannot be persisted by an agent session.
- The broader suite (`pytest` default markers) was previously run green: `4005 passed, 142 deselected` (not re-run this session since no source changed, only a test was added).

## Approaches that already failed and why (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.
- Extending the `See Also:`/`References:` guards to validate referenced-name resolution is LOW VALUE here: no `See Also:`/`References:` sections exist anywhere in `quant_trading/` or `examples/`, so such a guard would pass vacuously (only synthetic controls would exercise it). The handoff's "consider" suggestion is not actionable.

## One precise next task (if continuing this line of work)

- Extend the new `generate_signals` guard to also pin the `data` parameter annotation to `dict[str, pd.DataFrame]` (matching `Strategy.generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]`). Same pattern: add a parameter-annotation normalizer, extend `_tree_generate_signals_annotation_mismatches` to compare the first parameter, add synthetic negative/positive controls, and assert the real tree is clean. Zero current violations expected (every override already uses `dict[str, pd.DataFrame]`), so it passes cleanly and prevents future signature drift.

(End of file)
