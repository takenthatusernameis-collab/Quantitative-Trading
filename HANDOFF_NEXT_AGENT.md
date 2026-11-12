## What changed (this session)

Made `Config.update()` validate nested sub-config assignments by reconstructing
the sub-config through its `from_dict` (so `__post_init__` runs), in
`quant_trading/config/settings.py:835-843`.

`Config.update(**kwargs)`:
- unknown keys remain silently ignored (unchanged);
- scalar top-level updates (`logging_level`, `output_dir`) keep working
  unchanged;
- nested dataclass fields (`data`, `backtest`, `risk`, `portfolio`) given a
  `dict` are merged with the existing sub-config (`{**current.to_dict(), **value}`)
  and reconstructed via `field_type.from_dict(merged)`, so `__post_init__`
  validation runs; a failed validation leaves the sub-config untouched
  (`setattr` never executes).

Example: `config.update(data={"synthetic_days": 0})` now raises
`ValueError: invalid synthetic_days: ...` instead of silently storing it.

**Tests added** (`tests/test_config.py`, `TestConfig`):
- `test_update_rejects_invalid_nested_values` — 11 parametrized cases across
  `data`, `backtest`, `risk`, `portfolio` (all `match="invalid"`)
- `test_update_accepts_valid_nested_values` — partial nested updates keep
  unmentioned fields intact
- `test_update_scalar_fields_still_work` — `logging_level`/`output_dir`

No `__post_init__` logic was altered.

Files changed: `quant_trading/config/settings.py` (+~16/-2), `tests/test_config.py` (+43).

## Verified (this session, evidence)

- `python -m pytest tests/test_config.py tests/test_backtest_engine.py -q -p no:cacheprovider` → 228 passed (215 before + 13 new)
- `python -m ruff check quant_trading/config/settings.py tests/test_config.py` → All checks passed
- `python -m mypy quant_trading/config/settings.py --ignore-missing-imports` → Success: no issues found
- Full suite `python -m pytest -q -p no:cacheprovider` → 3344 passed; 17 failures are
  pre-existing environment gaps (missing `matplotlib` reporting tests), none
  related to this change

## Unresolved / not completed

- None for the assigned task. The 17 full-suite failures are pre-existing
  optional-dependency gaps; install `quant-trading[reporting]` to make them pass.

## Failed approaches (do not repeat unchanged)

- None.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_config.py tests/test_backtest_engine.py -q -p no:cacheprovider
python -m ruff check quant_trading/config/settings.py tests/test_config.py
python -m mypy quant_trading/config/settings.py --ignore-missing-imports
python -m pytest -q -p no:cacheprovider
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree has uncommitted changes (settings.py, test_config.py).
  Do NOT commit unless explicitly asked.

## One precise next task

The assigned task is complete and verified. No further work is required;
optional follow-ups would be committing the two modified files or installing
`quant-trading[reporting]` to clear the 17 pre-existing matplotlib failures.
