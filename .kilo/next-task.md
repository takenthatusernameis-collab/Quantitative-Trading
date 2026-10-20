# Next Task

## What changed

Fixed three defects in `quant_trading/risk/manager.py`. All three are
behaviour-preserving for callers that do not hit the buggy state, and each one
contradicts a contract the module already documents.

1. **`check_signal` ignored an explicit `portfolio_value=0.0`**
   (`quant_trading/risk/manager.py:225`). The line read
   `value = portfolio_value or self.portfolio_risk.total_market_value`, and
   `or` treats `0.0` as "not supplied", so an explicit zero fell back to the
   manager's internal value. The `if value <= 0` guard directly below it
   ("Portfolio value is zero or negative") was therefore unreachable for
   exactly `0.0` while still rejecting `-1.0`. The docstring already said
   "uses internal if None", so the fix is an explicit `is None` check.

2. **`current_drawdown` was measured against the *previous* peak**
   (`quant_trading/risk/manager.py:168-183`). `self.peak_value` was updated
   only *after* `PortfolioRisk` was constructed, so the drawdown was computed
   against the stale peak. Two consequences: a portfolio at a new all-time
   high reported a **positive** drawdown (`+0.2` after rising from 100,000 to
   120,000), even though `PortfolioRisk.current_drawdown` is documented as
   "0.0 = at peak"; and `PortfolioRisk.peak_value`, documented as "Peak
   portfolio value observed", was one update behind. The peak is now
   computed first, so the drawdown is always `<= 0` and agrees with the
   drawdown that `PortfolioLimit.check` computes from the same peak
   (`quant_trading/risk/limits.py:144`).

3. **`reset()` left the last computed metrics behind**
   (`quant_trading/risk/manager.py:394`). `self.risk_metrics` was not
   cleared, so a manager that had computed metrics still reported the
   Sharpe/drawdown of the discarded equity curve after a reset. The existing
   test `tests/test_risk_manager.py:432` already asserted `rm.risk_metrics is
   None` after `reset()`, but it never computed metrics first, so the
   assertion was vacuous and hid the bug.

## Verified

- `pytest tests/ -q`: **1511 passed, 1 skipped** (was 1506 passed, 1 skipped).
  Five new tests, no regressions.
- `pytest --doctest-modules tests/ quant_trading/ -q`: **1589 passed, 1 skipped,
  6 failed** — the 6 failures are pre-existing doctest failures in
  `quant_trading/risk/metrics.py` and are the next task (see below). They are
  unrelated to this change and were present before it.
- `ruff check quant_trading/ tests/`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `black --check quant_trading/risk/manager.py tests/test_risk_manager.py`:
  clean. (`black --check` still flags `quant_trading/strategies/examples.py`
  and `tests/test_portfolio.py`; both are pre-existing drift in files this
  change does not touch.)
- `python examples/cli.py --offline --symbols AAPL --days 120` runs clean.
- `python examples/run_analysis.py` runs clean.
- A standalone reproducer (`/home/runner/work/_temp/kilo-tmp/repro_risk_manager.py`)
  was run before and after the change and shows the before/after values for
  all three defects.

## Behaviour changes to be aware of

- `check_signal(signal, portfolio_value=0.0)` now **fails** the risk check
  instead of silently using the internal portfolio value. That is the point
  of the fix; `-1.0` already behaved this way.
- `PortfolioRisk.current_drawdown` is now `0.0` at a new peak instead of a
  positive number, and `PortfolioRisk.peak_value` now holds the real peak
  instead of the previous one. `history[-1]["drawdown"]` changes with it.
  `RiskManager.peak_value` and `check_portfolio()` are unaffected — they
  already used the updated peak.
- `RiskManager.risk_metrics` is `None` after `reset()`.

One existing assertion changed:
`tests/test_risk_manager.py:86` asserted
`current_drawdown == approx((120000 - 100000) / 100000)` (i.e. `+0.2`) at a new
peak. It now asserts `0.0`, which is what the attribute's own docstring
specifies. No other existing assertion was touched, and no production caller
depends on the old values (the only consumer, `Rebalancer._risk_adjust_buy`
at `quant_trading/portfolio/rebalancer.py:689`, compares against a negative
threshold and is unaffected at a peak).

## Note on the previously assigned task

The task named in the previous handoff — "Fix `Rebalancer.generate_rebalance_actions`
ignoring sell signals for short positions" — **was already implemented before
this session started** and needed no work:

- `quant_trading/portfolio/rebalancer.py:422` already reads
  `if holding and holding.quantity != 0:` (not `> 0`).
- The regression test already exists:
  `tests/test_rebalancer.py:131` (`test_generate_rebalance_actions_sell_signal_short`).
- `Portfolio.remove_holding` (`quant_trading/portfolio/portfolio.py:332-354`)
  already covers a short position and debits cash for it.

Do not re-implement it. The previous handoff's evidence was stale.

## Next task

**Make the doctests in `quant_trading/risk/metrics.py` executable and correct.**

Evidence: `pytest --doctest-modules quant_trading/` reports
**6 failed, 78 passed** — every failing doctest lives in
`quant_trading/risk/metrics.py`, and CI never runs them because
`pyproject.toml` sets `testpaths = ["tests"]` with no `--doctest-modules`.
So the module's documented examples have silently drifted away from the code.

The six failures, with the exact expected/actual values:

| Location | Expected | Actual | Classification |
| --- | --- | --- | --- |
| `metrics.py:15` (module docstring) | nothing | `7.750049096947889` | malformed doctest: a bare `...` line means "expect no output" in doctest, so the `+ELLIPSIS` directive never applies |
| `metrics.py:411` (`calculate_all_metrics`) | nothing | `11.90476190476198` | same malformed `...` pattern |
| `metrics.py:370` (`calculate_calmar_ratio`) | `1.09` | `504.0` | docstring is wrong; the code matches the documented formula (annual return / abs(max drawdown)) |
| `metrics.py:92` (`calculate_returns`) | `[0.02, -0.0098, 0.0297]` | `[0.02, -0.01, 0.03]` | docstring is wrong; `Series.round(3)` really does give `-0.01` and `0.03` |
| `metrics.py:187` (`calculate_sharpe_ratio`) | `2.06` | `1.06` | docstring is wrong; the code matches the documented formula (mean(excess) / std) |
| `metrics.py:229` (`calculate_sortino_ratio`) | `1.98` | `0.0` | **genuine conflict — needs a decision (see below)** |

Constraints and suggested approach:

- Add doctest collection to the pytest configuration so these examples are
  checked in CI. A verified configuration is
  `testpaths = ["tests", "quant_trading"]` plus
  `addopts = "--doctest-modules"`: with it the suite is
  **1589 passed, 1 skipped, 6 failed**, i.e. no existing test breaks and no
  other module's doctests break. Confirm the exact configuration on the
  current tree before committing.
- Fix the five docstring-only failures by correcting the expected output
  (or, for the two bare `...` cases, by asserting a concrete value such as
  `bool(metrics.sharpe_ratio)` -> `True`).
- The Sortino case is a real decision, not a transcription fix.
  `calculate_sortino_ratio` returns `0.0` whenever the return series has
  fewer than two losing observations (`quant_trading/risk/metrics.py:236-241`),
  so a strategy with a single loss reports "no downside risk" at all. The
  docstring's `1.98` corresponds to neither the code's `downside.std()`
  (undefined for one observation) nor the standard downside deviation
  `sqrt(sum(min(0, r - MAR)^2) / N)`; it corresponds to
  `excess / abs(worst_return)`. Pick one definition, state it in the
  docstring, implement it, and align the example.
- `tests/test_risk_metrics.py:194-216` pins the current behaviour: the
  `downside.std()` (ddof=1 over the losing subset only) divisor at line 197,
  and `0.0` for a single downside observation at lines 207-212. Those
  assertions will have to change if the definition changes; update them
  deliberately and explain why in the handoff.
- `tests/test_risk_metrics.py:194-198` is a good model for the style used in
  this repository: the expected value is computed from the same definition
  the implementation uses, so the test cannot drift from the code.

Useful context for later, if time allows: other findings that were
investigated and deliberately deferred, with their current status.

- `quant_trading/risk/limits.py:106,108` — `max_portfolio_risk` and
  `max_leverage` are configurable and documented but never enforced by
  `PortfolioLimit.check()`. This is a missing feature, not a bug, and is
  larger in scope.
- `quant_trading/regime/detector.py:539-553` — a segment's `return_pct` uses
  `prices[end] / prices[start + 1] - 1`, which drops the segment's first
  labeled return, so a one-bar segment always reports `0.0%` even when the
  bar moved 10%. Existing tests pin the current formula, so changing it
  changes documented semantics.
- `quant_trading/regime/detector.py:358` — a NaN price shifts the
  label-to-bar mapping (the return series is compacted with `dropna()` but
  the segment builder assumes label `i` is bar `i + 1`), producing wrong
  segment boundaries and `NaN` segment returns. No test pins the buggy
  behaviour.
- `quant_trading/backtest/engine.py:443` — the equity curve index is
  `[start] + processed_dates`, which produces a duplicate timestamp when
  `start` equals the first processed date.
