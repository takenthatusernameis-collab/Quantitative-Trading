## Status

Verified green on 2026-11-18, after fixing a real regression and closing the
last coverage gap in the reporting module.

## What changed

- `quant_trading/backtest/report.py`: added `typing.cast(pd.Series, ...)` to the
  return values of `_drawdown_series` (line ~213) and `_finite_series` (line
  ~234). Newer pandas-stubs types `Series.replace(...).fillna/dropna` as `Any`,
  so `mypy` reported two `no-any-return` errors and
  `tests/test_repository_integrity.py::test_repository_is_mypy_clean` failed.
  Behaviour is unchanged; this is a typing-only fix.
- `tests/test_backtest_report.py`: added
  `test_rolling_sharpe_chart_empty_after_dropna` and
  `test_rolling_volatility_chart_empty_after_dropna`, mirroring the existing
  comparison-chart tests. These cover the previously-uncovered fallback
  branches at `report.py` ~499-512 and ~570-583.

Commits: `829bd85` (mypy fix), `7a9fc1f` (chart fallback tests).

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
  -> **4107 passed, 142 deselected, 0 skipped** (5m08s).
- `python -m mypy quant_trading examples tests` -> **no issues in 162 files**.
- `python -m black --check` and `python -m ruff check` on both changed files
  -> clean.
- Coverage now works with a different core:
  `COVERAGE_CORE=sysmon python -m coverage run --source=quant_trading -m pytest ...`
  -> **99% total**, `quant_trading/backtest/report.py` **100%**.
  The old `pytest --cov` / default coverage core failure on Python 3.14
  ("cannot load module more than once per process") is avoided by
  `COVERAGE_CORE=sysmon`; use that, do not repeat the default invocation.

## Remaining work / unresolved

Only two uncovered statements remain in the whole package
(`COVERAGE_CORE=sysmon python -m coverage report -m --skip-covered`):

- `quant_trading/risk/metrics.py:217` — `return 0.0` after
  `calculate_max_drawdown` drops all non-finite drawdowns. If
  `running_max.max() > 0`, the point at the running max has equity equal to the
  peak and a finite 0 drawdown, so this line looks unreachable for any real
  input; it may be dead defensive code.
- `quant_trading/risk/metrics.py:1107` — `return 0.0` when
  `not np.isfinite(ulcer)`. `drawdown` is already finite and non-empty at that
  point, so this is also likely unreachable.

Do not delete these guards blindly; they encode "never return NaN/inf to a
caller" invariants.

## One precise next task

Determine empirically whether `quant_trading/risk/metrics.py:217` and `:1107`
are reachable with a pathological but valid equity curve (e.g. `Series` of
length > 0 whose running max is positive but whose drawdown becomes non-finite,
or extreme magnitudes near float overflow). Write a short script under
`/home/runner/work/_temp/kilo-tmp/` to probe both. If a reachable input exists,
add a regression test in `tests/test_risk_metrics.py`; if not, mark exactly
those two lines `# pragma: no cover` with a one-line justification and confirm
`COVERAGE_CORE=sysmon ... coverage report -m` shows the file at 100%. Verify
with the full suite and the mypy gate from `tests/test_repository_integrity.py`.
