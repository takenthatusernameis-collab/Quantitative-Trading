# Next Task

## What changed
- Documented the EMA Crossover example script in `README.md` (commit `c712116`). The `examples/run_ema_crossover.py` script (added in a prior commit) had no corresponding README entry, unlike every other example script. Added a section after the Moving Average Crossover entry describing `EMACrossover`, its bullish/bearish cross signals, and the `python examples/run_ema_crossover.py` command.

## What was actually verified (this session)
- `python examples/run_ema_crossover.py` → runs offline against synthetic data, produces deterministic output (65 trades, 4.98% return, deterministic seed=42).
- `PYTHONPATH=. python examples/cli.py --strategy ema --symbols AAPL --offline --start 2026-09-01 --end 2026-10-15` → CLI accepts `--strategy ema` with fast/slow period args, runs successfully.
- Full test suite: `pytest` → 1115 passed, 1 skipped (matches green baseline). Run completed in ~141s.
- Linting: `python -m ruff check .` → All checks passed.
- Formatting: `python -m black --check .` → 79 files would be left unchanged (all formatted).
- Type checking: `python -m mypy quant_trading` → Success: no issues found in 36 source files.

## What remains unresolved
- CI workflow push blocker: GitHub App token lacks `workflows` permission ("refusing to allow a GitHub App to create or update workflow ... without workflows permission"). Workflows are maintainer-managed. `.github/workflows/` contains `kilo-workflow-audit.yml` and `main.yml`, but no `ci.yml`. This cannot be fixed with a code change and must not be retried identically.
- This blocker is documented in prior commit history and prevents pushing workflow files; it requires external maintainer action.

## Approaches already failed
- Pushing `ci.yml` / retrying the identical CI push → blocked by missing `workflows` permission on the GitHub App token. Do not repeat.

## One precise next task
- External (no code work required): maintainer must grant the `workflows` permission to the GitHub App token, or push `.github/workflows/ci.yml` manually. Until that is done, the codebase is green (1115 passed, 1 skipped; ruff/black/mypy clean) with EMA example documented and verified. Next session should inspect this evidence rather than re-running full verification or retrying the workflow push.