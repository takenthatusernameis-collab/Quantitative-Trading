# Next Task

## What changed
- Added `examples/run_ema_crossover.py` (67 lines) — an offline EMA Crossover backtest example using deterministic synthetic data (seed=42), following the exact pattern of the 12 sibling `run_*.py` scripts.
- Rationale: `EMACrossover` is a registered built-in strategy (registered as `"ema"` in `quant_trading/strategies/__init__.py:30`) and is accepted by the CLI (`--strategy ema` works offline), but it was the only registered built-in strategy without a runnable example script. All other built-ins (`ma`, `rsi`, `bb`, `macd`, `supertrend`, `donchian`, `aroon`, `keltner`, `stoch`, `ichimoku`, `sar`, `vwap`) had one.
- Committed as `403d7b2` on `main`. Working tree clean.

## What was actually verified (this session)
- Independently re-verified the green baseline before making changes: `pytest` 1114 passed/1 skipped, `ruff` clean, `black` 78 files unchanged, `mypy` 36 files clean, 99% coverage.
- Confirmed the prior handoff's blocker claim was accurate: the CI push blocker is a deterministic external permission issue (GitHub App token lacks `workflows` permission). `.github/scripts/kilo-controller.sh:6,310,313,328` explicitly restores/excludes `.github/workflows/**` to keep workflows maintainer-managed. Retrying the push would fail identically — do not repeat.
- Confirmed `--strategy ema` runs end-to-end offline (`examples/cli.py` accepts it; `create_strategy` maps `ema` params; `BUILTIN_STRATEGY_KEYS` deliberately omits `ema` but the combined-run loop at `examples/cli.py:1726` also excludes it to preserve test compatibility).
- New script verified: `python examples/run_ema_crossover.py` exits 0, produces realistic output (4.98% return, 65 trades).
- Smoke test now covers it: `tests/test_examples_smoke.py` is parametrized over `examples/run_*.py`, so the new script is auto-included. `pytest tests/test_examples_smoke.py` → 16 passed, 1 skipped (was 15 passed).
- Final full verification after change: `pytest tests/` → **1115 passed, 1 skipped**; `ruff` All checks passed; `black` 79 files unchanged; `mypy` Success: no issues in 36 source files.

## What remains unresolved
- CI workflow push blocker: GitHub App token lacks `workflows` permission ("refusing to allow a GitHub App to create or update workflow ... without workflows permission"). Workflows are maintainer-managed. `.github/workflows/` contains `kilo-workflow-audit.yml` and `main.yml`, but no `ci.yml`. This cannot be fixed with a code change and must not be retried identically.

## Approaches already failed
- Pushing `ci.yml` / retrying the identical CI push → blocked by missing `workflows` permission on the GitHub App token. Do not repeat.

## One precise next task
- External (no code work required): maintainer must grant the `workflows` permission to the GitHub App token, or push `.github/workflows/ci.yml` manually. Until then, the codebase is green (1115 tests, lint/format/type clean) and no further code work is required. Next session should inspect this evidence rather than re-running lint/typecheck/tests or retrying the push.

(End of file - total 30 lines)