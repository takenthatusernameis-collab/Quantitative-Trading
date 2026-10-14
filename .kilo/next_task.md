# Task for the next Kilo agent

## Status: assigned task COMPLETE — quality gates restored; branch coverage is the next goal

## Context / verification of the assigned task

The previous handoff assigned: *"Close `quant_trading/data/yfinance_provider.py`
to 100% (or meaningfully raise it)"*, stated as 1534 stmts / 279 missed / 82%.

**That task is already COMPLETE.** A fresh full run
(`python -m coverage run --branch -m pytest tests/`) shows **817 passed** and:

- `quant_trading/data/yfinance_provider.py`: 1532 stmts, 0 missed, **100% line**
  (7 partial *branches* remain — see "Remains").
- All `quant_trading/` source: 3918 stmts, 0 missed, **100% line**.
- The handoff's "82% / 279 missed" figure (and its "667 passed" count) was stale —
  the line-coverage work was already finished before this session (git history:
  commits `04745d7`, `bf9140b`, and earlier). Do **not** re-attempt mocking the
  large network surface of yfinance_provider based on that stale figure.

## What changed this session

1. **Quality gates restored to green** (the previous handoff claimed these were
   clean, but they were *not* in this environment):
   - `black --check quant_trading/ tests/` → 59 files unchanged. Previously 2 test
     files needed reformatting: `tests/test_yfinance_fetch_many.py` and
     `tests/test_alphavantage_provider.py`. Applied `black` to both.
   - `mypy quant_trading/` → `Success: no issues found in 36 source files`.
     Previously 17 errors, all `Library stubs not installed for ...`. Fixed by
     installing the stub packages `pandas-stubs`, `types-requests`, `types-PyYAML`,
     and added them to `pyproject.toml` `[project.optional-dependencies] dev` so a
     fresh `pip install -e ".[dev]"` keeps the gate green.
   - `ruff check .` → All checks passed (already clean).

2. **Closed 4 source partial branches** with targeted tests (line coverage was
   already 100%; these are the first branch gaps closed). Each is a single partial,
   one test, verified to flip the branch to covered:
   - `quant_trading/config/settings.py` 96->98 — `Config.to_yaml` bare filename.
     `tests/test_config.py::TestConfig::test_to_yaml_bare_filename`
   - `quant_trading/data/providers.py` 166->169 — `DataManager.fetch(use_cache=False)`.
     `tests/test_data_providers.py::test_data_manager_fetch_no_cache`
   - `quant_trading/risk/metrics.py` 90->92 — `calculate_sortino_ratio(annualize=False)`.
     `tests/test_risk_metrics.py::TestCalculateSortinoRatio::test_non_annualized`
   - `quant_trading/utils/logging.py` 44->46 — `get_logger` existing-handler path.
     `tests/test_utils.py::test_get_logger_creates_or_returns_existing`

## What was verified

- `python -m coverage run --branch -m pytest tests/` → **817 passed** (813 + 4 new).
- `coverage report --include="quant_trading/*"`: 3918 stmts / 0 missed (100% line);
  branch partials 41 → **37**; the 4 files above now 100% branch.
- `ruff check .` → All checks passed.
- `black --check quant_trading/ tests/` → 59 files unchanged (clean).
- `mypy quant_trading/` → Success, no issues (36 files).
- The 4 new tests pass individually and within the full suite.

## What remains unresolved

Branch coverage is **not** enabled in the project config (no `[tool.coverage]`
section in `pyproject.toml`), so the "100%" is **line** coverage only. Enabling
branch coverage exposes 37 partial branches across source — the genuine remaining
gaps. Full list of remaining source partials (name stmts miss branch brpart missing):

- `quant_trading/backtest/engine.py`        1    295->exit
- `quant_trading/backtest/metrics.py`       1    95->107
- `quant_trading/backtest/trade_analysis.py` 5   110->105, 148->142, 156->160, 354->359, 359->exit
- `quant_trading/data/yfinance_provider.py` 7   107->111, 217->221, 222->233, 689->691, 1200->1186, 1579->1578, 2873->2877
- `quant_trading/optimization/base.py`      1    265->267
- `quant_trading/optimization/bayesian.py`  2    119->115, 206->209
- `quant_trading/optimization/walk_forward.py` 2   64->66, 299->279
- `quant_trading/portfolio/portfolio.py`    1    67->exit
- `quant_trading/portfolio/rebalancer.py`   8    81->74, 93->74, 115->107, 124->107, 126->107, 165->167, 171->175, 180->183
- `quant_trading/regime/detector.py`        1    202->206
- `quant_trading/risk/limits.py`           1    72->77
- `quant_trading/strategies/examples.py`    7    595->534, 615->534, 787->680, 834->680, 913->917, 925->929, 994->948

Cluster notes for the next agent:
- `strategies/examples.py`: 595->534 & 615->534 are the MACD `use_zero_line`
  zero-line fall-through arms (entered when `use_zero_line=True` but *neither*
  inner condition holds). The existing `create_macd_zero_line_data` helper only
  triggers the crossover, not the fall-through, so these are finicky. The
  Donchian/SuperTrend partials (787->680, 834->680, 913->917, 925->929, 994->948)
  are fallback/edge paths and more tractable.
- `portfolio/rebalancer.py` (8) and `backtest/trade_analysis.py` (5) are logic-rich
  conditional paths worth prioritizing.
- `data/yfinance_provider.py` (7) are mostly network/error-handling branches; use
  the `FakeResponse`/monkeypatch patterns already in `tests/test_data_providers.py`
  and `tests/test_yfinance_fetch_many.py`.

## Approaches already tried / failed

None this session. The earlier "close yfinance_provider to 100%" task appeared
blocked at "82%" in the handoff, but re-running coverage showed 100% line already.
Do not retry based on the stale miss count.

## Next task (precise, prioritized)

**Enable branch coverage as a project gate and close the remaining 37 partial
branches, largest cluster first, one module at a time.**

Recommended: add to `pyproject.toml`:
```toml
[tool.coverage.run]
branch = true
source = ["quant_trading"]
```
then verify with `python -m coverage run -m pytest tests/ && python -m coverage report
-m --include="quant_trading/*"`.

Order:
1. `portfolio/rebalancer.py` (8 partials) — add rebalancing scenarios that hit each
   fallback/zero-weight branch to `tests/test_rebalancer.py`.
2. `strategies/examples.py` (7) — start with Donchian/SuperTrend fallbacks, then the
   MACD zero-line fall-through if a clean data scenario is found.
3. `backtest/trade_analysis.py` (5) and `data/yfinance_provider.py` (7).
4. Remaining single partials (engine, metrics, base, bayesian, walk_forward,
   portfolio, detector, limits).

Constraint: add one cluster's tests, re-run branch coverage, confirm the partial
count drops, then move on. Do not attempt all 37 in one pass (the 4 single
partials here were closed one module at a time successfully).
