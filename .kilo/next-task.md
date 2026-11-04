# Next Task

## Repository state (post-cleanup)

All checks clean:
- `pytest -q` → **2749 passed, 129 deselected** (slow/network deselected by default).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 139 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Full coverage: **100%** across all 37 modules (6944 stmts, 0 miss, 2372 branches, 0 partial).

## What changed (this session)

Repaired a deterministic test failure introduced by the prior session's commit `58a351b`:

- That commit added `examples/run_cmo.py` (Chande Momentum Oscillator offline backtest) but did not document it in the README.
- The existing guard `tests/test_readme.py::TestReadmeExampleScripts::test_every_example_script_is_documented` failed with `example scripts missing from README: ['run_cmo.py']`.
- Fix: added a README "Example Scripts" entry for `examples/run_cmo.py` immediately after the existing `run_chande_momentum_oscillator.py` entry, describing the CMO zero-line crossover buy/sell behavior and the `python examples/run_cmo.py` command.

Only `README.md` was modified. No source, test, or config behavior changed.

## What was verified (this session)

- `tests/test_readme.py::TestReadmeExampleScripts` (both guard tests) now pass.
- Full `pytest -q` run: 2749 passed, 129 deselected, same as the pre-change baseline.
- `run_cmo.py` smoke tests (`test_example_script_imports_cleanly[run_cmo.py]`, `test_example_script_runs_offline[run_cmo.py]`) pass explicitly under `-m slow`.
- `python -m ruff check .`, `python -m black --check .`, `python -m mypy quant_trading/` all clean after the change.

## What remains unresolved

- Nothing functional. The tree is green and the README/example inventory is in sync again.
- The README change is left unstaged for the controller to checkpoint (never commit unless explicitly asked).
- Loose end left over from the prior session: `examples/run_cmo.py` has working-tree mode 600 while siblings are 644. Git tracks it as 100644, so it does not affect tracking or the smoke tests. Fix only if it causes an access problem.

## Approaches that failed and why

- Coverage-gap hunting is still a dead end: all 37 modules are at 100%.
- Inspecting the repo state directly (rather than hunting coverage gaps) surfaced the real defect: the previous session's commit added `examples/run_cmo.py` without a README entry, breaking the deterministic `TestReadmeExampleScripts` guard. Repairing the README is the minimal, safe fix.

## One precise next task

- If another session is requested, first re-run `pytest -q`, `python -m ruff check .`, `python -m black --check .`, and `python -m mypy quant_trading/` to confirm the tree is still green, then select a new bounded task.
- Candidate directions: add a missing `examples/run_*.py` for one of the 25 primary keys that still lack one (`klinger`, `chop`, `dpo`, `nvi`, `pvi`, `sar`, `stoch`, `stochrsi`, `supertrend`, `vol`, `vpt`, `vroc`, `williamsr`, `ao`, `cho`, `cmf`, `ema`, `eom`, `hma`, `mfi`, `roc`, `bb`, `bbpct`, `adl`) — each new script MUST also get a README entry or it will break the same `TestReadmeExampleScripts` guard, or extend CLI/README coverage for an under-documented feature.

(End of file)