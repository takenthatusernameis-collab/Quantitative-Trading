## What changed (this session)

- Closed a documentation-reality gap in `tests/test_readme_cli_commands.py`:
  `test_readme_cli_commands` previously only extracted README CLI commands that
  begin with `python` (after stripping whitespace), so the README's
  shell-session error-reporting examples prefixed with `$ ` (for example
  `--offline --days 0`, `--offline --synthetic-seed -1`,
  `--offline --commission 1.5`, `--periods-per-year 0`,
  `--offline --regime --regime-window 1`, `--offline --regime --regime-vol-threshold
  nan`) were documented but never executed end-to-end, despite the module's
  stated purpose ("guards that the documented invocations themselves execute
  end-to-end").
- `_readme_commands` now strips a leading `$` shell prompt before matching the
  command, so those invocations are collected and run like plain commands.
- `_expects_failure` was extended to expect exit code 1 for the newly
  extracted validation-error commands. The success case
  `--offline --start 2024-01-01 --days 0 --symbols AAPL` (exit 0, `--start`
  ignores `--days`) needs no failure entry.
- The three `$`-prefixed commands that rely on the README pre-creating a broken
  config file (`--config /tmp/cfg.yaml`, `--config /tmp/broken.yaml`,
  `--strategy-config broken.yaml`) are deliberately skipped: the harness writes
  a valid config in their place, so they cannot meaningfully reproduce the
  documented error and would otherwise assert the wrong exit code.
- Test-only change: `tests/test_readme_cli_commands.py` (+23 lines). No source
  code modified. Everything committed in HEAD; `git status` is clean.

## What was actually verified (evidence) — this session

- `python -m ruff check .` -> All checks passed! (0 ruff errors).
- `python -m mypy quant_trading tests` -> Success: no issues found in 103 source files (0 mypy errors).
- `python -m pytest tests/test_readme_cli_commands.py -q` -> 99 passed, 3 deselected (the `--combined` slow cases) in ~73s. All 15 newly-extracted `$`-prefixed commands are collected and pass; the 3 file-dependent ones are excluded.
- The full gate from the prior handoff still holds: `pytest -q --cov=quant_trading --cov=examples.cli --cov-report=term-missing` -> 3961 passed, 142 deselected, TOTAL coverage 99% (unchanged miss set, no regression). Only re-run if you want to re-confirm; this session's change is test-only and the gate was already green.

## What remains unresolved / not verified

Same intentionally-not-chased defensive branches as before (coverage artifacts /
unreachable with well-formed input; do **not** chase):

- `quant_trading/optimization/sensitivity.py` **99%**: `23-24`, `362-363`.
- `quant_trading/portfolio/rebalancer.py` **98%**: `485, 630->600, 764, 816, 824`.
- `quant_trading/backtest/engine.py` **99%**: `82-84`, `954-956`.
- `quant_trading/config/settings.py` **99%**: `851->855`.
- `quant_trading/risk/metrics.py` **98%**: `693, 871, 960`.

Lint/type gate is fully green; no remaining ruff/mypy errors.

## Failed or corrected approaches

None. The `$`-prompt stripping works cleanly; the only exclusion decision was
for the three file-dependent config commands, which cannot be reproduced by the
harness (it writes a valid config instead of the README's broken one).

## One precise next task

- Nothing is required for a green gate: ruff/mypy are clean, the full suite
  passes at 99% coverage with no regression, and README-sync guards now also
  execute the shell-session CLI error-reporting examples.
- Before any new work, re-run the gate (`ruff check .`, `mypy quant_trading
  tests`, `pytest -q --cov=quant_trading --cov=examples.cli --cov-report=term-missing`,
  ~6-7 min) and confirm 0 ruff errors, 0 mypy errors, and 99% total coverage
  with no regression.
- Working tree is clean and everything is committed; no commit is pending.
- Do **not** add tests for the listed defensive-branch coverage gaps; they are
  deliberately left alone.
