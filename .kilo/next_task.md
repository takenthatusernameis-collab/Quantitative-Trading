# Next Task

## What changed
- No new code changes in this session. Codebase remains in the state from the previous handoff: EMA Crossover example script exists (`examples/run_ema_crossover.py`), tests cover examples, all strategies and factory/registry include EMACrossover.

## What was actually verified (this session)
- Full test suite: `pytest` → 1115 passed, 1 skipped (matches green baseline). Run completed in ~87s.
- Linting: `ruff check .` → All checks passed.
- Formatting: `black --check .` → 79 files would be left unchanged (all formatted).
- Type checking: `mypy quant_trading` → Success: no issues found in 36 source files.
- Examples smoke tests: 16 passed, 1 skipped (includes EMA example).
- Coverage remains ~99% overall (single uncovered line in strategies/examples.py docstring context; not a functional gap).
- Confirmed EMA strategy is fully integrated: registered in `quant_trading/strategies/__init__.py`, factory supports `create_strategy("ema")`, CLI supports `--strategy ema` with parameter mapping, example script runs successfully producing deterministic output.

## What remains unresolved
- CI workflow push blocker: GitHub App token lacks `workflows` permission ("refusing to allow a GitHub App to create or update workflow ... without workflows permission"). Workflows are maintainer-managed. `.github/workflows/` contains `kilo-workflow-audit.yml` and `main.yml`, but no `ci.yml`. This cannot be fixed with a code change and must not be retried identically.
- This blocker is documented in prior commit history and prevents pushing workflow files; it requires external maintainer action.

## Approaches already failed
- Pushing `ci.yml` / retrying the identical CI push → blocked by missing `workflows` permission on the GitHub App token. Do not repeat.

## One precise next task
- External (no code work required): maintainer must grant the `workflows` permission to the GitHub App token, or push `.github/workflows/ci.yml` manually. Until that is done, the codebase is green (1115 passed, 1 skipped; ruff/black/mypy clean) with EMA example added and verified. Next session should inspect this evidence rather than re-running full verification or retrying the workflow push.
