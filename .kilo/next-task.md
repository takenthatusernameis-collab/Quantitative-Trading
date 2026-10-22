# Next Task

## Repository state

- `quant_trading/` is the library: backtest engine and metrics, strategies and
  the strategy registry, data providers, risk, portfolio, optimization, regime
  detection, Monte Carlo and trade analysis.
- `examples/cli.py` is the user-facing command line interface; the README
  documents it as *the* primary entry point. `examples/run_*.py` are the
  per-strategy example scripts.
- Checks: `python -m pytest -q`, `python -m ruff check .`,
  `python -m black --check .`, `python -m mypy quant_trading examples`.
- **The system `python3` has no dependencies installed.** Use the venv at
  `/home/runner/work/_temp/kilo-tmp/venv`
  (`/home/runner/work/_temp/kilo-tmp/venv/bin/python -m pytest -q`). Recreating
  it costs several minutes: `requirements.txt` plus the `dev` extra of
  `pyproject.toml` (which contains `scikit-optimize`).
- Baseline at the start of the current session: **1950 passed, 0 failed**;
  ruff clean, black clean, mypy clean in 56 files.

## This session (2026-10-22) — CLI user errors: assigned task verified, the residual paths closed, and a zero-step hang fixed

### What changed

The task assigned at the end of the previous section was to make the CLI
report user errors as a one-line message instead of a traceback, on four
paths. **That work was already committed** (`ed403d3`: `examples/cli.py`,
`tests/test_cli.py`, `tests/test_examples_smoke.py`, `README.md`) but the
handoff file was never updated, so this session verified it and then closed
the residual paths of the same defect class.

1. **Verified the assigned task.** The four paths (unknown strategy, missing
   `--config`, missing `--strategy-config`, unwritable `--output`) are clean
   messages with the exit code 1. The `--provider`, `--interval`,
   `--fast-period` and `--mc-simulations` flags still exit the way they did.
   The committed tree passes the full suite: **1950 passed, 0 failed**.
2. **`examples/cli.py::create_strategy` — a `--strategy-config` file with the
   wrong *content* no longer produces a traceback.** Four input shapes reached
   the strategy constructor and blew up there:
   | File content | Old failure |
   | --- | --- |
   | `- a\n- b\n` (not a mapping) | `AttributeError: 'list' object has no attribute 'get'` |
   | `type: rsi\nparameters: 5\n` | `TypeError: argument after ** must be a mapping, not int` |
   | `type: rsi\nparameters:\n  nosuchparam: 5\n` | `TypeError: RSIStrategy.__init__() got an unexpected keyword argument` |
   | `type: rsi\nparameters:\n  period: abc\n` | `TypeError: '<=' not supported between instances of 'str' and 'int'` |
   The CLI now checks that the document is a mapping, that `parameters` is a
   mapping, and converts a `TypeError`/`AttributeError` from the factory into a
   `ValueError` (which `main()` already turns into `Error: ...` + exit code 1).
   The library is untouched: `Strategy.from_config` still raises what it
   raised.
3. **`examples/cli.py::parse_range` + `_validate_range_arguments` — a
   `--*-range` argument with a step of zero no longer hangs the process.**
   `--optimize --ma-fast-range 5,20,0` looped forever
   (`quant_trading/optimization/base.py:91-93`: `v += self.step` never
   advances, so the list grows until the process is killed). The step is now
   rejected before the run starts and the message names the offending flag:
   `Error: invalid --ma-fast-range: Invalid range 5,20,0: the step must be
   greater than 0`.
   **Deliberate behaviour change:** a malformed range is now rejected even
   when the flag does not apply to the selected strategy, so
   `--ma-fast-range 1,2,x` exits 1 instead of exiting 0 with the flag
   ignored. That is how argparse already treats the other arguments
   (`--fast-period abc` fails even for a strategy that does not use it), and
   it turns a silent typo into a message.
4. **`quant_trading/optimization/base.py::ParameterSpace.generate_grid` —
   the infinite loop is now impossible for any caller.** It raises
   `ValueError("step must be greater than 0 to generate a grid (got 0.0)")`
   when the grid is generated from bounds with a non-positive step. An
   explicit `values=[...]` list is unaffected (the step is not used).
5. **Tests.** 17 new tests: 4 in-process + 4 subprocess for the strategy
   config content, 1 in-process + 1 subprocess for the invalid range, 2 unit
   tests for `parse_range`, 5 for `ParameterSpace.generate_grid`.
6. **README.md** — the "Error Reporting" section now also shows the malformed
   strategy config and the invalid range.

### What was actually verified

- **The committed tree (the assigned task)**: `python -m pytest -q` ->
  `1950 passed, 0 failed`; ruff clean; black clean; mypy clean (56 files).
- **After the strategy-config fix**: `python -m pytest -q` -> `1958 passed,
  0 failed`.
- **After the range fix**: `python -m pytest -q` -> `1967 passed, 0 failed`.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check .` -> 91 files unchanged (the smoke test file had to
  be reformatted once).
- `python -m mypy quant_trading examples` -> no issues found in 56 source
  files.
- **The new guards were proven to fail on a deliberately broken tree.** With
  the `examples/cli.py` change stashed (`git stash push -- examples/cli.py`),
  the 8 new strategy-config tests failed with the original tracebacks (e.g.
  `TypeError: '<=' not supported between instances of 'str' and 'int'`); the
  stash was popped and they went green again.
- **The hang was reproduced and measured.** Before the fix,
  `python examples/cli.py --optimize --ma-fast-range 5,20,0 --offline
  --symbols AAPL --days 30` was killed by a 90 s timeout (exit 124) with
  unbounded memory growth. After the fix it prints one line and exits 1.
- The `--optimize` path with valid ranges still works (`--ma-fast-range
  5,20,5 --ma-slow-range 20,50,10` produced the usual result table, exit 0).
- The neighbouring flags behave as before, except the one deliberate change:
  `--provider nosuchprovider` and `--fast-period abc` still fail in argparse
  (exit 2), `--interval 3x` and `--mc-simulations 0` still exit 0, and
  `--ma-fast-range 1,2,x` now exits 1 with a message (it used to exit 0 with
  the flag silently ignored).
- `python examples/cli.py --help` still renders (exit 0).

### What remains unresolved

- **A `--config` file with a wrong-typed value — RESOLVED this session.**
  `Config.from_yaml` now validates field types against the dataclass annotations
  and raises `ValueError`, which the CLI turns into a one-line
  `Error: ...` message with exit code 1 (no traceback).
- **`--interval 3x` is accepted silently.** `resolve_periods_per_year`
  (examples/cli.py:94) falls back to 252 for an unknown interval, which is a
  documented and tested behaviour
  (`tests/test_cli.py::TestResolvePeriodsPerYear::test_unknown_interval_falls_back_to_daily`).
  With a live provider the interval would fail later, in the provider. Where
  the check belongs is open: the two providers do not share one vocabulary
  (Yahoo Finance and Alpha Vantage use different interval strings), so the
  validation may belong in the provider and not in the CLI.
- **`--mc-simulations 0` is accepted and produces a confusing message.** The
  Monte Carlo summary comes back empty and the CLI prints
  `Error running backtest: 'probability_of_profit'`. A `--mc-simulations >= 1`
  check in the CLI would turn it into an actionable one-liner.
- **`--optimize --ma-fast-range 20,5,5` (minimum above maximum) still
  produces an empty result table and the exit code 0.** The step is validated
  now, the ordering is not.
- **`analyze_trades(periods_per_year=...)` is still not wired to the run, and
  the semantics are genuinely ambiguous — unchanged, deliberately.** The
  trade-level Sharpe and Sortino are computed on the **per-trade** return
  series, so the value of `periods_per_year` there means "how many *trades*
  per year" (see the docstring at
  `quant_trading/backtest/trade_analysis.py:466-491`), not "how many *bars*
  per year". A decision is needed on what the framework means by the parameter
  here; it is not a mechanical fix.
- **`TradeAnalysis.open_position_pnl` and the new
  `BacktestMetrics.unrealized_pnl` are different numbers and the names are
  close.** `open_position_pnl` is the part of the *realized* PnL that the
  positions which are still open booked (the entry fee of the shorts that were
  never covered) — it is already inside `total_pnl`. `unrealized_pnl` is the
  mark-to-market value of the open positions. Both are documented in the
  metrics docstring and in the README, but the confusion is still possible.
  Renaming either is a breaking change and was not attempted.
- **`calculate_backtest_metrics()` called with only an equity curve and a
  trade log reports `0.0` for the unrealized PnL even when the run had open
  positions.** The function accepts `positions=` and `unrealized_pnl=`
  (`quant_trading/backtest/metrics.py:163-227`) and the engine passes
  `positions=`, but a caller that rebuilds the metrics from
  `result.equity_curve` and `result.trades` alone still gets a `0.0` that is
  not the truth. Documented in the field docstring, in the README and in a
  dedicated test; the decision can be revisited.
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.
- **No CI workflow runs the project's test suite.** `.github/workflows/`
  holds only `main.yml` (the Kilo controller) and `kilo-workflow-audit.yml`
  (which validates the controller). A `ci.yml` that ran pytest/ruff/black/
  mypy would guard every future change, but **it cannot be committed by this
  harness**: the controller restores `.github/workflows` to the revision at
  session start and `git clean -fd`s the directory before the checkpoint
  commit (`.github/scripts/kilo-controller.sh:309-316`, and the pathspec
  exclusion `':(exclude).github/workflows/**'` at line 327). A CI workflow has
  to be added by a human, outside the agent loop.

### Approaches that already failed

- **The system Python has no dependencies.** `python3 -m pytest` fails with
  `ModuleNotFoundError: No module named 'pandas'`. Use the venv at
  `/home/runner/work/_temp/kilo-tmp/venv`; recreating it costs several
  minutes.
- **Installing `requirements.txt` alone left 11 failures** in
  `tests/test_optimization.py` (`ImportError: BayesianOptimizer requires
  scikit-optimize`). `scikit-optimize` is in the `dev` extra of
  `pyproject.toml`; this is **not** a repository defect — do not "fix" it.
- **Catching the strategy-config errors in `main()` was not enough.** The
  failures are `AttributeError` and `TypeError`, which are neither `OSError`
  nor `ValueError`, so the conversion has to happen where the file is read
  (`create_strategy`), not in the top-level handler.
- **Rejecting a zero step in `parse_range` alone was not enough.** The error
  message did not say which of the 27 `--*-range` flags was wrong, so the
  validation was moved up into `parse_args` where the flag name is known.
- **`parser._expand_help(action)` does not exist in Python 3.12** (it lives on
  `HelpFormatter`, not on the parser).
- **Ruff SIM117 rejects nested `with` statements** — combine them.
- **`MagicMock(spec=BacktestMetrics)` returns a child MagicMock, not the
  class default** — a spec restricts which attributes exist, it does not copy
  their values, so the mock cannot be formatted or serialized. Set the
  attributes explicitly.
- **Adding CLI print lines broke three existing CLI tests** that build
  `MagicMock()` metrics and set only the attributes the CLI prints.

### This session (2026-10-22) — wrongly-typed `--config` values

### What changed

**`quant_trading/config/settings.py`** — `Config.from_yaml` now validates every
deserialized value against the dataclass field annotations and raises
`ValueError` on a mismatch, before the dataclasses are constructed:

- New helpers `_type_matches(expected_type, value)` and
  `_check_field_types(dataclass_type, values)`.
- `int` is accepted for a `float` field; `float` is rejected for an `int`
  field; `bool` is accepted only for a `bool` field and never for an `int`
  field (`bool` is a subclass of `int`); `str | None` fields accept `None`.
- Unknown keys are still filtered out per sub-config (`_filter_fields`).
- Top-level fields (`logging_level`, `output_dir`) are checked too.
- No CLI changes were needed: `create_config` lets `ValueError` propagate and
  `main()` prints `Error: {e}` with exit code 1.

Now prints one line and exits 1 instead of a traceback:

```bash
$ cat /tmp/cfg.yaml
backtest:
  initial_capital: abc
$ python examples/cli.py --config /tmp/cfg.yaml --offline --symbols AAPL --days 10
Error: invalid config field BacktestConfig.initial_capital: expected <class 'float'>, got str ('abc')
```

### Tests

- `tests/test_config.py`: new `TestConfigFromYamlTypeChecking` with 10 unit
  tests (string for float, int for float, float for int, bool for int, int for
  bool, bool for bool, None for `str | None`, int for `str | None`, top-level
  field, unknown keys still ignored).
- `tests/test_examples_smoke.py`: new `CLI_CONFIG_CONTENTS` table (5 cases) and
  `test_cli_reports_a_wrongly_typed_config_without_a_traceback` subprocess
  test (exit code 1, message present, no traceback).
- `README.md` — "Error Reporting" section documents the wrongly-typed config.

### What was actually verified

- `python -m pytest -q` -> **1982 passed, 0 failed** (baseline 1967 + 15 new).
- `python -m ruff check .` -> All checks passed.
- `python -m black --check .` -> 91 files unchanged.
- `python -m mypy quant_trading examples` -> no issues found in 56 source
  files.
- End-to-end reproduction: the `initial_capital: abc` traceback is now the
  one-line `Error: ...` message above, exit code 1.
- Edge cases verified: int-for-float OK, bool-for-int rejected, int-for-bool
  rejected, float-for-int rejected, None for `str | None` OK.

### What remains unresolved

- **`--interval 3x` is accepted silently.** `resolve_periods_per_year`
  (examples/cli.py:94) falls back to 252 for an unknown interval, which is a
  documented and tested behaviour
  (`tests/test_cli.py::TestResolvePeriodsPerYear::test_unknown_interval_falls_back_to_daily`).
  With a live provider the interval would fail later, in the provider. Where
  the check belongs is open: the two providers do not share one vocabulary
  (Yahoo Finance and Alpha Vantage use different interval strings), so the
  validation may belong in the provider and not in the CLI.
- **`--mc-simulations 0` is accepted and produces a confusing message.** The
  Monte Carlo summary comes back empty and the CLI prints
  `Error running backtest: 'probability_of_profit'`. A `--mc-simulations >= 1`
  check in the CLI would turn it into an actionable one-liner.
- **`--optimize --ma-fast-range 20,5,5` (minimum above maximum) still
  produces an empty result table and the exit code 0.** The step is validated
  now, the ordering is not.
- **`analyze_trades(periods_per_year=...)` is still not wired to the run, and
  the semantics are genuinely ambiguous — unchanged, deliberately.** ...
- **`TradeAnalysis.open_position_pnl` and the new
  `BacktestMetrics.unrealized_pnl` are different numbers ...**
- **`calculate_backtest_metrics()` called with only an equity curve and a
  trade log reports `0.0` for the unrealized PnL ...**
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.
- **No CI workflow runs the project's test suite.** ... must be added by a
  human, outside the agent loop.

### Approaches that already failed

- **The system Python has no dependencies.** `python3 -m pytest` fails with
  `ModuleNotFoundError: No module named 'pandas'`. Use the venv at
  `/home/runner/work/_temp/kilo-tmp/venv`; recreating it costs several
  minutes.
- **Installing `requirements.txt` alone left 11 failures** in
  `tests/test_optimization.py` (`ImportError: BayesianOptimizer requires
  scikit-optimize`). `scikit-optimize` is in the `dev` extra of
  `pyproject.toml`; this is **not** a repository defect — do not "fix" it.
- **Catching the strategy-config errors in `main()` was not enough.** The
  failures are `AttributeError` and `TypeError`, which are neither `OSError`
  nor `ValueError`, so the conversion has to happen where the file is read
  (`create_strategy`), not in the top-level handler.
- **Rejecting a zero step in `parse_range` alone was not enough.** The error
  message did not say which of the 27 `--*-range` flags was wrong, so the
  validation was moved up into `parse_args` where the flag name is known.
- **`parser._expand_help(action)` does not exist in Python 3.12** (it lives on
  `HelpFormatter`, not on the parser).
- **Ruff SIM117 rejects nested `with` statements** — combine them.
- **`MagicMock(spec=BacktestMetrics)` returns a child MagicMock, not the
  class default** — a spec restricts which attributes exist, it does not copy
  their values, so the mock cannot be formatted or serialized. Set the
  attributes explicitly.
- **Adding CLI print lines broke three existing CLI tests** that build
  `MagicMock()` metrics and set only the attributes the CLI prints.

### Next task (one precise item)

**Make `--mc-simulations 0` a clean CLI error instead of the confusing
`Error running backtest: 'probability_of_profit'` message.**

Reproduced:
```bash
$ python examples/cli.py --monte-carlo --mc-simulations 0 --offline --symbols AAPL --days 10
Error running backtest: 'probability_of_profit'
```

Scope and constraints:
- Add the check in the CLI (`examples/cli.py`), not in the library: the Monte
  Carlo module is generic and a simulation count of 0 is a CLI usage error.
- The exception must be a `ValueError` so `main()` prints `Error: {e}` and
  returns 1 with no traceback.
- Accept `--mc-simulations >= 1` (the default is 1000); reject anything below
  1 with a message naming the flag, e.g.
  `Error: invalid --mc-simulations: the value must be at least 1 (got 0)`.
- Keep `--mc-simulations` unset/default behavior unchanged.
- Add a subprocess test in the style of `CLI_USER_ERRORS` /
  `CLI_CONFIG_CONTENTS` in `tests/test_examples_smoke.py`.
- Verify with `python -m pytest -q` (baseline **1982 passed, 0 failed**),
  `ruff check .`, `black --check .` and `mypy quant_trading examples`.
- Use the venv at `/home/runner/work/_temp/kilo-tmp/venv`.
