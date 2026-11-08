# Next Task

## Repository state (verified 2026-11-08, thirty-third session)
- Working tree clean; `git log -1 --oneline` → `5d388ab`; branch `main` up to
  date with `origin/main`. No open issues or PRs on the remote.
- `python3 -m ruff check .` → All checks passed.
- `python3 -m mypy quant_trading/` → Success: no issues found in 37 source
  files.
- `python3 -m pytest -q tests/test_risk_metrics.py tests/test_readme.py
  tests/test_repository_integrity.py` → **119 passed** in 6.50s.
- Prior Sortino fix (flat-portfolio zero-variance guard) confirmed live via
  `examples/cli.py --offline --provider synthetic --strategy ma --days 10
  --symbols AAPL` → `Sortino Ratio: 0.00`.

## Completed this session
- Audited every ratio/division site in `quant_trading/risk/metrics.py` for a
  missing zero-variance / divisor-zero guard (the class of defect the prior
  handoff flagged). All are guarded: `calculate_volatility`,
  `calculate_max_drawdown`, `calculate_sharpe_ratio`, `calculate_sortino_ratio`,
  `calculate_var`, `calculate_beta`, `calculate_alpha`,
  `calculate_calmar_ratio`. No missing guard found.
- Investigated the unintuitive `Trade Sharpe: -51.79` /
  `Trade Sortino: -15.20` printed by `examples/run_analysis.py`. Confirmed
  it is mathematically correct, not a degenerate-division artifact: the
  per-trade return series has non-zero variance (std ≈ 2.02e-05) with a
  positive but tiny mean (≈ 1.13e-06) below the per-period risk-free rate
  (≈ 7.94e-05), so the excess is legitimately negative. Reproduced
  deterministically (Sharpe ≈ -61.6, Sortino ≈ -15.4 annualized). No change
  made.

## One precise next task
**No bounded task pending.** No reproducible defect found after guard audit,
runtime output probing, and baseline re-verification. Act only on a new
external issue or feature request with concrete requirements. On arrival:
reproduce/define acceptance criteria, implement the smallest reversible
change, and verify (targeted checks + `ruff` + `mypy` + relevant/full tests).

Notes for the next session:
- `pytest`/`ruff`/`mypy` are importable as modules (`python3 -m pytest`, etc.).
- `data/` at repo root is `drwx------`, gitignored, created at runtime by the
  data providers. It is an environment artifact — do not change `.gitignore`
  or commit it.
- Full fast suite needs timeout > 300000 ms (~400s+); `rg` is unavailable
  (use grep/Python); commit/push only if explicitly requested.