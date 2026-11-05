# Next Task

## Repository state (post-cleanup)

All checks clean:
- `pytest -q` → **2752 passed, 131 deselected** (slow/network deselected by default).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 140 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Full coverage: **100%** across all 37 modules (6944 stmts, 0 miss, 2372 branches, 0 partial).

## What changed (this session)

Added three previously-undocumented CLI flags to the README "Basic Usage" section:

- `--version` — prints `quant-trading 0.1.0` and exits.
- `--start` / `--end` — explicit date range (YYYY-MM-DD), overrides `--days`.
- `--cache-dir` — custom cache directory for downloaded data.

Only `README.md` was modified (9 insertions). No source, test, or config behavior changed.

## What was verified (this session)

- `tests/test_readme_cli.py`, `tests/test_readme_cli_commands.py`, `tests/test_readme.py`, `tests/test_strategy_registry_coverage.py` → 59 passed, 3 deselected.
- Full `pytest -q` → 2752 passed, 131 deselected (baseline 2749; the +3 are the three newly documented commands, each now covered by `TestReadmeCliCommands`).
- `python -m ruff check .`, `python -m black --check .`, `python -m mypy quant_trading/` all clean.
- Manually ran all three documented commands; each exits 0 with no traceback. Temp cache dirs cleaned up.

## What remains unresolved

- Nothing functional. The tree is green and the README/CLI inventory is in sync again.
- The README change is left unstaged for the controller to checkpoint (never commit unless explicitly asked).

## Approaches that failed and why

- Coverage-gap hunting is still a dead end: all 37 modules are at 100%.
- Adding a new `examples/run_*.py` script is unnecessary: all 46 primary registry keys already have a corresponding example script and README entry.
- The real gap was found by comparing the README's documented CLI flags against the live parser: 47 flags are documented but the parser accepts 112. Most undocumented flags are per-strategy parameter overrides (already covered by `--strategy-config` docs) and argparse auto-generated flags. The three added flags are the user-facing ones with no other documentation home.

## One precise next task

- If another session is requested, first re-run `pytest -q`, `python -m ruff check .`, `python -m black --check .`, and `python -m mypy quant_trading/` to confirm the tree is still green, then select a new bounded task.
- Candidate directions: document more of the remaining undocumented but user-facing CLI flags (e.g. `--rsi-period`, `--macd-fast`, `--stoch-k-period`, `--mc-method`, `--mc-confidence`, `--mc-seed`), each verified to run end-to-end under the mocked-network harness; or extend CLI/README coverage for an under-documented feature.
- Constraints: Do not modify tests to make them pass. Keep changes minimal and reversible. The `tests/test_readme_cli.py` and `tests/test_readme_cli_commands.py` guards enforce bidirectional consistency between the README CLI section and the live parser; any newly documented flag must be a real parser flag and its command must exit 0 (or 1 for documented error cases) with no traceback.

(End of file - total 49 lines)