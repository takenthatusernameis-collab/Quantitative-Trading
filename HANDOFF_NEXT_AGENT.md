## What changed (this session)

- Added `--mc-seed` validation to the CLI, matching the established bounded-value
  pattern (see `--mc-simulations`, `--synthetic-seed`, `--days`, etc.).
  - `examples/cli.py`: in `parse_args`, reject `args.mc_seed < 0` (only when the
    value is not `None`, since `None` means "nondeterministic") with
    `ValueError("invalid --mc-seed: the value must be at least 0 (got N)")`.
  - `tests/test_cli.py`: five new tests in `TestParseArgs` —
    `test_mc_seed_negative_is_rejected` (-1/-100),
    `test_mc_seed_zero_is_accepted`, `test_mc_seed_positive_is_accepted`,
    `test_mc_seed_large_is_accepted` (2**40), `test_mc_seed_default_is_accepted`
    (`None`).
  - `README.md`: documented the check in the Monte Carlo section (the error
    example uses the `$ ` prompt form, so it is not executed as a runnable
    README command).
- **Files changed:** `examples/cli.py`, `tests/test_cli.py`, `README.md`.

## Why this task (evidence)

- The previous handoff's "next task" (`--synthetic-seed` validation) was already
  implemented and committed in `a891f0d`, and a matching library-level check was
  added in `aa615ab` (`quant_trading/config/settings.py` `DataConfig`). Both were
  verified before starting: `tests/test_cli.py -k "synthetic_days or synthetic_seed
  or days or regime"` → 28 passed.
- A genuine remaining gap was found: `--mc-seed` had no validation.
  Root cause: `args.mc_seed` is passed straight to
  `np.random.default_rng(random_state)` (examples/cli.py:2247 →
  quant_trading/monte_carlo/simulator.py:400). `default_rng` accepts any
  non-negative integer (arbitrary size) but rejects negatives with
  `ValueError("expected non-negative integer")`.
  Probe before the fix:
  - `--monte-carlo --mc-seed -1` → ran the **entire backtest first**, then printed
    `Error running backtest: expected non-negative integer`, exit 1. (The error is
    caught by the broad `except (ValueError, RuntimeError, KeyError)` at
    examples/cli.py:2534, so the user gets no flag name and wastes the run.)
  - `--monte-carlo --mc-seed 0` / `42` / `2**40` → normal run, exit 0.

## What was actually verified (evidence)

- `python -m pytest -q -p no:cacheprovider tests/test_cli.py -k "mc_seed or
  synthetic_seed or mc_simulations or monte_carlo"` → **23 passed**.
- `python -m pytest -q -p no:cacheprovider tests/test_cli.py::TestParseArgs`
  → **75 passed**.
- `python -m pytest -q -p no:cacheprovider tests/test_repository_integrity.py
  tests/test_config.py tests/test_readme.py` → **160 passed**.
- `python -m py_compile examples/cli.py tests/test_cli.py` → OK.
- Manual CLI probes after the fix:
  - `--monte-carlo --mc-seed -1` → `Error: invalid --mc-seed: the value must be at
    least 0 (got -1)`, exit 1, **before** the backtest runs.
  - `--monte-carlo --mc-seed 0 --days 30 --offline` → normal run, exit 0.

### Environment caveat (important for the next session)

This container is a **minimal env** (Python 3.14.4, pandas 3.1.1, numpy 2.5.4,
pytest 9.2.0). `ruff`, `mypy`, `matplotlib`, and `scikit-optimize` are **NOT
installed**, so lint/type checks cannot run and some tests fail for environmental
reasons only. Confirmed pre-existing, unrelated to this change:
- `tests/test_cli.py`: 9 failures in `TestHtmlReportFlag` (`--report`) need
  matplotlib.
- `tests/test_readme_cli_commands.py`: 5 failures need scikit-optimize (3) or
  matplotlib (2).

## Unresolved / not completed

- None for this task. The change is minimal, isolated, and verified.
- Not runnable in this env (no ruff/mypy): lint/type checks. The change follows
  the existing formatting/type patterns exactly.

## Failed approaches (do not repeat unchanged)

- None this session.

## Git state

- Branch `main`. The `--mc-seed` change was committed this session. See
  `git log --oneline -3`.

## One precise next task

- **`--risk-free-rate` accepts non-finite values and silently corrupts metrics.**
  `args.risk_free_rate` is assigned to `config.backtest.risk_free_rate`
  (examples/cli.py:1512) and consumed by the Sharpe/Sortino calculations. It has
  no validation at the CLI or in `BacktestConfig` (quant_trading/config/settings.py
  validates `initial_capital`, `commission`, `slippage`, `periods_per_year` but
  **not** `risk_free_rate`).
  - Evidence (before any fix):
    `python examples/cli.py --offline --strategy rsi --days 120 --symbols AAPL
    --risk-free-rate nan` → prints `Sharpe Ratio: nan` and exits **0** (silent
    corruption). `--regime-vol-threshold nan` likewise produces a bogus single
    regime segment and exits 0.
  - Concrete step: in `parse_args`, when `args.risk_free_rate is not None`, reject
    non-finite values with a message like
    `invalid --risk-free-rate: the value must be finite (got N)` (use
    `math.isfinite`). Optionally apply the same finite check to
    `--regime-vol-threshold` and `--regime-return-threshold` (both default to 0.0
    meaning "auto", so only reject `nan`/`inf`).
  - Add `tests/test_cli.py` cases (reject `nan`/`inf`/`-inf`; accept a normal value
    and the `None` default) and a README note/example (use the `$ ` prompt form so
    it is not executed).
  - Constraints: keep the check in `parse_args` (not the library) to match the
    established CLI-validation convention; do not reject negative rates unless you
    decide that is in scope (negative real rates are legitimate, so prefer a
    finite-only check). Run `tests/test_cli.py::TestParseArgs` +
    `tests/test_repository_integrity.py` + `tests/test_readme.py`.