## What changed (2026-11-09, this session)

- **Type-hygiene / root-cause fixes (small, reversible):**
  - `quant_trading/backtest/engine.py`: added explicit optional analysis fields on `BacktestResult` (`regime_analysis`, `monte_carlo`, `trade_analysis` with `TYPE_CHECKING` imports); removed `type: ignore[attr-defined]` assignments in `from_dict` and `type: ignore[no-any-return]` in `to_dataframe`; cleaned unused `cast` import and removed quoted return annotation (ruff UP037). Kept serialization behavior compatible (attrs still optional, `to_dict` emits them when present).
  - `quant_trading/optimization/base.py`: fixed `OptimizationResult.from_dict` best_result parsing (preserves pass-through for non-dict/legacy sentinel values as covered by tests); `_coerce_datetime` now returns `None` for unsupported types (removes ignore; still accepts `None`/`datetime`/ISO strings).
  - `quant_trading/optimization/__init__.py`: removed unused `Any` import; kept optional `BayesianOptimizer` import fallback pattern but reduced ignores (mypy clean).
  - `quant_trading/strategies/examples.py`: removed `type: ignore[no-any-return]` in NVI/PVI helpers by returning typed series directly (no behavior change; indexes preserved). For RSI/Choppiness helpers, removed ignores with minimal numeric-stability guards (`avg_loss` zero -> NaN/RSI fillna 100; CHOP inf/-inf -> NaN) consistent with existing NaN-safe handling patterns; targeted strategy/backtest tests passed.

## Verified (this session)

- `python -m pytest -q --tb=line` (default suite/markers) → **3015 passed, 110 skipped, 129 deselected** (~398s).
- `python -m ruff check .` → **All checks passed**.
- `python -m mypy quant_trading --ignore-missing-imports` → **Success, no issues (37 files)**.
- Focused: `pytest tests/test_backtest_engine.py tests/test_strategies*.py -q` → **652 passed**.
- Focused: `pytest tests/test_optimization.py -q` → **110 passed, 30 skipped** (Bayesian tests skipped where deps absent).

## Unresolved / not completed

- `quant_trading/optimization/bayesian.py:376` still has `@self._use_named_args  # type: ignore[untyped-decorator]`. `skopt` is not installed in this environment (Bayesian tests skipped), so changing decorator typing without evidence/running skopt-dependent checks risks breakage. Leave unless task requires Bayesian typing refactor + skopt installed/verified.
- Remaining `type: ignore` count in `quant_trading/` reduced to **1** (bayesian decorator). Prior count was 12.
- `_RebalancePlan` (private, `quant_trading/portfolio/rebalancer.py`) still lacks `to_dict`/`from_dict` (intentionally uncovered; no demonstrated need).

## Failed approaches (do not repeat unchanged)

- I briefly changed `OptimizationResult.from_dict` to coerce non-`BacktestResult`/non-dict `best_result` values to `None`. This broke `tests/test_optimization.py::TestOptimizationResultSerialization::test_from_dict_passes_through_non_dict_best_result` (expects non-dict sentinel pass-through). Reverted to pass-through semantics while keeping mypy clean via explicit `Any`-permissive local typing.

## One precise next task

- **Trigger:** If `scikit-optimize`/`skopt` is available in the environment or added as a dev dependency for verification.
- **Action:** Remove `type: ignore[untyped-decorator]` in `quant_trading/optimization/bayesian.py` by adding a narrowly-scoped typing-safe wrapper/protocol or `cast(Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]], use_named_args)`-style pattern (only if verified), without changing runtime behavior.
- **Constraints:** Smallest reversible change; no API/safety weakening; verify with `python -m pytest tests/test_optimization.py -q` (including Bayesian tests when skopt present), `python -m ruff check .`, `python -m mypy quant_trading --ignore-missing-imports`. Do not claim Bayesian tests passed if skopt remains unavailable—state evidence.

## Git state

- Working tree has **4 modified source files** (no commit made this session): `quant_trading/backtest/engine.py`, `quant_trading/optimization/__init__.py`, `quant_trading/optimization/base.py`, `quant_trading/strategies/examples.py`. No secrets/caches added.
