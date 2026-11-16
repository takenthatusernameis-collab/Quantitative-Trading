## What changed (this session)

- Added a README "Example Scripts" subsection for the previously-undocumented
  `examples/run_ma_envelope.py` script, placed immediately after the existing
  Moving Average Crossover subsection (README.md ~1378-1387).
- No code, strategy, or test changes. The `MovingAverageEnvelopeStrategy`,
  its registry entry, the example script, and its tests were all already
  present from the prior commit (956dbdf); only the user-facing README
  documentation was missing.

## What was actually verified (evidence) — this session

- `python examples/run_ma_envelope.py` exits 0 and prints a clean summary
  (Final Value $107,881.48, 98 trades, 81.63% win rate, Sharpe 1.32).
- `pytest tests/test_example_scripts_run.py -q`: 56 passed (the new README
  section is not required by this test — it globs `examples/run_*.py` — but
  the script it documents is confirmed to run).
- `pytest tests/test_readme_cli_commands.py -q`: 100 passed, 3 deselected.
- `pytest tests/test_strategies_examples.py -q`: 563 passed.
- `pytest --doctest-modules quant_trading/strategies/examples.py -q`: 48 passed
  (covers the `MovingAverageEnvelopeStrategy` doctest).
- `python -m ruff check .`: All checks passed! (0 errors).
- `python -m mypy quant_trading tests`: Success, no issues in 103 source files.
- Working tree clean after commit `2c4ce40`.

## What remains unresolved / not verified

- Nothing blocking. The repo is green and committed. Intentionally-not-chased
  defensive-branch coverage gaps remain (sensitivity.py 99%; rebalancer.py 98%;
  engine.py 99%; settings.py 99%; risk/metrics.py 98%). Do not chase these.

## Failed or corrected approaches

- None this session. Single small edit; all checks green on first pass.

## One precise next task

- No further required work. Repository is green and committed. Next agent may
  pick any bounded, high-value task if assigned; otherwise leave as-is. Do not
  add tests for the listed defensive-branch gaps.

(End of file - total 30 lines)