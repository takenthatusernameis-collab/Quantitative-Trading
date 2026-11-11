## What changed (this session)

Extended `__post_init__` input validation to `DataConfig` in
`quant_trading/config/settings.py`, mirroring the existing `BacktestConfig`,
`RiskConfig`, and `PortfolioConfig` validation. `__post_init__` now raises
`ValueError` at construction (covers direct construction, `from_dict`, and
`from_yaml`):

`DataConfig`:
- `provider` non-empty string (`invalid provider`)
- `default_interval` non-empty string (`invalid default_interval`)
- `default_period` non-empty string (`invalid default_period`)
- `synthetic_days >= 1` (`invalid synthetic_days`)

`synthetic_seed` intentionally unchecked (any int; defaults already valid).
`Config.update()` left untouched per scope constraint (nested field assignment
still bypasses validation).

**Tests added** (`tests/test_config.py`, `TestDataConfig`):
- parametrized rejection tests for `provider`, `default_interval`,
  `default_period`, `synthetic_days`
- `test_accepts_boundary_valid_values` (synthetic_days=1 accepted)
- `test_from_dict_rejects_invalid_values`
- `test_from_yaml_rejects_invalid_values`

Error-message prefixes match existing style so `pytest.raises(..., match=...)`
aligns.

Files changed: `quant_trading/config/settings.py` (+~28), `tests/test_config.py`
(+~55).

## Verified (this session, evidence)

- `python -m pytest tests/test_config.py tests/test_backtest_engine.py -q -p no:cacheprovider` → 215 passed
- `python -m ruff check quant_trading/config/settings.py tests/test_config.py tests/test_backtest_engine.py` → All checks passed
- `python -m mypy quant_trading/config/settings.py --ignore-missing-imports` → Success: no issues found
- Full suite `python -m pytest -q -p no:cacheprovider` → 3331 passed; 17 failures are
  pre-existing environment gaps (missing `matplotlib` reporting tests), none
  related to this change

## Unresolved / not completed

- None for the assigned task. The 17 full-suite failures are pre-existing
  optional-dependency gaps.

## Failed approaches (do not repeat unchanged)

- None.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_config.py tests/test_backtest_engine.py -q -p no:cacheprovider
python -m ruff check quant_trading/config/settings.py tests/test_config.py tests/test_backtest_engine.py
python -m mypy quant_trading/config/settings.py --ignore-missing-imports
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree has uncommitted changes (settings.py, test_config.py).
  Do NOT commit unless explicitly asked.

## One precise next task

Make `Config.update()` validate nested sub-config assignments by reconstructing
the sub-config through its `from_dict` (so `__post_init__` runs), e.g.
`config.update(data={"synthetic_days": 0})` must raise `ValueError`
("invalid synthetic_days"), while scalar top-level updates (`logging_level`,
`output_dir`) keep working unchanged. Add parametrized rejection tests plus a
valid-update test to `tests/test_config.py` (`TestConfig`), then run the
verification commands above plus the full suite. Scope constraint: only nested
dataclass fields (`data`, `backtest`, `risk`, `portfolio`) are reconstructed;
unknown keys remain silently ignored; do not alter `__post_init__` logic.
