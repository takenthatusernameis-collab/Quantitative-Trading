# Next Task

## Repository state (verified 2026-11-07, session 3)
- Working tree clean; `git log -1 --oneline` → `d739d45`; branch `main` up to
  date with `origin/main`. No open issues or PRs on the remote.
- `python3 -m ruff check .` → All checks passed.
- `python3 -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Targeted confidence subset
  `python3 -m pytest tests/test_packaging.py tests/test_strategy_factory.py
  tests/test_strategy_registry_coverage.py tests/test_readme.py
  tests/test_readme_cli.py tests/test_readme_cli_commands.py -q` → **146
  passed, 3 deselected** (~37s).
- Strategy registry: 46 primary keys, 108 total keys (with aliases). README
  registry table, aliases, example-script references, and `Test<ClassName>`
  coverage all reconcile with the live registry.

## Completed this session
- Independently re-verified the baseline (ruff, mypy, targeted confidence
  subset) — the prior sessions' "verified" claims are reproducible, not
  asserted.
- Probed `--output-strategy-config` roundtrip for a regular backtest, an
  optimization, and a `--strategy-config` run: each writes a YAML that
  re-creates the same strategy (verified `type`/`name`/`parameters` round
  trip). README claim holds.
- Probed combined-mode JSON shape: `--combined` alone emits
  `{best_strategy, comparison}`; adding `--regime --monte-carlo` adds
  `monte_carlo` and `regime_analysis` at the top level. Matches the README.
- Probed `--strategy-config` precedence: it overrides `--strategy` and every
  individual `--*-period`/`--*-multiplier` flag for the same parameter, as the
  README documents.
- Confirmed README ↔ code ↔ CLI ↔ examples ↔ tests all stay in sync; no
  undocumented flag, no doc/code drift, no README claim the code violates.

## One precise next task
**No bounded task pending.** No reproducible defect found after direct CLI
probing and baseline re-verification. Act only on a new external issue or
feature request with concrete requirements. On arrival: reproduce/define
acceptance criteria, implement the smallest reversible change, and verify
(targeted checks + `ruff` + `mypy` + relevant/full tests).

Notes for the next session:
- `pytest`/`ruff`/`mypy` are importable as modules (`python3 -m pytest`, etc.);
  the `~/.local/bin` copies are not on PATH by default.
- `data/` at repo root is `drwx------`, gitignored, created at runtime by the
  data providers (`cache_dir="./data/cache"`). It is an environment artifact —
  do not change `.gitignore` or commit it.
- The 1 skipped fast test (`tests/test_cli.py:4050`) is a correct conditional
  `skipif` for the "bayesian optimizer without scikit-optimize" path; it only
  runs in skopt-less environments. Not a defect.