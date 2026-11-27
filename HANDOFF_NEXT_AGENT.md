## Session 2026-11-27 (allowlist cleanup - portfolio/portfolio.py)

### What changed
- Added valid, runnable SINGLE-LINE `Examples:` doctests to 18 public
  `quant_trading/portfolio/portfolio.py` callables that lacked them, and removed
  their allowlist entries:
  - `Holding.unrealized_pnl`, `unrealized_pnl_pct`, `update_price`,
    `to_position`, `to_dict`.
  - `Portfolio.get_holdings_value`, `get_position`, `get_position_value`,
    `get_position_pct`, `add_holding`, `remove_holding`, `update_prices`,
    `get_positions`, `get_allocation`, `get_net_allocation`,
    `get_gross_allocation`, `reset`, `summary`, `to_dict`.
  - Each example builds `Portfolio(...)` / `Holding(...)` directly and prints a
    scalar / short tuple / dict - no backtest/heavy run. Fast + deterministic.
- Allowlist shrank by 20 lines (18 distinct names; `to_dict` was listed twice).
  Remaining portfolio.py entries (2 lines): `from_dict` (both `Holding.from_dict`
  and `Portfolio.from_dict` - KEPT, see failed-approach note).

### What was verified (evidence)
- `pytest tests/test_repository_integrity.py --doctest-modules quant_trading/portfolio/portfolio.py`
  -> 76 passed, 1 skipped (was 54; +22 new doctest assertions).
- `python -m ruff check quant_trading/portfolio/portfolio.py tests/test_repository_integrity.py`
  -> All checks passed.
- `python -m black --check` on both files -> 2 files unchanged.
- Guard tests `pytest tests/test_repository_integrity.py -k "examples or allowlist"`
  -> 3 passed.
- Full default suite `pytest -q` -> 5361 passed, 171 skipped, 151 deselected
  (was 5339; +22 new doctests, no regressions).

### IMPORTANT: failed approach this session (do not repeat)
- Do NOT try to de-allowlist `from_dict` (either class). Their existing Examples
  use MULTI-LINE `>>>` openers (`>>> Holding.from_dict({` / `>>> Portfolio.from_dict({`)
  that end in an open brace. `_validate_doctest_lines` compiles each `>>>` line
  in ISOLATION, so an open-brace opener fails with "was never closed". They must
  stay allowlisted unless rewritten to single-line `>>>` statements.
- RULE (unchanged): keep every `>>>` statement on ONE line; do NOT use `...`
  continuation for the FIRST line of a statement. Verify EXACT repr output by
  running the snippet in `python -c` BEFORE editing (e.g. `get_position_pct`
  returns `0.11764705882352941`; the example uses `round(..., 4)` -> `0.1176`).

### Notes for next session
- Pattern that works: build result objects directly from `Portfolio(...)` /
  `Holding(...)`; keep each `>>>` statement single-line and confirm exact output
  first. `Position` repr is `Position(symbol=..., quantity=..., avg_price=...,
  current_price=..., unrealized_pnl=..., realized_pnl=...)` - prefer printing a
  single field (e.g. `.quantity`) over the whole repr.
- Ruff uses default rules (no E501), so long single-line `>>>` lines are fine;
  black does not reformat docstring content.

### Next task
Pick one more bounded module and clear its PUBLIC single-line-doctestable
allowlist entries. Good candidates (public, data-only, no heavy runs):
- `quant_trading/risk/metrics.py`: public `calculate_alpha`,
  `calculate_component_var`, `calculate_equal_risk_contribution_weights`,
  `calculate_marginal_var`, `calculate_risk_budget_weights`,
  `calculate_volatility_contributions`, `to_dict`/`from_dict` - need small
  numpy arrays / dataclass; verify exact float reprs with `python -c`.
- `quant_trading/regime/detector.py`: `summary`, `to_dataframe`, `to_dict`,
  `from_dict`, `detect`/`detect_regimes` (detector needs a return series).
- Alternatively scan `_EXAMPLES_ALLOWLIST` (tests/test_repository_integrity.py
  ~line 1787) for the next module whose public functions have NO Examples yet.
Verify with `pytest tests/test_repository_integrity.py --doctest-modules <module>`
and `ruff check`, then full `pytest -q`. Only de-allowlist functions whose
Examples use single-line `>>>` statements only, and confirm exact output first.