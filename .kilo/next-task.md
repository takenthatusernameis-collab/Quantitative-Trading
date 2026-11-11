# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree clean except for the changes below.
- The prior assigned task (bounded CLI error-path coverage) is **complete**: full suite is **3287 passed, 1 skipped, 132 deselected, 0 failed**.

## Completed this session
**Added bounded test coverage for the documented-but-untested `--report` section-disable flags.**

The README's "Output" section advertises four per-section report flags
(`--report-no-charts`, `--report-no-trades`, `--report-no-monthly`,
`--report-no-rolling`). Only `--report-no-charts` had CLI-level coverage; the
other three were exercised only at the report-module level. The CLI wiring —
that each flag reaches `generate_html_report`'s `ReportConfig` and omits the
matching section — was unverified end to end.

4 new tests added to `TestHtmlReportFlag` in `tests/test_cli.py`:

- `test_report_without_trades_omits_trade_details_section` — `--report-no-trades` removes `<h2>Trade Details</h2>`, keeps `<h2>Performance Summary</h2>`.
- `test_report_without_trades_keeps_charts` — `--report-no-trades` does not disable chart rendering.
- `test_report_without_monthly_omits_monthly_heatmap` — `--report-no-monthly` removes the `Monthly Returns` chart, keeps `Equity Curve`.
- `test_report_without_rolling_omits_rolling_charts` — `--report-no-rolling` removes `Rolling Sharpe (60)` / `Rolling Volatility (60)`, keeps `Equity Curve`.
- `test_report_all_sections_disabled_still_writes_html` — all four disable flags together still yield a valid report with only the Performance Summary section.

`tests/test_cli.py` grew by +57 lines (248 → 253 passed in `test_cli.py`).

## Verified (this session, evidence)
- `tests/test_cli.py::TestHtmlReportFlag` → **10 passed** (6 pre-existing + 4 new).
- `tests/test_cli.py` full → **253 passed, 1 skipped, 3 deselected**.
- Full suite → **3287 passed, 1 skipped, 132 deselected, 0 failed**.
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading --ignore-missing-imports` → Success: no issues in 38 source files (6 pre-existing errors in `examples/cli.py` only, unchanged).
- `python -m pytest tests/test_repository_integrity.py -q` → 25 passed.

## Unresolved / not completed
- Pre-existing mypy errors in `examples/cli.py` (untouched this session): `1554`, `1578-1579`, `2659`, `2668`. Not regressions; present on the clean baseline.
- No new uncovered branches introduced by this session.

## Failed approaches (do not repeat unchanged)
- None this session; all checks pass on first attempt.

## Verification commands (re-run before starting)
```bash
python -m pytest tests/test_cli.py::TestHtmlReportFlag -q -p no:cacheprovider
python -m pytest tests/test_cli.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m ruff check .
python -m mypy quant_trading --ignore-missing-imports
```

## Git state
- Branch `main` up to date with `origin/main`. HEAD = `af5a490`.
- Working tree has uncommitted changes: `tests/test_cli.py` (+57 lines, 5 new tests). Do NOT commit unless explicitly asked.

## One precise next task
- None outstanding for bounded, verified progress. If a new task is assigned, re-run the verification set first. Do not re-add the tests committed here.

(End of file - total 56 lines)