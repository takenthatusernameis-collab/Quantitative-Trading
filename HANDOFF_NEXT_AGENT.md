## Status

Verified green on 2026-11-18, after closing the last two coverage gaps in
`quant_trading/risk/metrics.py`.

## What changed

Both previously-uncovered lines in `quant_trading/risk/metrics.py` were
probed empirically and found **reachable** — they are NOT dead code. Added
regression tests in `tests/test_risk_metrics.py`:

- `test_all_infinite_equity_reports_neutral_drawdown` and
  `test_zero_then_infinite_reports_neutral_drawdown` — hit
  `metrics.py:217` (`return 0.0` when every drawdown ratio is non-finite
  after `.replace([inf, -inf], nan).dropna()`). Triggered by equity curves
  whose values are all `inf`, or a zero running peak followed by `inf`.
- `test_overflow_drawdown_reports_neutral_ulcer_index` and
  `test_extreme_negative_drawdown_reports_neutral_ulcer_index` — hit
  `metrics.py:1107` (`return 0.0` when `not np.isfinite(ulcer)`). Triggered
  by a ~1e155 drawdown (squared drawdown overflows to `inf`) and a drop to
  `-1e200` from a finite peak.

No production code was modified; the guards are load-bearing and correctly
return `0.0` for these pathological-but-valid inputs.

Commit: `dfef90f`.

## Environment note (important for the next runner)

The runner environment is reset between sessions and starts with no numpy,
pandas, pytest, mypy, black, ruff, matplotlib or scikit-optimize. Reinstall
before verification:

```bash
python -m pip install "pandas>=2.0.0" "numpy>=1.24.0" "yfinance>=0.2.0" \
  "pytest>=7.0.0" "black>=26.0.0,<27" "ruff>=0.1.0" "mypy>=1.0.0" \
  "pandas-stubs>=3.0.0" "types-requests" "types-PyYAML" \
  "matplotlib>=3.7.0" "scikit-optimize>=0.10.0" "coverage>=7.6"
```

Without matplotlib/scikit-optimize about 111 tests skip; install them so the
full suite actually runs.

## What was actually verified

- `MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider`
  -> **4111 passed, 142 deselected, 0 skipped** (5m15s).
- `python -m mypy quant_trading examples tests` -> **no issues in 162 files**.
- `python -m black --check` and `python -m ruff check` on
  `tests/test_risk_metrics.py` -> clean.
- `COVERAGE_CORE=sysmon python -m coverage run --source=quant_trading -m pytest ...`
  -> **TOTAL 100%** (8880 stmts, 0 miss, 3130 branches, 0 partial),
  `quant_trading/risk/metrics.py` **100%** (273 stmts, 0 miss).

## Remaining work / unresolved

None. The entire `quant_trading` package is at 100% coverage, the mypy gate
is clean, and the full suite is green.

## One precise next task

The repository is in a fully-green, fully-covered state. The next bounded,
high-value task should be chosen from the product backlog (e.g. a new
indicator in `quant_trading/indicators/`, a strategy in
`quant_trading/strategies/`, or an example in `examples/`), implemented
with tests, and verified with the same gates:
`MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider`,
`python -m mypy quant_trading examples tests`,
`COVERAGE_CORE=sysmon python -m coverage run --source=quant_trading -m pytest ...`,
plus `black --check` and `ruff check` on changed files.