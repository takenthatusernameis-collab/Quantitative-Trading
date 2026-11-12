## What changed (this session)

- Added `--regime-window` validation to the CLI, matching the established bounded-value
  pattern (see `--periods-per-year`, `--wf-windows`, `--wf-step-size`, etc.).
  - `examples/cli.py`: in `parse_args`, reject `args.regime_window < 2` with
    `ValueError("invalid --regime-window: the value must be at least 2 (got N)")`.
  - `tests/test_cli.py`: three new tests — `test_regime_window_below_two_is_rejected`
    (0/1/-3), `test_regime_window_two_is_accepted`, `test_regime_window_default_is_accepted`.
  - `README.md`: documented the new check in the "CLI Market Regime Analysis" section
    (error example uses the `$ ` prompt form, matching the other error examples, so it is
    not executed as a runnable README command).
- **Files changed:** `examples/cli.py`, `tests/test_cli.py`, `README.md`.

## Why this task (evidence)

- The prior handoff's "one precise next task" (`--wf-windows` validation) was ALREADY
  implemented in `HEAD` (examples/cli.py:1076). So there was no pending assignment; this
  was a freshly selected bounded, high-value task.
- `--regime-window` was the remaining unvalidated numeric CLI arg. Probes:
  - `--regime-window 0` or `1` → rolling std/mean are all-NaN → detector returns a silent,
    degenerate `unknown` regime (no error).
  - `--regime-window -1` → crashes deep inside pandas: `window must be an integer 0 or greater`.
  - `window 2` is the true minimum (need >=2 returns for a non-NaN std).

## What was actually verified (evidence)

- `python -m pytest -q -p no:cacheprovider tests/test_cli.py tests/test_readme_cli.py` → **270 passed, 1 skipped**
- `python -m pytest -q -p no:cacheprovider tests/test_readme.py tests/test_repository_integrity.py` → **40 passed**
- `python -m ruff check .` → **All checks passed**
- `python -m mypy quant_trading/` → **Success: no issues found in 38 source files**
- Manual CLI probe: `--regime --regime-window 0/1/-3` → clean `Error: invalid --regime-window ...`;
  `--regime --regime-window 2` → real regimes (`bull_high_vol`, 52 segments).

Note: full default suite (3521 passed, 1 skipped) was green at the start of this session
before any change; the change is isolated to CLI arg validation + docs, so only the
directly-affected modules were re-run.

## Unresolved / not completed

- None. Change is minimal, isolated, and verified.

## Failed approaches (do not repeat unchanged)

- None this session.

## Git state

- Branch `main`, up to date with `origin/main`. Changes are **uncommitted** (no commit was
  requested). Modified: `examples/cli.py`, `tests/test_cli.py`, `README.md`.

## One precise next task

- **`--days` has no validation.** `--days` (examples/cli.py:330, default 365) is used only
  when `--start` is absent: `start_date = end_date - timedelta(days=args.days)`
  (examples/cli.py:2362). A value `< 1` produces an invalid date window (`start >= end`):
  - `--days 0` → start == end → empty window → a silent, all-zero backtest (Sharpe 0.00,
    Total Return $0.00) instead of an actionable error.
  - `--days -5` → start > end → same silent all-zero result.
  Evidence: `python -m examples.cli --offline --days 0 --symbols AAPL` and `--days -5` both
  print `Sharpe Ratio: 0.00` with no error; `--days 120` returns a real result.
  Concrete step: in `parse_args`, add a check that rejects `args.days < 1` **only when
  `args.start` is None** (so an explicit `--start` that legitimately overrides `--days` is
  not falsely rejected), with message `invalid --days: the value must be at least 1 (got N)`.
  Add a `tests/test_cli.py` case (reject 0/-1 without `--start`; accept `--start` even with
  `--days 0`), and a README error example. Constraints: keep the `--start`-override case
  working; follow the existing `if args.X ...: raise ValueError(f"invalid --X: ...")`
  pattern; run `tests/test_cli.py` + `tests/test_readme_cli.py` + ruff + mypy.