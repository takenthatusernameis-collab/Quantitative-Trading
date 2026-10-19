# Next Task

## What changed (this session)

Two commits, both pushed to `origin/main` (`f60ac45`, `baeb83d`).

### 1. Closed the last coverage gap in the package (`f60ac45`)

- `quant_trading/strategies/examples.py` — the only module that still had a
  coverage gap. The reported arc `2165->2124` is the **fall-through of the
  bearish `elif`** in `ParabolicSARStrategy.generate_signals`, *not* the
  long-to-short reversal path. It is **unreachable**: `_calculate_sar` only
  ever emits trend values of `+1`/`-1`, so `current_trend != prev_trend`
  always matches exactly one of the two reversal patterns and the `elif`
  never falls through. The arc is now marked `# pragma: no branch` (with a
  comment stating why). **No strategy logic was changed.**
- `tests/test_strategies_examples.py`:
  - Repaired the tests added for this gap in the previous two commits
    (`aac5991`, `3604d96`). Three of them **never executed**: one was
    nested inside the module-level `create_momentum_data` helper and two
    were nested inside the `if __name__ == "__main__":` block, so Python
    parsed them as nested functions, not tests. They are now real test
    methods.
  - Removed `TestParabolicSARStrategyAdditional`, which duplicated the
    existing `test_generate_signals_bearish_reversal`; its scenario is kept
    as `test_generate_signals_bearish_reversal_after_sustained_uptrend`.
  - Added `test_generate_signals_skips_nan_current_price` (the
    `MomentumStrategy` guard's first clause had no test).
  - Added two parametrized invariant tests over four hand-traced SAR
    scenarios (`SAR_SCENARIOS`): the SAR trend is always bipolar
    (`+1`/`-1`), and every trend change produces exactly one signal of the
    matching side. These encode the invariant that makes the `elif`
    fall-through dead, so a future change that breaks it fails loudly
    instead of silently invalidating the pragma.
- `README.md` — the "Strategy Registry" table documented only 4 of the 14
  registered strategies; it now documents all 14, and the "Built-in
  Strategies" feature bullet was corrected.
- `tests/test_readme.py` (new, 3 tests) — parses the README registry table
  and checks it against `quant_trading.strategies.list_strategies()`, so the
  table can no longer drift.

### 2. Untracked generated runtime artifacts (`baeb83d`)

`git rm --cached` (working-tree copies untouched) for:

- `coverage.xml` — a stale Cobertura report describing 4392 statements /
  1402 branches, while the current package has 4489 / 1440. The repo's own
  tooling already treats it as an artifact: `.github/scripts/kilo-controller.sh`
  excludes `**/coverage.xml` and `**/.coverage` from the changes it stages.
- `test_output.json` — the JSON result of one `examples/cli.py --output` run.
- `data/cache/yfinance_AAPL,GOOGL_..._1d.pkl` — a 48 KB pickled market-data
  cache. `.gitignore` already listed `data/cache/`, but the rule never
  applied to an already-tracked file, so the ignore list was misleading.

`coverage.xml` and `test_output.json` were added to `.gitignore` so they
cannot be re-added.

## What was actually verified (this session)

- `python -m pytest` → **1172 passed, 1 skipped** (baseline at session start:
  1160 passed, 1 skipped; +12 new tests).
- `python -m pytest --cov=quant_trading --cov-report=term-missing` →
  **TOTAL 100%** — 4489 statements, 1440 branches, 0 missing, 0 partial.
  At session start the same command reported `examples.py ... 2165->2124`
  and `TOTAL 99%`. The two spots named in the previous handoff
  (`2165->2124` and `2401`) were the only gaps in the whole package; both
  are now closed.
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 81 files unchanged. **Note: black was
  failing at session start** — the previous session's commits left
  `tests/test_strategies_examples.py` unformatted. Now fixed.
- `python -m mypy quant_trading examples/cli.py` → Success, 37 source files.
- The `# pragma: no branch` was proved to suppress **only** the dead arc:
  using the coverage API on a run that does not exercise the sell path, the
  bearish branch body statements (lines 2168/2170/2171/...) are still in
  the measured statement set and are still reported as **missing**. A/B
  tested on a toy module: with the pragma the missing-branch count drops
  to 0 while the branch body stays required; without it the branch is
  reported missing again. `no branch` comes from coverage's
  `partial_always` list, so it stays active even though this project
  overrides `exclude_lines` in `pyproject.toml`.
- The README drift test was negative-tested: deleting one registry row and
  corrupting one class name makes 2 of the 3 tests fail; restoring the file
  makes all 3 pass.
- The untracked files were confirmed to still exist on disk after
  `git rm --cached`, and `git check-ignore --no-index` confirms all three
  are now matched by `.gitignore` rules.

## What remains unresolved

- **Trading costs do not affect the backtest equity curve** — this is the
  next task, described below. It is a real, reproducible defect, not a
  cosmetic issue.
- **External CI workflow blocker (unchanged from prior handoffs):** the
  GitHub App token lacks the `workflows` permission, so workflow files
  cannot be pushed. `.github/workflows/` contains `kilo-workflow-audit.yml`
  and `main.yml` but no `ci.yml`. This requires maintainer action and
  cannot be fixed with a code change. Do not retry the identical workflow
  push.

## Approaches already failed

- **Trying to cover `2165->2124` with new OHLC test data.** The arc is the
  *fall-through* of the bearish `elif`, not the reversal path; the
  reversal path is the arc `2165->2167`, which was already covered. The
  previous handoff misidentified the arc, which is why two sessions spent
  effort on data that could never reach it.
- **Adding tests at the wrong indentation level.** Commits `aac5991` and
  `3604d96` placed test functions one level too deep, so they were parsed
  as nested functions inside `create_momentum_data` and inside the
  `if __name__ == "__main__":` block. The file still parsed and pytest
  still passed — the tests were simply never collected. Lesson: after
  adding tests, check the *collected* count (`pytest --collect-only -q`)
  or assert on `trades_df` content, not just on a green run.
- **`pytest --cov=quant_trading.strategies.examples`** → `ImportError:
  cannot load module more than once per process`. Use `--cov=quant_trading`
  (the package) instead of a module path.

## One precise next task

**Make the backtest actually charge commission and slippage to the
portfolio, so the equity curve, `final_value`, `total_return_pct` and every
equity-derived metric (Sharpe, Sortino, Calmar, max drawdown) agree with
the trade log.**

### The defect, with reproduction

`BacktestConfig.commission` is documented as "Commission rate per trade (as
a fraction of trade value)" and `slippage` as "Slippage rate applied to
each fill"; the README advertises "Event-driven backtest with realistic
costs (commission, slippage)". But the costs never reach the portfolio:

- `quant_trading/portfolio/portfolio.py:224` — `add_holding` does
  `self.cash -= quantity * price`. No commission, no slippage.
- `quant_trading/portfolio/portfolio.py:253` — `remove_holding` does
  `self.cash += actual_qty * price`. No commission, no slippage.
- `quant_trading/backtest/engine.py:483` — the buy sizing check *does* use a
  cost-inclusive `cost = quantity * price * (1 + commission + slippage)`,
  so a trade can be sized against costs it never pays.
- `quant_trading/backtest/engine.py:516` — the sell's `realized_pnl` *is*
  cost-aware, and `Trade.cost` / `Trade.pnl` are cost-aware properties.

So the trade log is cost-aware while the portfolio is cost-blind, and the
two do not reconcile.

Reproduction (deterministic, no network, ~1 s):

```python
# 6 daily bars, buy on bar 1 at 110, sell on bar 3 at 130
# run the same strategy with (commission, slippage) = (0.0, 0.0)
#                                       and with (0.01, 0.005)
```

Observed on this tree:

```
equity zero-cost: [10000.0, 10000.0, 10100.0, 10200.0, 10200.0, 10200.0, 10200.0]
equity costed   : [10000.0, 10000.0, 10100.0, 10200.0, 10200.0, 10200.0, 10200.0]
EQUITY CURVES IDENTICAL? True
zero-cost final_value: 10200.0   ret%: 2.0
costed    final_value: 10200.0   ret%: 2.0
costed trades 'cost' column: [1014.9999999999999, 1182.0]   sum: 2197.0
costed trades 'pnl'  column: [0.0, 182.0]                    sum: 182.0
```

`final_value - initial_capital` is 200 but the sum of realized PnL is 182;
the 18 difference is exactly the uncharged costs.

### Constraints and evidence for the next agent

- **Decide the cost model explicitly before coding.** Two defensible
  models: (a) charge costs as fees on the cash leg — buy cash reduced by
  `quantity * price * (1 + commission + slippage)`, sell proceeds credited
  `quantity * price * (1 - commission - slippage)`; or (b) model slippage
  as a worse fill price — buy at `price * (1 + slippage)`, sell at
  `price * (1 - slippage)`, plus commission as a fee. The existing
  `Trade.cost` property implies (a); (b) is what most engines do. Whichever
  is chosen, `Trade.cost`, `Trade.pnl`, the portfolio cash and the trade
  log must all agree.
- **Target invariants, to be encoded as executable tests:**
  1. A costed run's equity curve must be strictly below a zero-cost run's
     for the same data and strategy.
  2. `final_value - initial_capital` must equal the sum of the trades'
     `pnl` column (within float tolerance) once costs are charged to cash.
  3. The sum of `trades["cost"]` must be consistent with the cash
     reduction across the run.
- **Do not silently change unrelated numbers.** This fix changes every
  previously reported backtest result. Audit the existing tests that assert
  on equity values, `final_value` or metrics and update them deliberately
  (e.g. `tests/test_backtest_engine.py:168` asserts
  `result.total_return_pct == 2.0`; `tests/test_integration.py` and
  `tests/test_backtest_analysis.py` may assert on other values).
- Keep the package at **100% line and branch coverage** — it is there now
  and the new cost branches must be covered.
- Keep `ruff check .`, `black --check .` and `mypy quant_trading` clean.
- The suite must stay green at **1172 passed, 1 skipped** (plus the new
  tests).
- A useful side effect to consider: `BacktestResult` could expose the
  total costs paid, so the headline numbers and the trade log can be
  reconciled by a reader without recomputing them.
