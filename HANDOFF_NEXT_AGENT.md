## Status

**calculate_max_drawdown zero/negative-peak engine-level regression test added and verified.**

The assigned task — add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_max_drawdown` zero/negative-peak semantics — is complete.

## What changed

- `tests/test_backtest_engine.py`:
  - Added `import numpy as np`.
  - Added `TestMaxDrawdownNonPositivePeak` class with three tests:
    - `test_zero_peak_reports_finite_drawdown_matching_direct_call`: equity `[0.0, -5.0, -10.0, -7.0]` (running peak zero) reports finite, non-NaN drawdown equal to a direct `calculate_max_drawdown` call.
    - `test_negative_peak_reports_finite_drawdown_matching_direct_call`: equity `[-5.0, -10.0, -3.0]` (running peak negative) reports finite, non-NaN drawdown equal to the direct call.
    - `test_zero_start_then_recovery_reports_finite_drawdown_matching_direct_call`: equity `[0.0, -5.0, 10.0]` reports finite, non-NaN drawdown equal to the direct call.
  - Each test drives the engine's metrics path via `calculate_backtest_metrics` (the same call the engine makes at `quant_trading/backtest/engine.py:929`) and asserts `max_drawdown`/`max_drawdown_pct` match `quant_trading/risk/metrics.py:calculate_max_drawdown` directly.
- No production behaviour change; `_align_series`/`calculate_max_drawdown` logic untouched.

## What was verified

- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_engine.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 417 passed (414 original + 3 new).
- `black --check`, `ruff check`, `mypy` clean on `tests/test_backtest_engine.py`.

## Unresolved

- None from the prior assignment.

## One precise next task

Add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_ulcer_index` zero/negative-peak semantics (e.g. equity curves `[0.0, -5.0, -10.0]`, `[-5.0, -10.0, -3.0]`, `[0.0, -5.0, 10.0]`), verifying the Ulcer Index does not produce NaN/inf and matches `quant_trading/risk/metrics.py:calculate_ulcer_index` directly, driven through `calculate_backtest_metrics` (the engine's path at `quant_trading/backtest/engine.py:929`). Mirror the `TestMaxDrawdownNonPositivePeak` structure just added. Re-run the five test files + black/ruff/mypy. Do not touch workflows.
