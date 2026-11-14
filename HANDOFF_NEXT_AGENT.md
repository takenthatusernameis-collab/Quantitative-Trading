## What changed (this session)
- Extended `tests/test_repository_integrity.py` with `test_cli_arg_defaults_match_strategy_init_defaults`, a deterministic guard that parses `examples/cli.py` (`CLI_ARG_DEFAULTS` and `create_strategy`'s `strategy_param_map`) and asserts each mapped CLI default matches the corresponding strategy `__init__` default.
- Intentional, documented drift is allowlisted explicitly: `ema` shares `--fast-period`/`--slow-period` with MA-style CLI defaults (10/30) while `EMACrossover` declares canonical class defaults (12/26). Any new CLI/class default drift will fail unless added to the allowlist with rationale.
- Confirmed the root-package re-export direction requested in the prior handoff is already covered: `test_package_reexports_are_listed_in_defining_module_all` walks all `quant_trading/**/__init__.py` (including root) and `quant_trading/__init__.py` currently has no package->defining-module `__all__` gaps.

## What was actually verified (evidence)
- Baseline at session start (from prior handoff, consistent with repo state): full suite `3783 passed, 140 deselected` (RC 0); `ruff check .` clean; `mypy quant_trading/` clean.
- Pre-change evidence: compared `CLI_ARG_DEFAULTS` against mapped strategy `__init__` defaults and found exactly 2 drifts: `('ema','fast_period','fast_period',10,12)` and `('ema','slow_period','slow_period',30,26)`. README/CLI usage and strategy class show EMA class canonical defaults are 12/26 while CLI reuses shared MA-style flags (10/30), treated as intentional and allowlisted.
- New guard: `python3 -m pytest -q tests/test_repository_integrity.py -k "cli_arg_defaults_match"` -> `1 passed, 26 deselected in 0.41s` (after fixing an initial missing `inspect` import in the test module).
- Focused integrity: `python3 -m pytest -q tests/test_repository_integrity.py` -> `27 passed in 1.01s`.
- Lint/type on touched areas: `python3 -m ruff check tests/test_repository_integrity.py examples/cli.py` -> `All checks passed!`.
- Not rerun this session (no source behavior changes, only a test/guard addition): full `pytest -q`, `mypy quant_trading/`, network-backed provider paths, and long-running smoke tests (deselected by default).

## What remains unresolved
- Nothing blocking. `CLI_ARG_DEFAULTS` currently covers only a subset of strategies/params exposed by the CLI; drift is guarded only for parameters present in `create_strategy`'s `strategy_param_map`. Not all CLI-exposed strategy constructor params are mapped/default-tracked there.
- Not verified this session: network-backed provider paths (`--provider yfinance` / `alphavantage`) and long-running smoke tests.

## Failed approaches (do not repeat unchanged)
- No material approach failures. Minor fix during implementation: first run of the new guard failed with `NameError: name 'inspect' is not defined` in `tests/test_repository_integrity.py`; resolved by adding `inspect` to imports (not a task-level blocker).

## One precise next task
- Extend CLI/default drift protection to strategies/params not represented in `create_strategy.strategy_param_map`: audit every strategy in `BUILTIN_STRATEGY_KEYS` whose class `__init__` takes tunable params but is absent or only partially mapped in `strategy_param_map` (e.g. strategies currently falling through to `factory_create_strategy(args.strategy)` defaults or using unmapped constructor params), then (1) decide per case whether the CLI should expose explicit flags/defaults or intentionally rely on class defaults, and (2) add a repository-integrity guard that, for each CLI-exposed tunable param, either asserts `CLI_ARG_DEFAULTS`/argparse default == class `__init__` default or records an explicit, rationale-backed allowlisted exception. Keep the change small, verify with `python3 -m pytest -q tests/test_repository_integrity.py tests/test_cli.py` and `python3 -m ruff check .`.
