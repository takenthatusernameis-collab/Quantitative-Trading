## What changed (this session)

- Added `examples/run_sensitivity.py`, an offline, deterministic demo for the
  previously-documented-but-unexercised `quant_trading.optimization.sensitivity`
  module. It runs a small grid search over MA fast/slow periods on seeded
  synthetic data, then feeds the scores into `prepare_sensitivity_data`,
  `create_1d_sensitivity_plot`, `create_2d_sensitivity_heatmap`, and
  `generate_sensitivity_report_html`, writing a standalone HTML report to
  `examples/output/sensitivity_report.html`.
- Documented the new script in the README "Example Scripts" section
  (`README.md`), right after the `run_optimization.py` block.
- Added `examples/output/` to `.gitignore` so the generated HTML report is
  not committed.

## What was actually verified (evidence)

- `python3 examples/run_sensitivity.py` exits 0 cleanly; prints the sensitivity
  summary table and reports the 1D plot / 2D heatmap / HTML report sizes.
- `python3 -m pytest -q` -> `3819 passed, 142 deselected` (was 3818, +1 from the
  new script's documented-invocation test in `tests/test_example_scripts_run.py`).
- Targeted: `pytest tests/test_readme.py::TestReadmeExampleScripts
  tests/test_example_scripts_run.py tests/test_examples_smoke.py
  tests/test_repository_integrity.py tests/test_sensitivity.py -q`
  -> 104 passed, 135 deselected.
- The existing `TestReadmeExampleScripts` guard (`tests/test_readme.py:255-270`)
  already enforces bidirectional README<->script sync, so the new script is
  covered without a new guard: it detects both a missing README entry and a
  README entry pointing at a nonexistent script.
- `python3 -m ruff check examples/run_sensitivity.py` -> All checks passed.
- `python3 -m black --check examples/run_sensitivity.py` -> unchanged.
- `python3 -m mypy quant_trading/ examples/` -> Success, no issues in 96 files.
  (Note: `mypy --disallow-untyped-defs` on `examples/run_sensitivity.py`
  flags the untyped `df` param of `_print_summary_table`, exactly matching
  the pre-existing pattern in `examples/run_parabolic_sar.py:29`; example
  scripts are not in the project's `disallow_untyped_defs` override list, so
  this is consistent with the repo convention, not a regression.)

## What remains unresolved

Nothing for this change. The suite is green, ruff/black/mypy clean on the
changed files, and the working tree contains only the intended additions.

## Failed or corrected approaches this session

- First write of `examples/run_sensitivity.py` introduced a stray character on
  the `sys.path.insert(...)` line that made the file fail to parse; rewrote the
  line and re-verified with `ast.parse`.
- The `_print_summary_table` helper initially tried to derive min/max from
  `mean ± std`, which is not meaningful; replaced it with the summary_df's own
  `mean_score`, `score_std`, `sensitivity_range`, `n_values` columns.
- Moved a late `import pandas as pd` to the module top to match the other
  example scripts.

## One precise next task

No further work required for correctness. A future session need only re-run
`python3 -m pytest -q` and `mypy quant_trading/ examples/` to confirm no
regression. If more coverage is desired, the only remaining gaps are the same
defensive branches noted in the prior handoff (engine.py TYPE_CHECKING imports
and guards).

(End of file - total 59 lines)