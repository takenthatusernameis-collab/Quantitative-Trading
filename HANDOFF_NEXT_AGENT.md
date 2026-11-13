## What changed (this session)

- Closed the nan-acceptance hole in `quant_trading/config/settings.py`
  `__post_init__` guards (the same class of bug fixed last session in
  `RiskManager`/`PositionLimit`/`PortfolioLimit`):
  - `DataConfig.__post_init__` line 96: `if self.synthetic_days < 1:` →
    `if not math.isfinite(self.synthetic_days) or self.synthetic_days < 1:`
    (message now reads "must be at least 1 and finite").
  - `DataConfig.__post_init__` line 101: `if self.synthetic_seed < 0 or ...` →
    `if not math.isfinite(self.synthetic_seed) or self.synthetic_seed < 0
    or self.synthetic_seed > 2**32 - 1:`.
  - `RiskConfig.__post_init__` line 468: `if self.max_leverage < 1e-9:` →
    `if not math.isfinite(self.max_leverage) or self.max_leverage < 1e-9:`.
  - `PortfolioConfig.__post_init__` line 578: `if self.max_positions < 1:` →
    `if not math.isfinite(self.max_positions) or self.max_positions < 1:`.
  Range semantics unchanged; only non-finite values are now rejected.
- Tests: extended `tests/test_config.py` parametrizations with
  `float("nan")`/`float("inf")`/`float("-inf")` for `synthetic_days`,
  `synthetic_seed`, `max_leverage`, and `max_positions`.
- **Files changed:** `quant_trading/config/settings.py`,
  `tests/test_config.py`. Changes are **not committed**.

## What was actually verified (evidence)

- Library probes: `DataConfig(synthetic_days=nan)`,
  `DataConfig(synthetic_seed=nan)`, `RiskConfig(max_leverage=nan)`,
  `PortfolioConfig(max_positions=nan)` all raise `ValueError` with the
  expected `invalid <field>` prefix; valid finite values still construct.
- `python -m py_compile` on changed files: OK.
- `pytest tests/test_config.py tests/test_repository_integrity.py`: **168
  passed**.
- Full suite: **3547 passed, 17 failed, 131 skipped, 136 deselected** (up from
  3535 passed last session — the +12 are the new parametrized cases). All 17
  failures are pre-existing environmental ones (matplotlib not installed ->
  test_backtest_report.py + TestHtmlReportFlag; scikit-optimize not
  installed -> bayesian README CLI commands). None touch the changed code.

### Environment caveat (unchanged)

Minimal env (Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0).
`ruff`, `mypy`, `matplotlib`, `scikit-optimize` are **NOT** installed, so
lint/type checks cannot run and the 17 tests above fail for environmental
reasons only.

## Unresolved / not completed

- Lint/type checks not run (no ruff/mypy).
- Not committed (no explicit request).

## Failed approaches (do not repeat unchanged)

- None this session.

## One precise next task

- No remaining nan-acceptance holes of this exact kind were found in the
  config layer. If a follow-up is wanted, the next bounded task is to run
  `ruff check .` / `mypy quant_trading/` once the dev extras are installed
  (`pip install -e ".[dev]"`), to clean up any lint/type issues the minimal
  environment cannot surface. Constraints: do not change range semantics;
  only fix genuine lint/type errors.

(End of file - total 68 lines)