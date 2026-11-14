## What changed (this session)
- Closed the remaining `CLI_ARG_DEFAULTS` <-> strategy `__init__` coverage gap with an explicit, enforced classification instead of new CLI flags:
  - Added `_tunable_init_params(strategy_cls)` to `tests/test_repository_integrity.py`. It returns the constructor parameters a caller can tune, excluding `self`, `name`, `parameters`, and `*args`/`**kwargs` (uses `inspect.signature(cls)`, not `cls.__init__`, to stay mypy-clean).
  - Added `_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS`, a documented allowlist of the 30 registered strategies that intentionally run on class defaults and are tuned through `--strategy-config` (whose `parameters` are forwarded verbatim to the constructor by `Strategy.from_config`).
  - Added `test_registered_strategies_have_documented_cli_coverage`. It asserts:
    1. every `strategy_param_map` key is a registered strategy;
    2. for each mapped strategy, every tunable `__init__` param is exposed by a dedicated flag (no partial mapping hiding a knob);
    3. every registered strategy with tunable params is either mapped or allowlisted;
    4. every allowlist entry is still registered, still unmapped, and still has tunable params (no stale entries).
- No production code (`examples/cli.py`) was changed; the 30 unmapped strategies already behave correctly (they use class defaults), so the fix is purely making the existing design explicit and guarded.

## What was actually verified (evidence)
- `python3 -m pytest -q tests/test_repository_integrity.py -p no:cacheprovider` -> `29 passed in 7.19s` (was 28; +1 new test).
- `python3 -m pytest -q tests/test_cli.py -p no:cacheprovider` -> `295 passed, 3 deselected in 240.84s` (RC 0).
- `python3 -m ruff check .` -> `All checks passed!`.
- `python3 -m mypy tests/test_repository_integrity.py` -> same 4 pre-existing errors as `HEAD` (lines 495, 518, 609, 621; verified by stashing the change and re-running). The new helper adds no new mypy error.
- Negative test: temporarily removed `"adl"` from the allowlist; the new test failed with `adl (AccumulationDistributionStrategy) has tunable __init__ params ['signal_period'] but is neither in strategy_param_map nor in _STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS`. File restored afterwards; `git diff --stat` shows only the intended +144 lines.
- Ad-hoc AST audit confirmed no current CLI default/type mismatch (all `CLI_ARG_DEFAULTS`-backed flags use a compatible `type=`, and the three boolean entries are `store_true` with no `type=`).

## What remains unresolved
- Nothing blocking. The `CLI_ARG_DEFAULTS` drift axes are now both guarded:
  1. entry <-> flag wiring (previous session), and
  2. registered strategy <-> CLI coverage (this session).
- Working tree is intentionally uncommitted: only `tests/test_repository_integrity.py` is modified (the system instructions forbid committing without an explicit request). `HANDOFF_NEXT_AGENT.md` is updated but uncommitted.
- Not verified this session: network-backed provider paths (`--provider yfinance` / `alphavantage`) and long-running/slow smoke tests (deselected by default).

## Failed approaches (do not repeat unchanged)
- Do not weaken the new allowlist/guard to make it pass; the guard is the point.
- Do not convert the 30 config-file-only strategies into dedicated CLI flags without a demonstrated need: that would duplicate the class API and bloat the parser, contrary to the handoff constraint.

## One precise next task
- Add a cheap, deterministic guard that each `CLI_ARG_DEFAULTS`-backed argparse flag's `type=` is compatible with its default value (and that boolean entries are `store_true` with no `type=`). Evidence this is currently green: the ad-hoc AST audit above shows every `int`/`float` default matches its `type=`, `dc_exit_period=None` is the only `None` default, and `macd_zero_line`/`kc_use_middle_cross`/`stoch_use_midline` have no `type=`.
  - Where: extend `tests/test_repository_integrity.py` next to `_cli_flag_defaults` / `test_cli_arg_defaults_entries_are_used_by_a_flag`; parse the `type=` keyword of each `add_argument` call and compare against `_cli_default_values(tree)[key]`.
  - Constraints/evidence: reuse `_cli_flag_defaults` (extend it to also return the `type=` name if needed). Verify with `python3 -m pytest -q tests/test_repository_integrity.py tests/test_cli.py`, `python3 -m ruff check .`, and `python3 -m mypy tests/test_repository_integrity.py` (compare error count to the 4-error baseline). Keep the change small and reversible.