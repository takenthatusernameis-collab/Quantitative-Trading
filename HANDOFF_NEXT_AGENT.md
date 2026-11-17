## What changed (this session)

- Picked up handoff option 2 from the prior session: added explicit coverage for
  the `--report-no-charts` path (README.md:710, 717-719) asserting it stays
  green *without* matplotlib. The prior harness only *implicitly* covered it
  (it is not skip-marked, so it ran and passed whenever matplotlib happened to
  be installed), with no test that it does not import matplotlib.
- New test `TestExplicitCombinedAndStrategyConfigErrors.test_report_no_charts_runs_without_matplotlib`
  in `tests/test_readme_cli_commands.py`:
  - Patches `quant_trading.backtest.report.MATPLOTLIB_AVAILABLE = False` to
    simulate a core-only environment.
  - Runs `--offline --report <f> --report-no-charts` and asserts exit 0, the
    HTML file is written, and no traceback — i.e. the chart-free path does not
    touch matplotlib.
  - Runs the same invocation shape *without* `--report-no-charts` and asserts
    exit 1, no file written, no traceback, and a one-line error mentioning
    `matplotlib` — proving the two paths diverge cleanly.
  - Restores the flag in a `finally` so other tests are unaffected.
- No production code changed.

## What was actually verified (evidence)

- New test alone: `pytest tests/test_readme_cli_commands.py::TestExplicitCombinedAndStrategyConfigErrors::test_report_no_charts_runs_without_matplotlib -v`
  -> **1 passed**.
- README CLI module: `pytest tests/test_readme_cli_commands.py -q -rs`
  -> **120 passed, 3 deselected** (was 119/3; +1 is the new test).
- Full default suite: `pytest -q` -> **4055 passed, 142 deselected** (was 4054;
  +1 is the new test). No failures.
- Formatting/lint/typecheck on the edited file:
  - `black --check tests/test_readme_cli_commands.py` -> unchanged.
  - `ruff check tests/test_readme_cli_commands.py` -> All checks passed.
  - `mypy tests/test_readme_cli_commands.py` -> Success: no issues found.
- Manual sanity: with `MATPLOTLIB_AVAILABLE = False`, charted command exits 1
  with `Error: matplotlib is required for chart generation...`; chart-free
  command exits 0 and writes the HTML file.

## What remains unresolved / not verified

- The optional extras (`matplotlib`, `scikit-optimize`) are installed in
  *this* session's user site only; the repo still must not assume they are
  present in a fresh checkout.
- `--combined` commands remain marked `slow` (deselected by default).
- Network-marked tests deselected as usual.

## Approaches that failed

- None.

## One precise next task

The optional-extra README-command failures are resolved, the chart-free report
path is explicitly covered, and the full default suite is green (4055 passed).
If continuing, pick one of:

1. Add a CI check that runs `pytest` in a **core-only** environment to lock in
   that the skip logic keeps the suite green without optional extras (e.g. a
   GitHub Actions matrix leg with `pip install -e .` and no extras, asserting
   exit 0). Relevant files: `.github/workflows/` +
   `tests/test_readme_cli_commands.py`.
2. Extend the new test to also assert the other documented chart-free flags
   (`--report-no-trades`, `--report-no-monthly`, `--report-no-rolling`,
   README.md:717-719) do not require matplotlib — currently only
   `--report-no-charts` is covered. Evidence to build on:
   `quant_trading/backtest/report.py:729-730` (`if config.include_charts:
   _check_matplotlib()`) and `tests/test_readme_cli_commands.py`.

(End of file - total 68 lines)