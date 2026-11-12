## What changed (this session)

- Added parse-time finite-value validation to the CLI, following the established
  `parse_args` convention (see `--mc-seed`, `--slippage`, `--commission`).
  - `examples/cli.py`: imported `math`; in `parse_args`, reject non-finite
    `--risk-free-rate` (only when not `None`, since `None` means "use config
    value") with
    `ValueError("invalid --risk-free-rate: the value must be finite (got N)")`.
    Also reject non-finite `--regime-vol-threshold` and
    `--regime-return-threshold` (both default to `0.0` meaning "auto", so only
    `nan`/`inf` are rejected).
  - `tests/test_cli.py`: six new tests in `TestParseArgs` —
    `test_risk_free_rate_non_finite_is_rejected` (`nan`/`inf`/`-inf`),
    `test_risk_free_rate_finite_is_accepted` (incl. negative rate),
    `test_risk_free_rate_default_is_accepted` (`None`),
    `test_regime_thresholds_non_finite_are_rejected`,
    `test_regime_thresholds_default_is_accepted` (`0.0`).
    Non-finite cases use the `--flag=value` argv form because a bare `-inf`
    token is consumed by argparse as an option, not a value.
  - `README.md`: documented the finite checks in the config-override section
    (risk-free rate) and the market-regime section (thresholds), using the `$ `
    prompt form so the error examples are not executed as commands.
- **Files changed:** `examples/cli.py`, `tests/test_cli.py`, `README.md`.

## Why this task (evidence)

- The previous handoff's "next task" was exactly this gap. Root cause confirmed:
  `args.risk_free_rate` is assigned to `config.backtest.risk_free_rate`
  (examples/cli.py) and consumed by the Sharpe/Sortino calculations; neither the
  CLI nor `BacktestConfig` checked finiteness. `BacktestConfig.__post_init__`
  validates `initial_capital`, `periods_per_year`, `commission`, `slippage` but
  **not** `risk_free_rate`.
- Probe before the fix (from the previous handoff): `--risk-free-rate nan` printed
  `Sharpe Ratio: nan` and exited 0 (silent corruption).
- The regime thresholds (`--regime-vol-threshold`, `--regime-return-threshold`)
  had the same gap: `nan`/`inf` produced a bogus single regime segment and exit 0.

## What was actually verified (evidence)

- `python -m pytest -q -p no:cacheprovider tests/test_cli.py -k "risk_free_rate or
  regime_threshold"` → **9 passed**.
- `python -m pytest -q -p no:cacheprovider tests/test_cli.py::TestParseArgs`
  → **80 passed**.
- `python -m pytest -q -p no:cacheprovider tests/test_repository_integrity.py
  tests/test_readme.py tests/test_config.py` → **160 passed**.
- `python -m py_compile examples/cli.py tests/test_cli.py` → OK.
- Manual CLI probes after the fix:
  - `--risk-free-rate nan` → `Error: invalid --risk-free-rate: the value must be
    finite (got nan)`, exit 1, before the run.
  - `--regime-vol-threshold inf` → `Error: invalid --regime-vol-threshold: the
    value must be finite (got inf)`, exit 1.
  - `--risk-free-rate 0.05 --regime-vol-threshold 0.2 --days 120 --offline` →
    normal run, exit 0.
- Full `tests/test_cli.py` → **285 passed, 9 failed**. The 9 failures are the
  pre-existing `TestHtmlReportFlag` (`--report`) cases that require matplotlib,
  which is not installed in this minimal env (confirmed
  `import matplotlib` → `ModuleNotFoundError`). Unrelated to this change.

### Environment caveat (unchanged)

Minimal env (Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0).
`ruff`, `mypy`, `matplotlib`, `scikit-optimize` are **NOT** installed, so
lint/type checks cannot run and the 9 matplotlib report tests + 5
`tests/test_readme_cli_commands.py` tests fail for environmental reasons only.

## Unresolved / not completed

- None for this task. The change is minimal, isolated, and verified.
- Lint/type checks not run (no ruff/mypy). The change follows existing
  formatting/type patterns exactly.

## Failed approaches (do not repeat unchanged)

- Passing `-inf` as a separate argv token in tests: argparse consumes a bare
  `-inf` as an option (`SystemExit: expected one argument`). Use the
  `--flag=value` form for values starting with `-`.

## Git state

- Branch `main`. The `--risk-free-rate` / regime-threshold change was committed
  this session. See `git log --oneline -3`.

## One precise next task

- **Non-finite float strategy parameters are silently accepted and corrupt runs.**
  The strategy constructors validate positivity with `<= 0`, which lets `nan`
  and `inf` through (`nan <= 0` and `inf <= 0` are both `False`).
  - Evidence gathered this session:
    - Source: `quant_trading/strategies/examples.py:566` uses
      `if self.std_dev <= 0`, `:918` uses `if self.multiplier <= 0` (and similar
      guards at the ATR/Keltner/SuperTrend/etc. constructors).
    - Library: `BollingerBandsStrategy(period=20, std_dev=float('nan'))` →
      constructs OK (`s.std_dev` is `nan`).
      `AverageTrueRangeStrategy(period=14, atr_multiplier=float('inf'))` and
      `... = float('nan')` → both construct OK.
    - CLI: `python examples/cli.py --offline --strategy bb --bb-period 20
      --bb-std nan --days 60 --symbols AAPL` → prints an all-zero result
      (`Profit Factor: 0.00`, `Sortino Ratio: 0.00`, ...) and exits **0** (silent
      degenerate run, no error, no trades).
  - Concrete step: reject non-finite float parameters at the **library
    constructor** level (root cause, also protects direct API users), e.g. change
    `if self.std_dev <= 0:` to
    `if not math.isfinite(self.std_dev) or self.std_dev <= 0:` in
    `quant_trading/strategies/examples.py` (import `math`), and apply the same
    finite guard to the other float params guarded by `<= 0`
    (`multiplier`/`atr_multiplier`, `st_multiplier`, `kc_multiplier`, etc.).
    Integer `period` params are unaffected by nan/inf, but a finite guard is
    harmless there; prefer the minimal float-only change.
  - Add tests in `tests/test_strategy*.py` (or the existing strategy test file —
    locate it with `glob tests/**/*strateg*`) covering `nan`/`inf` rejection and
    normal-value acceptance for the affected strategies.
  - Constraints: do **not** reject negative values (the existing `<= 0` rule
    already covers those); only add the finite check. Keep changes minimal and
    localized. Run the strategy test file plus
    `tests/test_repository_integrity.py` + `tests/test_config.py`.