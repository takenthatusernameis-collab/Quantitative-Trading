# Next Task

## Repository state (verified 2026-11-07, session 2)
- Environment gap discovered: a fresh checkout has **no** pandas/numpy/pytest/ruff/
  mypy installed. Run `pip install -e ".[dev]"` first; binaries land in
  `~/.local/bin` (not on PATH by default).
- `python3 -m ruff check .` → All checks passed.
- `python3 -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python3 -m pytest -q -m "not slow and not network" --no-cov` → 2901 passed, 1
  skipped, 131 deselected, 1 warning (257.70s). Reproduced the previous session's
  count exactly.
- `git status` → clean; `git log -1 --oneline` → `f1ffac6`; branch `main` up to date
  with `origin/main`.
- No open issues on the GitHub remote (0 open issues). No TODO/FIXME/HACK markers
  in `quant_trading/` or `examples/`.

## Completed this session
- Installed dev dependencies and independently re-verified the baseline (ruff,
  mypy, full fast test suite) — the previous session's "verified" claims are
  reproducible, not asserted.
- Probed the CLI end-to-end in every documented offline mode (single backtest,
  grid/bayesian optimization, walk-forward, combined, combined+regime+monte-carlo,
  regime, monte-carlo bootstrap/parametric) and every documented validation case
  (`--mc-simulations 0`, `--wf-step-size 0`, `--n-jobs -2`,
  `--bayesian-n-initial > --n-iter`). All behave as documented: exit 0 on success,
  one-line `Error: ...` and exit 1 on user error, no tracebacks.
- Verified the README's PnL identity on a live multi-symbol run:
  `final_value - initial_capital == total_pnl + unrealized_pnl` holds.
- Confirmed the combined JSON output shape matches the README
  (`best_strategy`, `comparison` with `total_pnl`/`unrealized_pnl`,
  `monte_carlo`, `regime_analysis`).
- Confirmed the slow suite (`-m "slow and not network"`) → 131 passed, 2902
  deselected (242.30s), matching the previous session's count.

## One precise next task
**No bounded task pending.** No reproducible defect found after direct CLI probing.
Act only on a new external issue or feature request with concrete requirements.
On arrival: reproduce/define acceptance criteria, implement the smallest reversible
change, and verify (targeted checks + `ruff` + `mypy` + relevant/full tests).

Notes for the next session:
- The 1 skipped fast test (`tests/test_cli.py:4050`) is a correct conditional
  `skipif` for the "bayesian optimizer without scikit-optimize" path; it only runs
  in skopt-less environments. Not a defect.
- `data/` at repo root is `drwx------`, gitignored, and created at runtime by the
  data providers (`cache_dir="./data/cache"`). It is an environment artifact — do
  not change `.gitignore` or commit it.
- `python3 -m pytest -q -m "slow and not network" --no-cov` → 131 passed, 2902
  deselected (242.30s). Confirmed this session.