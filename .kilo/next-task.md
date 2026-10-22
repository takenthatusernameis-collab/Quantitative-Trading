# Next Task

## What changed

The assigned task was to expose the unrealized PnL of the positions that are
still open explicitly, and to assert the reconciliation identity. The library
part of the task was already done in the repository when this session started
(`BacktestMetrics` had no `unrealized_pnl` field, and `BacktestResult` carried
the open positions but no way to read their mark-to-market PnL). The work of
this session:

1. **`quant_trading/backtest/metrics.py` — `BacktestMetrics` gained an
   explicit `unrealized_pnl` field.**
   - The field is the mark-to-market PnL of the positions that were still open
     when the run ended. Together with `total_pnl` it explains the change of
     the portfolio value:
     `final_value - initial_capital == total_pnl + unrealized_pnl`.
   - It is declared **last** in the dataclass, so the positional order of the
     fields above it is unchanged for callers that build a metrics object
     positionally. Every in-repo construction is keyword based, but the field
     order is public API and was not touched.
   - `to_dict()` reports it under the key `"unrealized_pnl"`.
   - The docstring spells out that the field is **engine-populated**:
     `calculate_backtest_metrics()` sees an equity curve and a trade log, and
     neither of them carries the market value of an open position, so the
     field stays `0.0` when the function is called directly. A run that ended
     with every position closed also reports `0.0`.
2. **`quant_trading/backtest/engine.py` — the engine populates the field.**
   - `BacktestEngine.run()` computes the open positions once
     (`self.portfolio.get_positions()`), sums their `Position.unrealized_pnl`
     and writes it into `metrics.unrealized_pnl`. The engine is the only place
     that knows the open positions, so this is where the number has to come
     from; `calculate_backtest_metrics()` was deliberately left alone.
   - `BacktestResult` gained an `unrealized_pnl` **property** that returns
     `self.metrics.unrealized_pnl`, so the figure is reachable from the result
     as well (`result.unrealized_pnl`). There is a single source of truth (the
     metrics field), and the randomized invariant tests assert that the two
     agree.
   - The class docstring of `BacktestResult` now states the reconciliation
     identity in its bullet list of reconciling facts.
3. **`examples/cli.py` — the single-run output shows the split.**
   - The printed block gained `Realized PnL:` and `Unrealized PnL:` lines
     right below `Total Return:`, so the total return can be read as the sum
     of the two.
   - The JSON output gained the keys `"total_pnl"` and `"unrealized_pnl"`.
4. **`README.md` — a new "Realized and Unrealized PnL" section** right after
   the "Short Selling" section (which is where the reconciliation prose for a
   fully liquidated round trip already lived). It states the identity, points
   at the CLI output and the JSON keys, and warns that
   `calculate_backtest_metrics()` cannot derive the figure on its own. The
   Quick Start snippet also prints the new field.
5. **Tests** (7 new tests, plus the shared invariant helper):
   - `tests/test_cost_accounting_invariants.py`: the shared helper
     `_assert_cost_accounting_invariants()` gained invariant 8 — the metrics
     report the unrealized PnL of the open positions and the two halves
     reconcile — so it now runs over all ~70 randomized scenarios
     (round trips, partial exits, add-to-position, multiple symbols, rejected
     signals, short round trips, open shorts).
   - `tests/test_cost_accounting_invariants.py::test_the_metrics_report_the_unrealized_pnl_of_the_open_positions`
     — a run that ends with **an open long and an open short**.
   - `tests/test_cost_accounting_invariants.py::test_a_fully_liquidated_run_reports_no_unrealized_pnl`
     — a fully closed run reports `0.0`.
   - `tests/test_backtest_metrics.py::TestBacktestMetricsUnrealizedPnl` — the
     default is `0.0`, the field is in `to_dict()`, and a direct call of
     `calculate_backtest_metrics()` leaves it at `0.0`.
   - `tests/test_cli.py::TestUnrealizedPnlReporting` — the printed block
     reports both halves, and the JSON output reconciles to the total return.
   - `tests/test_cli.py`: the three CLI tests that mock the metrics
     (`MagicMock()` with only the printed attributes set) now also set
     `total_pnl` and `unrealized_pnl` to `0.0`. This is a mechanical
     consequence of the two new printed lines, not a weakening of an
     assertion.

## What was actually verified

- **Baseline before any change**: `python3 -m pytest -q` ->
  `1913 passed, 1 skipped`. The tree was green.
- **After the change**: `python3 -m pytest -q` -> **`1920 passed, 1 skipped,
  0 failed`** (7 new tests).
- `python3 -m ruff check .` -> All checks passed.
- `python3 -m black --check .` -> 91 files unchanged.
- `python3 -m mypy quant_trading examples` -> no issues found in 56 source
  files.
- **The new tests fail against the pre-change source.** The two source files
  were restored from `HEAD` (the test files were kept) and the new tests were
  re-run: all 5 library tests failed with
  `AttributeError: 'BacktestMetrics' object has no attribute 'unrealized_pnl'`
  (4x) and
  `TypeError: BacktestMetrics.__init__() got an unexpected keyword argument
  'unrealized_pnl'` (1x). The two CLI tests fail on the pre-change source
  because the printed lines and the JSON keys do not exist there.
- **The identity was measured, not assumed.** A scratch script drove the
  engine through six scenarios and compared
  `final_value - initial_capital` with
  `metrics.total_pnl + metrics.unrealized_pnl`:
  open long only, open short only, open long + open short, partial long +
  open short, fully liquidated long, fully liquidated short. The residual was
  at most `2.3e-13` in every case (float noise).
- `metrics.total_pnl` was measured to be **exactly** the sum of the raw trade
  log `pnl` column in every scenario (the `split_trade_log()` "entries" sum),
  so the metrics field and the trade log agree.
- `metrics.unrealized_pnl` was measured to be exactly the sum of
  `Position.unrealized_pnl` of the open positions, which is the sum of
  `Holding.unrealized_pnl` of the same positions (`Holding.to_position()`
  copies the figure).
- **End-to-end CLI**: `PYTHONPATH=. python3 examples/cli.py --offline
  --symbols AAPL --days 120 --output /tmp/cli_out.json` prints
  `Total Return:    $12.08 (0.01%)`, `Realized PnL:    $0.45` and
  `Unrealized PnL:  $11.63`; the JSON carries `total_return =
  12.077983863971895`, `total_pnl = 0.4493655360112796` and
  `unrealized_pnl = 11.628618327961107`, which add up to the total return
  exactly.

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
- **The combined mode of the CLI does not report the split.** It prints a
  comparison table and writes per-strategy JSON entries; neither was changed
  (see "approaches that already failed" for the concrete blocker). The
  library values are available to a caller of `run_combined()`.
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.
- **The repository integrity guard still does not cover `examples/`** — this
  is the next task.

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

**Extend the repository integrity guard to the `examples/` tree.**

Evidence:

- `tests/test_repository_integrity.py:25` scans
  `SOURCE_DIRS = ("quant_trading", "tests")` only. The guard exists because
  this repository has repeatedly been broken by a patch that was applied
  twice (a duplicated keyword argument made the package unimportable, a
  duplicated dataclass field silently overrode the earlier default, and a
  duplicated test function was never collected — that last one was the
  failing test the previous session found in this repository).
- `examples/cli.py` is **2027 lines** and is exactly the kind of file that
  guard was written for; the previous session's handoff already flagged the
  missing `examples/` coverage as "a hardening opportunity rather than a
  live bug".
- The `examples/` tree is **currently clean**: a scan with the same AST rules
  the guard uses over `examples/**/*.py` (19 files) found **0** duplicate
  module-level definitions and **0** duplicate class members or annotated
  fields, and every file compiles. So this task is a guard, not a bug fix.

Bounded scope:

1. Cover `examples/` in `tests/test_repository_integrity.py`. The cheapest
   form is to add `"examples"` to `SOURCE_DIRS`; the alternative is a second
   list so that the package-specific checks keep their current meaning. The
   checks must stay **AST based** — the example modules have import-time side
   effects and must not be imported by the guard.
2. Keep the guard cheap: it already parses every file, and 19 more files add
   no measurable time.
3. **Prove the new coverage works**: temporarily duplicate a function
   definition inside an `examples/` file, confirm the guard fails, and revert
   the temporary change. A guard that has never been shown to fail is not
   evidence. Record the observed failure in the handoff.
4. If the scan over `examples/` turns out to have real offenders (it did not
   in this session), fix them instead of just guarding them.

Constraints: do not change the semantics of the existing checks; do not
import the example modules; keep the public API of the guard unchanged
(it is a test module, so only its own helpers are at stake); run
`python3 -m pytest -q`, `python3 -m ruff check .`, `python3 -m black --check .`
and `python3 -m mypy quant_trading examples` before handing off, and confirm
the new check fails against a deliberately broken tree.
