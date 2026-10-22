# Next Task

## Repository state

Checks: `python -m pytest -q` (2016 passed, 0 failed), `python -m ruff check .` (clean), `python -m black --check .` (clean), `python -m mypy quant_trading` (clean, 37 files), `python -m mypy --explicit-package-bases examples` (clean, 19 files).

## Completed this session

Fixed a documentation/code mismatch in `examples/cli.py`: the README documents `--interval` values such as `monthly_adjusted`, `quote`, `market_status`, `fx_daily`, `fx_5m`, `crypto_daily`, `sector`, `sma`, `gold` as valid CLI values (Alpha Vantage provider), but `cli.py`'s `_is_supported_interval` rejected them with `invalid --interval` before the run ever started.

Changes:
- `examples/cli.py`: import `AlphaVantageProvider` from `quant_trading.data.yfinance_provider` and build `ALPHAVANTAGE_INTERVALS`, a frozenset union of every interval alias the provider accepts, so the CLI accepts exactly what the provider supports and stays in sync with it.
- `examples/cli.py`: `_is_supported_interval` now returns `True` for any `ALPHAVANTAGE_INTERVALS` value (in addition to `INTERVAL_PERIODS_PER_YEAR` keys and `m`/`h` intraday forms). Truly unknown values like `3x` are still rejected.
- `examples/cli.py`: added `monthly_adjusted: 12` to `INTERVAL_PERIODS_PER_YEAR`, so `--interval monthly_adjusted` annualizes as monthly (12 periods/year) instead of falling back to the daily default of 252.
- `tests/test_cli.py`: added `TestIsSupportedInterval` (parametrized over the documented intervals + rejection of `3x`/`""`/`None`) and `test_monthly_adjusted_annualizes_as_monthly` in `TestResolvePeriodsPerYear`.
- `tests/test_examples_smoke.py`: added `test_cli_accepts_a_documented_alphavantage_interval_without_a_traceback` (offline run with `--interval monthly_adjusted` must exit 0 with no traceback).

## What was actually verified

- `python -m pytest -q`: 2016 passed, 0 failed (baseline was 1998; +16 new tests).
- `python -m ruff check .`: clean (auto-fixed import ordering in test_cli.py).
- `python -m black --check examples/cli.py tests/test_cli.py tests/test_examples_smoke.py`: clean.
- `python -m mypy quant_trading`: clean, 37 files. `python -m mypy --explicit-package-bases examples`: clean, 19 files (note: `mypy quant_trading examples` without `--explicit-package-bases` reports a pre-existing "source file found twice" artifact for `examples/cli.py` because `examples/` has no `__init__.py`; unrelated to this change).
- Manually confirmed `--interval monthly_adjusted`/`quote`/etc. no longer produce `invalid --interval`, `3x` is still rejected, `resolve_periods_per_year("monthly_adjusted") == 12`, and `examples/cli.py --offline --interval monthly_adjusted` exits 0.

## What remains unresolved

None for this task. Repository is in a complete, verified state.

## Approaches that already failed

None — the first approach (widen interval acceptance to the provider's interval set, derived from `AlphaVantageProvider`) worked on the first try.

## One precise next task

None outstanding. The next session may start a new bounded task (e.g. from the issue backlog) or report the repo as complete.
