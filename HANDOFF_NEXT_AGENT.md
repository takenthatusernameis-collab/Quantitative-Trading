## What changed (this session)
- Added a new deterministic repository-integrity guard in `tests/test_repository_integrity.py`: `test_cli_arg_defaults_entries_are_used_by_a_flag`. It parses `examples/cli.py` via AST and asserts every `CLI_ARG_DEFAULTS` entry is referenced as the `default=` of a real argparse flag, and that no flag references a missing key.
- The guard immediately exposed three dead `CLI_ARG_DEFAULTS` entries (`macd_zero_line`, `kc_use_middle_cross`, `stoch_use_midline`) that were documented but never wired to their `store_true` flags. Fixed by making `--macd-zero-line`, `--kc-use-middle-cross`, and `--stoch-use-midline` read `default=CLI_ARG_DEFAULTS[...]` (three one-line additions in `examples/cli.py`), restoring a single source of truth.
- Refactored `_cli_default_values` into a thin wrapper over a new `_cli_arg_defaults_node` helper (returns the AST dict node) so both the existing default-parity test and the new wiring guard share the same lookup.

## What was actually verified (evidence)
- `python3 -m pytest -q tests/test_repository_integrity.py` -> `28 passed in 7.25s` (was 27; +1 new test).
- `python3 -m pytest -q tests/test_cli.py -p no:cacheprovider` -> `295 passed, 3 deselected in 235.63s` (RC 0).
- `python3 -m ruff check .` -> `All checks passed!`.
- `python3 -m mypy examples/cli.py` -> `Success: no issues found in 1 source file`.
- Behavior of the three edited flags is unchanged: `store_true` with a `False` default behaves identically to the implicit `store_true` default; only the default source changed.
- Confirmed (by AST scan) that the only argparse flags not backed by `CLI_ARG_DEFAULTS` are intentionally literal/constant: ranges (optimization), floats (`n-iter`, `bayesian-noise`, `wf-*`), booleans (`wf-anchored/rolling`, `report-*`), and `strategy`.

## What remains unresolved
- Nothing blocking. Two separate drift axes remain partially covered:
  1. Flag <-> `CLI_ARG_DEFAULTS` wiring: now guarded (this session).
  2. `CLI_ARG_DEFAULTS` <-> strategy `__init__` defaults: guarded only for the (strategy, cli_arg, param) triples present in `create_strategy.strategy_param_map` (pre-existing guard `test_cli_arg_defaults_match_strategy_init_defaults`). Many registered strategies have tunable constructor params that the CLI does not expose with dedicated flags and therefore fall through to `factory_create_strategy(args.strategy)` defaults (e.g. `cci`, `cmf`, `cmo`, `dpo`, `eom`, `hma`, `klinger`, `mfi`, `momentum`, `obv`, `roc`, `smi`, `stochrsi`, `trix`, `vortex`, `vroc`, `vpt`, `williamsr`, `adl`, `bbpct`, `ao`, `cho`, `vol`, `ppo`, `pvo`, `nvi`, `pvi`, `force_index`, `elder_ray`, `ultimate_oscillator`). These are NOT flagged by either guard today.
- Not verified this session: network-backed provider paths (`--provider yfinance` / `alphavantage`) and long-running/slow smoke tests (deselected by default).

## Failed approaches (do not repeat unchanged)
- Initial version of the new guard failed (by design) with `1 failed` because the three boolean `CLI_ARG_DEFAULTS` entries were unused. The correct resolution was to wire the flags to those entries (root-cause fix), NOT to add them to an allowlist or weaken the guard. Do not weaken the guard to make it pass.

## One precise next task
- Close the remaining `CLI_ARG_DEFAULTS` <-> strategy `__init__` coverage gap for strategies the CLI does not currently expose with dedicated flags. Concretely:
  1. Enumerate every registered strategy in `BUILTIN_STRATEGY_KEYS`/`list_strategies()` whose class `__init__` declares tunable params (skip `self`, `name`, `parameters`) but which has no entry in `create_strategy.strategy_param_map`.
  2. Decide per strategy whether the CLI should (a) intentionally rely on class defaults (document this in an explicit allowlist with rationale), or (b) expose explicit flags + `CLI_ARG_DEFAULTS` entries + `strategy_param_map` mappings so the CLI and class stay in lockstep.
  3. Extend a repository-integrity guard so each CLI-exposed tunable param asserts `CLI_ARG_DEFAULTS`/argparse default == class `__init__` default, or records an explicit, rationale-backed allowlisted exception.
  - Constraints/evidence: start from `tests/test_repository_integrity.py::test_cli_arg_defaults_match_strategy_init_defaults` and the helpers `_cli_strategy_param_map` / `_cli_default_values` / `_cli_flag_defaults`. Verify with `python3 -m pytest -q tests/test_repository_integrity.py tests/test_cli.py`, `python3 -m ruff check .`, and `python3 -m mypy examples/cli.py`. Keep the change small and reversible; do not convert every class-default strategy into a new CLI flag unless there is a demonstrated need.