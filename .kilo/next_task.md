# Next Task: Close remaining 12 branch partials (coverage gate)

## Context

A `branch = true` coverage gate was added to `pyproject.toml` under
`[tool.coverage.run]`/`[tool.coverage.report]`. The full suite is green
(`847 passed, 13 warnings`) and overall branch coverage is 99% (1246 branches,
12 partials remaining out of the original 37).

## What was already done (verified)

- `tests/test_rebalancer.py` — rebalancer.py 100% branch (8 partials closed).
- `tests/test_trade_analysis.py` — trade_analysis.py 100% branch (5 closed).
- `tests/test_limits.py` — risk/limits.py 100% branch (1 closed).
- `tests/test_regime.py` — regime/detector.py 100% branch (1 closed).
- `tests/test_portfolio.py` — portfolio/portfolio.py 100% branch (1 closed).
- `tests/test_backtest_engine.py` — backtest/engine.py 100% branch (1 closed).
- `tests/test_optimization.py` — optimization/bayesian.py 100% branch,
  walk_forward.py 1 partial closed, base.py 1 closed.
- `tests/test_strategies_examples.py` — strategies/examples.py 5 partials closed
  (Donchian no-exit arms, MACD zero-line-disabled arm).
- `tests/test_strategy_aroon.py` — Aroon no-crossover arm closed.

## Remaining partials (run: `python -m coverage run --branch -m pytest tests/ -q`
then `python -m coverage report -m --include="quant_trading/*"`)

| File | Missing |
|---|---|
| `quant_trading/backtest/metrics.py` | `95->107` — `if len(returns) > 0` False arm; effectively unreachable because `calculate_returns` always returns a non-empty Series after the length guard |
| `quant_trading/data/providers.py` | `11` — `if TYPE_CHECKING:` import block; type-checking-only, unreachable at runtime |
| `quant_trading/data/yfinance_provider.py` | `107->111, 217->221, 222->233, 689->691, 1200->1186, 1579->1578, 2873->2877` — cache-hit/empty-data/parse/exception branches in `AlphaVantageProvider`; see `tests/test_alphavantage_provider.py` fixtures (`FakeResponse`, `DAILY_RESPONSE`, etc.) |
| `quant_trading/optimization/base.py` | `225` — abstract `run()` body (`...`); unreachable by definition |
| `quant_trading/strategies/examples.py` | `615->534, 913->917, 925->929` — MACD bearish zero-line crossover, Aroon inner-loop `for` without `break` (pandas skips `rolling.apply` when the window contains NaN, so these are effectively unreachable) |

## Suggested next steps

1. **Close the reachable yfinance partials** using the existing
   `tests/test_alphavantage_provider.py` fixtures (cache hit on group fetch,
   empty-data handling, parse branches, exception paths). This is the largest
   cluster (7 partials) and is reachable.
2. **For the unreachable partials** (`metrics.py 95->107`, `providers.py 11`,
   `base.py 225`, `examples.py 913->917`/`925->929`), add
   `# pragma: no cover` markers to the defensive branches rather than
   contorting tests to hit them — this is the idiomatic coverage approach and
   keeps the gate honest.
3. Re-run the full suite and confirm 0 partials before declaring the gate green.

## Constraints

- Do not weaken the coverage gate or disable validation to make numbers go up.
- Keep changes minimal and reversible; do not refactor unrelated modules.
- Run `python -m pytest tests/ -q` after every change.