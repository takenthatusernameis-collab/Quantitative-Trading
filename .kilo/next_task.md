# Next Task: (HANDOFF)

## Status

IN_PROGRESS - Repository is clean with all tests passing and 100% coverage; one bounded improvement added this session.

## What this session did

- Selected Option 1 from the prior handoff: an end-to-end integration test for the CLI `--combined` mode (previously only tested with mocked `run_backtest`).
- Added 2 tests to `tests/test_cli.py::TestRunCombined`:
  - `test_main_offline_combined_end_to_end` — runs `main(["--offline","--combined","--symbols","AAPL","--days","120"])` with no mocks and asserts all 13 strategies run, the comparison table prints, and "Best strategy (by Sharpe)" appears.
  - `test_main_offline_combined_with_output` — same run with `--output` and asserts the JSON comparison file is written with `comparison` and `best_strategy` keys.
- Verified `--combined` runs end-to-end against synthetic data in ~4.5s, all 13 strategies succeed.

## What was verified

- `python -m pytest tests/test_cli.py -q` → 81 passed (79 before + 2 new).
- `python -m pytest -q` (full suite) → 1053 passed, 1 skipped, 13 warnings (143s).
- `python -m ruff check tests/test_cli.py` → All checks passed.
- `python -m black --check tests/test_cli.py` → 1 file unchanged.
- `python -m mypy tests/test_cli.py --ignore-missing-imports` → 3 errors, all pre-existing inline-mock `generate_signals` overrides in `TestFactoryIntegration` (confirmed identical on the clean committed tree via `git stash`); no new issues introduced.

## What remains unresolved

- Nothing from this session. Coverage config (`pyproject.toml` `source = ["quant_trating"]`) excludes `examples/`, so the new CLI tests add integration value but do not affect the 100% package coverage figure.

## Approaches that failed

- None.

## Next precise task

Add tests for regime-detection edge cases in `quant_trading/regime/detector.py`:
- Short series where `window > len(prices)` → rolling stats all NaN → `_label_series` returns all `None` → empty `RegimeResult` (detector.py:108-113, 167-169, 191-192).
- Constant / flat price series → zero returns → vol = 0 → single SIDEWAYS_LOW_VOL segment (detector.py:115-116, 227-232).
- Monotonic trending series → single BULL_ or BEAR_ segment (single-regime curve).
- Explicit `vol_threshold`/`return_threshold` override vs auto-derived (detector.py:119-124).

Suggested test file: extend `tests/test_regime.py` (check existing conventions there first). Keep each test bounded and deterministic (seeded or hard-coded `pd.Series`, no network).

Constraints: do not modify `detector.py` behavior unless a genuine bug is found; only add tests. Preserve 100% coverage, clean ruff/black/mypy (modulo pre-existing test-file mypy overrides).