# Next Task

## What changed

The assigned task was to thread `periods_per_year` through the regime entry
points. The **library** part of that task was already done in the repository
when this session started (`detect_regimes()`, `analyze_regimes()` and
`regime_for_backtest()` all accepted `periods_per_year` and passed it to
`RegimeDetector`). What was still missing was the last mile, and the session
found a **failing test** on the way in. Four things were changed.

1. **Fixed the failing repository-integrity test** (this was the concrete
   blocker in the tree).
   - `tests/test_backtest_analysis.py` defined
     `test_analyze_regimes_periods_per_year_affects_volatility` **twice**
     (lines 227 and 271) and
     `test_regime_for_backtest_periods_per_year_affects_volatility` **twice**
     (lines 249 and 291). The second definition shadows the first, so half of
     the regime annualization tests were never collected or executed.
     `tests/test_repository_integrity.py::test_no_duplicate_module_level_definitions`
     caught this and **failed**: the baseline suite was
     `1 failed, 1894 passed, 1 skipped`.
   - The duplicated pair was replaced by a single, stronger pair that uses the
     file's existing `_make_result()` fixture and asserts the exact
     `sqrt(periods_per_year)` scaling instead of a mere inequality. Four new
     tests were added: the two scaling tests, an auto-threshold label
     invariance test, an explicit-threshold test, and a test that the analysis
     records the annualization it used. The now-unused `BacktestMetrics`
     import was removed.
2. **`examples/cli.py` — the regime analysis now uses the period count of the
   run.** `_get_regime_analysis()` gained a `periods_per_year: int = 252`
   argument and the caller passes `config.backtest.periods_per_year`. Before
   this, the CLI annualized every regime label at 252 while the backtest
   metrics, the Monte Carlo simulation and the optimizers all honoured the
   configured frequency, so a weekly run reported a regime volatility that was
   off by the square root of the frequency ratio. The printed block and the
   JSON output now report the annualization factor (`Periods per Year:` and
   `regime_analysis["periods_per_year"]`).
3. **`quant_trading/backtest/analysis.py` — `BacktestRegimeAnalysis` records
   the annualization.** The dataclass gained a `periods_per_year: int = 252`
   field, which `analyze_regimes()` fills in, and the field is reported in
   `summary()` and `to_dict()`. The public defaults are unchanged.
4. **Two adjacent gaps of exactly the same class were found and fixed**
   (see "What remains unresolved" for the one that was deliberately *not*
   fixed):
   - `examples/cli.py::_get_trade_analysis()` now forwards
     `config.backtest.risk_free_rate` to `analyze_trades()`. Before this the
     CLI's trade-level Sharpe and Sortino were always computed with the
     library default of `0.02`, so `--risk-free-rate 0.05` moved the backtest
     Sharpe but left the trade Sharpe untouched.
   - `examples/cli.py::run_combined()` silently ignored `--regime`,
     `--monte-carlo` and `--trade-analysis`. Combined mode runs one backtest
     per strategy and has no combined equity curve, so the analyses are now
     reported for the **best strategy** of the comparison (the one the table
     already announces) and are written to the JSON output under the same
     keys a single run uses. The flags are read with `getattr(args, ..., False)`
     because `run_combined()` is also called directly with hand-built
     `argparse.Namespace` objects in the existing tests.

Also updated: `examples/run_analysis.py` (threads `config.periods_per_year`
into the backtest, the regime analysis and the Monte Carlo simulation) and
`README.md` (a new "Regime Annualization" subsection, the combined-mode
analysis behaviour, the trade-analysis risk-free rate, and
`analyze_regimes`/`regime_for_backtest` in the list of layers that accept
`periods_per_year`).

## What was actually verified

- **Baseline before any change**: `python3 -m pytest -q` ->
  `1 failed, 1894 passed, 1 skipped`. The failure was
  `tests/test_repository_integrity.py::test_no_duplicate_module_level_definitions`
  reporting the two duplicated test names.
- **After the change**: `python3 -m pytest -q` -> **`1913 passed, 1 skipped,
  0 failed`** (19 new tests, 1 previously failing test fixed).
- `python3 -m ruff check .` -> All checks passed.
- `python3 -m black --check .` -> 91 files unchanged.
- `python3 -m mypy quant_trading` -> no issues found in 37 source files.
- **Every new test was confirmed to fail against the pre-change source** by
  stashing only `quant_trading/backtest/analysis.py` and `examples/cli.py`
  and re-running:
  - the 5 new `TestRegimePeriodsPerYear` tests (2 x `TypeError:
    _get_regime_analysis() got an unexpected keyword argument`, 2 x missing
    `Periods per Year:` in the output, 1 x `KeyError: 'periods_per_year'` in
    the JSON);
  - `test_backtest_regime_analysis_records_periods_per_year` (`AttributeError:
    'BacktestRegimeAnalysis' object has no attribute 'periods_per_year'`);
  - the 3 new `TestTradeAnalysisRiskFreeRate` tests (2 x `TypeError` on the
    new keyword, 1 x `assert -34.61 != -34.61` — the pre-change CLI produced
    the **same** trade Sharpe for two different risk-free rates);
  - 3 of the 4 new `TestCombinedAnalysis` tests (the fourth is the control
    that asserts the analysis blocks are *absent* without the flags, so it
    passes both before and after).
- **Behavioural facts were measured, not assumed** (script over a 300-bar
  seeded random walk and over the test fixtures):
  - the annualized regime volatility scales by exactly `sqrt(ppy)`
    (0.181868 / 0.082615 = 2.201398 = `sqrt(252/52)`);
  - with **auto-derived** thresholds the labels are **invariant** to
    `periods_per_year` (the threshold is the mean of the very statistic it is
    compared against, and both are scaled by the same factor) — 68 identical
    segments for ppy 252, 52 and 12;
  - with an **explicit** threshold the labels **do** follow the period count
    (68 -> 60 -> 56 -> 9 segments for ppy 252, 52, 12, 12), because an
    explicit threshold is a fixed number in annualized units.
- **End-to-end CLI**: `PYTHONPATH=. python3 examples/cli.py --offline --regime
  --periods-per-year {252,52} --symbols AAPL --days 120 --output ...` ->
  the JSON reports `total_volatility` 0.00020570703 (252) vs
  0.0000934438 (52); the ratio is 2.201398157116029 = `sqrt(252/52)`.
- **End-to-end CLI**: `--combined --offline --regime --monte-carlo
  --trade-analysis` now prints all three analysis blocks and
  `Analysis of the best strategy: Aroon_25`; the JSON carries
  `regime_analysis`, `monte_carlo` and `trade_analysis` next to
  `best_strategy`.
- `PYTHONPATH=. python3 examples/run_analysis.py` runs and prints
  `Periods per Year:  252`.
- The `examples/` tree was scanned with the same AST rule the integrity test
  uses: **no duplicate module-level definitions** in `examples/` either.

## What remains unresolved

- **`analyze_trades(periods_per_year=...)` is still not wired to the run, and
  the semantics are genuinely ambiguous — deliberately not changed.** The
  trade-level Sharpe and Sortino are computed on the **per-trade** return
  series, so the value of `periods_per_year` there means "how many *trades*
  per year" (see the docstring at
  `quant_trading/backtest/trade_analysis.py:466-491`), not "how many *bars*
  per year". Forwarding the bar frequency from the config would be an
  approximation that conflates the two. A decision is needed on what the
  framework means by the parameter here; it is not a mechanical fix.
- **The long-side entry fee "asymmetry" in `split_trade_log()` is NOT a bug —
  closed after two sessions of carry-over.** The previous handoff listed it as
  an open item. Evidence: the engine capitalizes a long entry fee into
  `Holding.avg_cost` and books `0.0` realized PnL on the long entry row, so
  there is nothing to fold. Measured on a real run: **0** `buy` rows with a
  nonzero `pnl`, and the `sell` rows' PnL already equals the whole trade log's
  PnL (4.726498 = 4.726498). The short side *must* fold its entry fee into
  the cover because a short keeps its raw execution price as its cost basis.
  The two sides are mirror images, and `split_trade_log()` is correct. No
  change is needed; this item is now closed.
- **`total_pnl` is realized, `total_return` includes unrealized PnL.** The
  engine invariant `final_value - initial_capital == sum(trades["pnl"]) +
  unrealized_pnl` holds (measured: 39.17651702 == 4.72649812 + 34.45001890,
  and the per-position unrealized PnL sums to the same 34.45001890:
  -44.84929466 + 79.29931356). But `BacktestResult` exposes no explicit
  realized/unrealized split field, so the split is only reachable by manual
  subtraction. This is the next task.
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.
- **The repository integrity guard does not cover `examples/`.**
  `tests/test_repository_integrity.py` scans `SOURCE_DIRS = ("quant_trading",
  "tests")` only, while `examples/cli.py` is ~2000 lines and is exactly the
  kind of file this guard was written for (the repo has repeatedly been bitten
  by double-applied patches). The tree is currently clean, so this is a
  hardening opportunity rather than a live bug.

## Approaches that already failed

- **Assuming the assigned task was undone.** The handoff said
  `detect_regimes()` did not expose `periods_per_year`; the repository already
  had it at `quant_trading/regime/detector.py:584`. The next agent should
  **verify the current state of a file before trusting a handoff claim about
  it** — the handoff described the intended change, not necessarily the
  state of the tree.
- **Narrow `--cov` targets on submodules** can fail under coverage import
  hooks in some environments — measure with package-wide `--cov=quant_trading`.
- **Missing deps in a fresh env** (pandas/numpy/pytest/scikit-optimize/
  yfinance) cause import failures; `pip install -e ".[dev]"` is needed first.
  The scripts land in `~/.local/bin`, which is not on `PATH`, so the tools have
  to be invoked as `python3 -m ruff` / `python3 -m black` / `python3 -m mypy`.
- **`examples/cli.py` cannot be run as `python3 examples/cli.py`**; it needs
  `PYTHONPATH=.` from the repository root.
- **Reading `args.regime` directly inside `run_combined()` broke three
  existing tests** that build `argparse.Namespace` objects by hand
  (`TestRunCombined`, `TestFactoryIntegration`). Use
  `getattr(args, "regime", False)` there, the way the function already reads
  the strategy-specific arguments.
- **An earlier attempt asserted that consecutive out-of-sample periods are
  *contiguous*** in the walk-forward optimizer. That is wrong for a
  walk-forward: the in-sample span of a later fold sits between two
  out-of-sample spans. The correct invariant is "disjoint and chronological".

## Next task

**Expose the unrealized PnL of the open positions explicitly, and assert the
reconciliation identity.**

Evidence:

- The engine already knows both halves: `BacktestResult` is built at
  `quant_trading/backtest/engine.py:539-552` and carries
  `positions=self.portfolio.get_positions()`; every `Position` exposes
  `unrealized_pnl` (`quant_trading/strategies/base.py:117`).
- The identity holds on a real run: `final_value - initial_capital ==
  sum(trades["pnl"]) + unrealized_pnl` (39.17651702 == 4.72649812 +
  34.45001890, with the per-position unrealized PnL summing to the same
  34.45001890: -44.84929466 + 79.29931356).
- `BacktestMetrics.total_pnl` is the **realized** PnL (sum of the trade log)
  while `BacktestMetrics.total_return` **includes** the unrealized PnL of the
  positions that are still open
  (`quant_trading/backtest/metrics.py:47-53`). The two are documented as
  different numbers, but the difference is only reachable by manual
  subtraction, and the README has to explain the distinction in prose.

Bounded scope:

1. Add an explicit `unrealized_pnl` to `BacktestMetrics` (or a property on
   `BacktestResult`) and populate it **in the engine**, which is the only
   place that knows both the open positions and the initial capital.
   Do **not** compute it inside `calculate_backtest_metrics()`: that function
   receives only an equity curve and a trade log, and its `total_return` is
   the change of the *curve*, which only coincides with
   `final_value - initial_capital` when the curve starts at the initial
   capital.
2. Add a test that asserts
   `result.final_value - result.initial_capital == result.metrics.total_pnl +
   result.metrics.unrealized_pnl` for a run that ends with open positions
   (long and short), and that the field is `0.0` for a fully liquidated run.
3. Keep every existing public default and the existing
   `total_return`/`total_pnl` semantics unchanged — this is an addition, not
   a redefinition.
4. Document the field in the README next to the risk-limit / reconciliation
   prose.

Constraints: keep the existing public defaults; do not change the regime or
trade labelling rules; run `python3 -m pytest -q`, `python3 -m ruff check .`,
`python3 -m black --check .` and `python3 -m mypy quant_trading` before
handing off, and confirm the new test fails against the pre-change code.
