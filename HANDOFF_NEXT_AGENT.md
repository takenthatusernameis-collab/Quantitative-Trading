## What changed (this session)

- Added `--synthetic-days` validation to the CLI, matching the established bounded-value
  pattern (see `--days`, `--regime-window`, `--periods-per-year`, `--wf-windows`, etc.).
  - `examples/cli.py`: in `parse_args`, reject `args.synthetic_days < 1` with
    `ValueError("invalid --synthetic-days: the value must be at least 1 (got N)")`.
  - `tests/test_cli.py`: three new tests in `TestParseArgs` —
    `test_synthetic_days_below_one_is_rejected` (0/-1/-365),
    `test_synthetic_days_one_is_accepted`, `test_synthetic_days_default_is_accepted`.
  - `README.md`: documented the check in the offline/synthetic section (error example uses
    the `$ ` prompt form, so it is not executed as a runnable README command).
- **Files changed:** `examples/cli.py`, `tests/test_cli.py`, `README.md`.

## Why this task (evidence)

- The previous handoff was **stale**: both its "next task" (`--days`) and the prior task
  (`--regime-window`) were ALREADY implemented and committed in `HEAD`
  (examples/cli.py:1085 and :1090). Verified by grep and by running their tests.
- A genuine remaining gap was found: `--synthetic-days` has no CLI validation.
  Root cause: `create_config` assigns `config.data.synthetic_days = args.synthetic_days`
  **after** `Config()` is built (examples/cli.py:1492), which bypasses the
  `DataConfig.__post_init__` check `synthetic_days >= 1` (quant_trading/config/settings.py:95).
  Probes before the fix:
  - `--synthetic-days 0` → 1-row/empty series → silent all-zero backtest, **exit 0**.
  - `--synthetic-days -1` / `-365` → raw `OverflowError` traceback deep in pandas, exit 1.
  - `--synthetic-days 1` / `365` → run normally, exit 0.

## What was actually verified (evidence)

- `python -m pytest -q -p no:cacheprovider tests/test_cli.py -k "synthetic_days or days or regime"`
  → **24 passed**.
- Manual CLI probes after the fix:
  - `--synthetic-days 0 / -1 / -365` → `Error: invalid --synthetic-days: the value must be
    at least 1 (got N)`, exit 1.
  - `--synthetic-days 1 / 365` → normal run, exit 0.
- `python -m pytest -q -p no:cacheprovider tests/test_repository_integrity.py tests/test_config.py`
  → **138 passed**.
- `python -m pytest -q -p no:cacheprovider tests/test_readme.py tests/test_readme_cli.py`
  → passed (included in the 97 passed below).
- `python -m py_compile examples/cli.py tests/test_cli.py` → OK; no added line exceeds the
  100-char ruff limit (checked programmatically).

### Environment caveat (important for the next session)

This container is a **minimal env** (Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0).
`ruff`, `mypy`, `matplotlib`, and `scikit-optimize` are **NOT installed**, so the prior
handoff's `ruff`/`mypy` commands cannot run here and some tests fail for environmental
reasons only. Confirmed pre-existing, unrelated to this change:
- `tests/test_cli.py`: **267 passed, 9 failed** — all 9 failures are in `TestHtmlReportFlag`
  (`--report`), which needs matplotlib.
- `tests/test_readme_cli_commands.py`: **97 passed, 5 failed** — 3 bayesian-optimization
  commands need scikit-optimize; 2 `--report` commands need matplotlib.
  Verified messages: `Error: matplotlib is required for chart generation...` and
  `Error: BayesianOptimizer requires scikit-optimize...`.

## Unresolved / not completed

- None for this task. The change is minimal, isolated, and verified.
- Not runnable in this env (no ruff/mypy): lint/type checks. The change follows the existing
  formatting/type patterns exactly.

## Failed approaches (do not repeat unchanged)

- None this session.

## Git state

- Branch `main`, up to date with `origin/main`. Changes are **uncommitted** (no commit was
  requested). Modified: `examples/cli.py`, `tests/test_cli.py`, `README.md`.
- Note: the base commit already contained the prior sessions' `--regime-window` and `--days`
  work; this session adds `--synthetic-days` on top.

## One precise next task

- **`--synthetic-seed` has no validation.** `--synthetic-seed` (examples/cli.py:407, default
  42) is assigned to `config.data.synthetic_seed` (examples/cli.py:1494) and consumed by
  `create_synthetic_data` → `np.random.seed(seed)` (quant_trading/data/synthetic.py:77).
  `np.random.seed` accepts only `0 <= seed <= 2**32 - 1`; outside that range the run fails
  **late** with `Error running backtest: Seed must be between 0 and 2**32 - 1` (exit 1)
  instead of a clean parse-time error.
  - Evidence: `--synthetic-seed -1` and `--synthetic-seed 4294967296` both print
    `Error running backtest: Seed must be between 0 and 2**32 - 1` (exit 1);
    `--synthetic-seed 4294967295` (2**32-1) is accepted (exit 0).
  - Concrete step: in `parse_args`, add a check rejecting `args.synthetic_seed < 0` or
    `args.synthetic_seed > 2**32 - 1`, with message
    `invalid --synthetic-seed: the value must be between 0 and 4294967295 (got N)`.
  - Add `tests/test_cli.py` cases (reject -1 and 4294967296; accept 0 and 4294967295 and the
    default 42), and a README error example.
  - Constraints: follow the existing `if args.X ...: raise ValueError(f"invalid --X: ...")`
    pattern; keep the check in `parse_args` (not in the library) to match the established
    CLI-validation convention; run `tests/test_cli.py` (expect the 9 matplotlib-only
    `TestHtmlReportFlag` failures) + `tests/test_readme.py` + `tests/test_repository_integrity.py`.