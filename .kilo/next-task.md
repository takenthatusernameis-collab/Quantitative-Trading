# Next Task

## This session

The assigned task was to extend the repository integrity guard to the
`examples/` tree. It was completed, and the natural follow-on — the combined
CLI mode still did not report the realized/unrealized PnL split — was taken as
well.

1. **`tests/test_repository_integrity.py` — the guard now covers `examples/`.**
   - `SOURCE_DIRS` changed from `("quant_trading", "tests")` to
     `("quant_trading", "examples", "tests")` (line 25). The three existing
     checks (`test_all_source_files_parse`, `test_no_duplicate_module_level_definitions`,
     `test_no_duplicate_methods_or_class_fields`) now scan 19 more files over
     `examples/**/*.py`.
   - The checks stay **AST based** — the example modules have import-time side
     effects and are still not imported by the guard; `test_all_package_modules_import()`
     walks only `quant_trading.__path__` and is unchanged.
   - **The new coverage was proven to fail on a deliberately broken tree.**
     A second `def main()` was appended to `examples/run_aroon.py` and the
     guard failed with:
     ```
     AssertionError: duplicate module-level definitions:
       examples/run_aroon.py: main defined at lines [42, 65]
     ```
     The change was reverted immediately. The `examples/` tree is clean: 0
     duplicate module-level definitions, 0 duplicate class members or annotated
     fields, and every file compiles.
2. **`examples/cli.py` — `run_combined()` now reports the split.**
   - Every `comparison` entry gained `total_return`, `total_pnl` and
     `unrealized_pnl` (the single-run path already wrote the last two), so the
     reconciliation identity can be read from a combined output file too.
   - The combined `json.dump` switched from `json.dump(output_data, f, indent=2)`
     to `json.dump(output_data, f, indent=2, default=str)`, matching the
     single-run path, so the new floats serialize even when a metrics object is
     not a plain float.
3. **`tests/test_cli.py` — the three `MagicMock(spec=BacktestMetrics)` metrics
   gained `total_pnl = 0.0` and `unrealized_pnl = 0.0`** (lines 1469, 1585,
   2053). A mechanical consequence of the two new JSON keys, not a weakening of
   an assertion.
4. **`tests/test_cli.py::test_main_offline_combined_with_output`** now asserts
   that every comparison entry carries `total_pnl`, `unrealized_pnl` and
   `total_return`, and that `total_return == total_pnl + unrealized_pnl` for
   each.
5. **`README.md`** — the "Realized and Unrealized PnL" section now notes that
   the same keys are present in every strategy entry of a combined run.

## What was actually verified

- **Baseline before any change**: `python3 -m pytest -q` ->
  `1920 passed, 1 skipped`. The tree was green.
- **After the change**: `python3 -m pytest -q` -> **`1920 passed, 1 skipped,
  0 failed`** (the new combined-mode assertion is folded into an existing test,
  so the count is unchanged; the guard's 4 tests still pass).
- `python3 -m ruff check .` -> All checks passed.
- `python3 -m black --check .` -> 91 files unchanged.
- `python3 -m mypy quant_trading examples` -> no issues found in 56 source
  files.
- **The guard was shown to fail on a deliberately broken tree.** A second
  `def main()` was appended to `examples/run_aroon.py` and the guard failed
  with `duplicate module-level definitions: examples/run_aroon.py: main
  defined at lines [42, 65]`. The change was reverted.
- **The combined identity was measured, not assumed.** An end-to-end
  `--offline --combined --symbols AAPL --days 120 --output
  /tmp/combined_out.json` run wrote 14 strategy entries; every one carried
  `total_pnl` and `unrealized_pnl`, and `total_return - (total_pnl +
  unrealized_pnl)` was at most `9e-12` in every case (float noise). Entries
  that ended fully closed (SuperTrend, Aroon, Parabolic_SAR, Momentum) reported
  `unrealized_pnl = 0.0` exactly, as expected.

## What remains unresolved

- **`analyze_trades(periods_per_year=...)` is still not wired to the run, and
  the semantics are genuinely ambiguous — unchanged, deliberately.** The
  trade-level Sharpe and Sortino are computed on the **per-trade** return
  series, so the value of `periods_per_year` there means "how many *trades*
  per year" (see the docstring at
  `quant_trading/backtest/trade_analysis.py:466-491`), not "how many *bars*
  per year". Forwarding the bar frequency from the config would be an
  approximation that conflates the two. A decision is needed on what the
  framework means by the parameter here; it is not a mechanical fix.
- **`TradeAnalysis.open_position_pnl` and the new
  `BacktestMetrics.unrealized_pnl` are different numbers and the names are
  close.** `open_position_pnl` is the part of the *realized* PnL that the
  positions which are still open booked (the entry fee of the shorts that were
  never covered) — it is already inside `total_pnl`. `unrealized_pnl` is the
  mark-to-market value of the open positions. Both are documented in the
  metrics docstring and in the README, but the confusion is still possible.
  Renaming either is a breaking change and was not attempted.
- **`calculate_backtest_metrics()` called directly reports `0.0` for the
  unrealized PnL even when the run had open positions.** This is documented
  in the field docstring, in the README and in a dedicated test, but a caller
  that rebuilds the metrics from `result.equity_curve` and `result.trades`
  still gets a `0.0` that is not the truth. The alternatives (an optional
  `unrealized_pnl=` argument, or `None` for "unknown") were considered and
  rejected to keep the field a plain float with a documented default; the
  decision can be revisited.
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.

## Approaches that already failed

- **Adding the two CLI print lines broke three existing CLI tests**

- **`analyze_trades(periods_per_year=...)` is still not wired to the run, and
  the semantics are genuinely ambiguous — unchanged, deliberately.** The
  trade-level Sharpe and Sortino are computed on the **per-trade** return
  series, so the value of `periods_per_year` there means "how many *trades*
  per year" (see the docstring at
  `quant_trading/backtest/trade_analysis.py:466-491`), not "how many *bars*
  per year". Forwarding the bar frequency from the config would be an
  approximation that conflates the two. A decision is needed on what the
  framework means by the parameter here; it is not a mechanical fix.
`unrealized_pnl` is the mark-to-market value of the open positions. Both are
  documented in the metrics docstring and in the README, but the confusion is
  still possible. Renaming either is a breaking change and was not attempted.
- **`calculate_backtest_metrics()` called directly reports `0.0` for the
  unrealized PnL even when the run had open positions.** This is documented
  in the field docstring, in the README and in a dedicated test, but a caller
  that rebuilds the metrics from `result.equity_curve` and `result.trades`
  still gets a `0.0` that is not the truth. The alternatives (an optional
  `unrealized_pnl=` argument, or `None` for "unknown") were considered and
  rejected to keep the field a plain float with a documented default; the
  decision can be revisited.
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.

## Approaches that already failed

- **Adding the two CLI print lines broke three existing CLI tests**
  (`TestConfigFileEndToEnd::test_main_with_a_config_file_uses_the_limit_of_the_file`,
  `TestIntervalEndToEnd::test_main_uses_the_interval_of_the_config_file`,
  `TestIntervalEndToEnd::test_main_lets_the_flag_override_the_interval`).
  They build `MagicMock()` metrics and set only the attributes the CLI
  prints, so the two new attributes were MagicMocks and
  `f"{mock:.2f}"` raised
  `TypeError: unsupported format string passed to MagicMock.__format__`.
  Fixed by setting `total_pnl` and `unrealized_pnl` on those three mocks —
  the alternative (not printing the new fields) would have thrown the feature
  away.
- **`MagicMock(spec=BacktestMetrics).unrealized_pnl` returns a child
  MagicMock, not the class default `0.0`.** A `spec` only restricts *which*
  attributes exist; it does not copy their values. So a spec'd metrics mock
  cannot be formatted either.
- **The combined mode was deliberately left alone because of that mock.** Its
  JSON is written with `json.dump(output_data, f, indent=2)` — **without**
  `default=str` — while the single-run path uses
  `json.dump(output_data, f, indent=2, default=str)`. The two existing
  combined-mode tests use `MagicMock(spec=BacktestMetrics)` metrics, so
  adding `result.metrics.total_pnl` to the comparison entries would raise
  `TypeError: Object of type MagicMock is not JSON serializable` unless the
  mocks are changed. That is a separate, small change; it was left out to
  keep this change bounded.
- **A `BacktestResult.unrealized_pnl` property derived from `self.positions`
  was rejected** in favour of delegating to `self.metrics.unrealized_pnl`:
  two independently computed copies of the same number can drift apart for a
  hand-built result. The metrics field is the single source of truth, and the
  randomized invariant tests assert that the result property and the metrics
  field agree.
- **Inserting the new dataclass field next to `total_pnl` was rejected** even
  though that reads better: the dataclass fields are the positional
  arguments of `BacktestMetrics.__init__`, and inserting a field in the
  middle would silently change the meaning of `BacktestMetrics(1000.0,
  500.0, 1.5)`. The field is declared last instead.


## Next task

**There is no further task assigned.** Both items outstanding at the start of
this session — the repository integrity guard covering `examples/` and the
combined CLI mode reporting the realized/unrealized PnL split — are done. The
remaining items in "What remains unresolved" are genuinely open decisions, not
assigned work.
