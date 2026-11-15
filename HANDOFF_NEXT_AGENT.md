## What changed (this session)
Completed the type-annotation migration of `tests/test_strategies_examples.py` (593 defs, 8291 lines):
- Added return annotations to all 555 previously-untyped functions:
  - `-> None` for 550 test methods/helpers that never return a value.
  - Specific return types for the 5 value-returning helpers in `TestExamplesRemainingCoverage`:
    `_ohlcv` -> `pd.DataFrame`, `_ohlcv_no_volume` -> `pd.DataFrame`,
    `_ohlcv_prev_nan`/`_ohlcv_last_zero`/`_ohlcv_last_nan` -> `list[float]`.
- Added the 12 missing parameter annotations:
  - `test_calculate_sar_trend_is_always_bipolar(self, high: list[float], low: list[float], close: list[float])`
  - `test_signal_matches_trend_reversal(self, high: list[float], low: list[float], close: list[float])`
  - `_ohlcv(self, closes: list[float], volume: Any = None)`
  - `_ohlcv_prev_nan`/`_ohlcv_last_zero`/`_ohlcv_last_nan`/`_ohlcv_no_volume(self, closes: list[float])`
- Added `from typing import Any` (used by `_ohlcv`).
- Ran `black` (wrapped two over-long SAR signatures).

Fixed 27 latent body-checking errors that the new override exposed (they were hidden because the
functions were previously untyped). All fixes are behavior-preserving and prefer real annotations:
- `list[int]` -> `list[float]` invariance at VROC/Donchian call sites: changed `[1_000_000] * 25 + [2_000_000]`,
  `[1_000_000] * 25 + [500_000]`, and `closes = [100] * 10 + [150] * 5` literals to floats.
- `volume = [1000] * 80` -> `[1000.0] * 80` (then `volume[-1] = float("nan")` type-checks).
- Three Choppiness test loops: annotated `closes`/`highs`/`lows` as `list[float] = []` and changed
  `c = 100` -> `c = 100.0` so the float branch assignments type-check.

Appended `[[tool.mypy.overrides]] module = "tests.test_strategies_examples"` /
`disallow_untyped_defs = true` immediately before `[tool.coverage.run]` (now 59 overrides, 0 duplicates).

## What was actually verified (evidence)
- `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental`
  -> only 1 pre-existing error: `tests/test_optimization.py:1542` (list-item). No errors in the migrated file.
- `python3 -m pytest tests/test_strategies_examples.py -p no:cacheprovider -q` -> `556 passed` (identical to baseline).
- `python3 -m ruff check tests/test_strategies_examples.py pyproject.toml` -> `All checks passed!`
- `python3 -m black --check tests/test_strategies_examples.py` -> `1 file would be left unchanged.`
- `git diff --check` -> clean.
- AST re-check: 0 missing return annotations, 0 missing param annotations in the file.

## What remains unresolved (pre-existing / environment, DO NOT "fix" by editing test code)
- `tests/test_optimization.py:1542` list-item error: `DataManager([MockDataProvider(...)])` where
  `DataManager.__init__` expects `list[DataProvider]` (providers.py:530) and `DataProvider` is an ABC
  (providers.py:343). `MockDataProvider` (test_optimization.py:68) is a duck-typed stand-in that does NOT
  subclass `DataProvider` and lacks the abstract `fetch_latest`. This is the ONLY remaining mypy error.
- `test_optimization.py` also has 2 notes (annotation-unchecked) at 4222/4252 (bodies of still-untyped funcs).
- Missing optional dep `matplotlib`; `pandas-stubs>=3.0.0` declared but not installed -> env noise (drives
  `TestHtmlReportFlag` failures in test_cli.py). pandas is treated as `Any` by mypy.
- `black --check pyproject.toml` parse failure (do not run black on the TOML).

## Remaining migration candidates (verified via AST)
- `tests/test_optimization.py`: 211 missing return, 76 params. ONLY remaining file without a mypy override.
  SKIP UNTIL the 1542 list-item error is resolved, or the override will expose many more body errors.

## One precise next task
Migrate `tests/test_optimization.py`, starting by resolving the single blocking error at line 1542.
1. Baseline: `python3 -m pytest tests/test_optimization.py -p no:cacheprovider -q` and
   `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` (confirm only 1542 error).
2. Resolve 1542 with the smallest real fix, e.g. make `MockDataProvider` subclass `DataProvider` and
   implement `fetch_latest` (check providers.py:376+ for abstract methods), OR change the call to satisfy
   the declared type. Do NOT add a blanket `# type: ignore` unless no structural fix is reasonable.
3. Add return annotations (`-> None` for test functions; specific types for value-returning helpers — run
   the AST "has_value_return" check first; do NOT annotate value-returning defs as `-> None`) and the 76
   missing param annotations (watch for nested `if __name__ == "__main__":` defs and pytest fixtures).
4. Append `[[tool.mypy.overrides]] module = "tests.test_optimization"` / `disallow_untyped_defs = true`
   immediately before `[tool.coverage.run]` (expect 60 overrides, 0 duplicates).
5. Verify: mypy -> only pre-existing 1542 (now fixed, so ideally 0 errors); pytest test_optimization.py;
   ruff check tests/test_optimization.py pyproject.toml; black --check tests/test_optimization.py; git diff --check.
Constraints: preserve the working baseline; no unrelated refactors; prefer real annotations over
`# type: ignore`; lines <= 100 chars; leave changes uncommitted.

## Failed or corrected approaches this session
- Adding the `disallow_untyped_defs` override alone is insufficient: mypy then type-checks all now-annotated
  bodies and surfaced 27 pre-existing latent errors (list[int] vs list[float] invariance, int lists assigned
  floats). Fixed by converting literals to float and annotating the accumulator lists; do NOT re-add these
  to the skip list.
- `list` is invariant; `list[int]` is not assignable to `list[float]`. Prefer float literals (or `Sequence`
  in helper signatures) over `# type: ignore`.