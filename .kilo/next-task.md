# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree has uncommitted test-only changes (see HANDOFF_NEXT_AGENT.md).
- `pytest`, `pandas`, `numpy`, `yfinance`, `scikit-optimize`, `ruff`, `black`, `mypy` are installed in the session-local pip environment at `/home/runner/work/_temp/kilo-home/.local/bin` — add that directory to `PATH` before running any test/lint/typecheck command.

## Completed this session
**Fixed 8 deterministic test failures caused by missing `@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, ...)` decorators on tests that exercise `generate_html_report` with charts enabled.** All 8 were `ImportError: matplotlib is required for chart generation` — environment-only, not a code defect. Marked the tests to skip when the optional `reporting` extra is absent, matching their sibling tests.

- `tests/test_backtest_report.py`: +3 skip decorators.
- `tests/test_cli.py`: +1 import, +4 skip decorators on `TestHtmlReportFlag`.
- `tests/test_readme_cli_commands.py`: +1 import, +skip marks appended to every `--report` README command in `_readme_commands()`.

## Verified (this session, evidence)
- `python -m pytest tests/test_backtest_report.py tests/test_cli.py::TestHtmlReportFlag tests/test_readme_cli_commands.py -q -p no:cacheprovider` → **121 passed, 24 skipped** (was 8 failed).
- Full suite `python -m pytest tests/ -q -p no:cacheprovider -m "not slow and not network"` → **2999 passed, 25 skipped, 132 deselected, 0 failed** (was 8 failed).
- `python -m ruff check .` → **All checks passed!**
- `python -m black --check tests/test_backtest_report.py tests/test_readme_cli_commands.py` → unchanged. `tests/test_cli.py` has pre-existing black issues at lines 555/581 (verified on baseline via `git stash`); out of scope.

## Unresolved / not completed
- Pre-existing black formatting issues in `tests/test_cli.py` (lines 555, 581) — unrelated to this session.
- `yfinance_provider.py:85`, `engine.py:82-84` — environment-only or `TYPE_CHECKING`; not logic gaps.

## One precise next task
- None outstanding. If a new task is assigned, re-run the verification set first:
  `python -m pytest tests/test_backtest_report.py tests/test_cli.py::TestHtmlReportFlag tests/test_readme_cli_commands.py -q -p no:cacheprovider`,
  `python -m pytest tests/ -q -p no:cacheprovider -m "not slow and not network"`,
  `python -m ruff check .`,
  `python -m black --check tests/test_backtest_report.py tests/test_readme_cli_commands.py`.

## Git state
- Working tree has uncommitted test-only changes (3 files). Do NOT commit unless explicitly asked.

(End of file)