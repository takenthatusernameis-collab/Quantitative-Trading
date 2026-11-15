## What changed (this session)
- Added a "Parameter Sensitivity Analysis" bullet to the README Features list
  (`README.md:17`), advertising the previously-documented-but-unlisted
  `quant_trading.optimization.sensitivity` module. The module was exported via
  `quant_trading.optimization.__init__` and listed in the project tree, but the
  user-facing Features bullet omitted it — a silent gap for every other
  optimization feature.
- Added a regression guard mirroring the existing
  `test_readme_features_list_advertises_all_optimizers` pattern:
  `test_readme_features_list_advertises_sensitivity_analysis` in
  `tests/test_repository_integrity.py:375-410`. It asserts that every name in
  `quant_trading.optimization.sensitivity.__all__` is mentioned in the README
  Features block (scanning the whole block, not just the Parameter Optimization
  line, because the sensitivity bullet sits on its own line).

## What was actually verified (evidence)
- `python3 -m pytest -q` -> `3818 passed, 140 deselected` (was 3817, +1 new test).
- Targeted: `pytest tests/test_repository_integrity.py tests/test_sensitivity.py
  tests/test_readme.py tests/test_readme_cli.py tests/test_readme_cli_commands.py -q`
  -> 149 passed, 3 deselected.
- Negative control: removing the whole sensitivity bullet from README.md in
  memory makes the new guard fail with the expected message; restoring it
  passes. Proves the guard detects the regression it guards against.
- `python3 -m ruff check quant_trading/ tests/test_repository_integrity.py
  tests/test_sensitivity.py` -> All checks passed.
- `python3 -m black --check quant_trading/ tests/test_repository_integrity.py
  tests/test_sensitivity.py` -> 41 files unchanged.
- `python3 -m mypy tests/test_repository_integrity.py --disallow-untyped-defs`
  -> Success. Note: `test_sensitivity.py` has 15 pre-existing
  `no-untyped-def` errors (lines 114-184, untouched this session); it is not in
  the project's mypy `disallow_untyped_defs` override list, so those are
  pre-existing and not a regression from this change.

## What remains unresolved
Nothing for this change. The suite is green, ruff/black/mypy clean on the
changed files, and the working tree contains only the intended README bullet +
guard.

## Failed or corrected approaches this session
- First attempt at the guard used `readme.index("\n", features_start)` to bound
  the scan to a single line, which missed the sensitivity bullet on its own
  line. Corrected to `readme.index("\n## ", features_start)` so the whole
  Features block is scanned.

## One precise next task
No further work required for correctness. A future session need only re-run
`python3 -m pytest -q` and
`mypy tests/test_repository_integrity.py --disallow-untyped-defs` to confirm no
regression. If more coverage is desired, the only remaining gaps are the same
defensive branches noted in the prior handoff (engine.py TYPE_CHECKING imports
and guards).