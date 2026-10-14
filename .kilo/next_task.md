# Next Task: Restore 100% coverage on `quant_trading/strategies/examples.py`

## Context

The prior handoff (regime detector robustness) was completed and committed; a
subsequent checkpoint added the `StochasticOscillatorStrategy` (commit `84ab720`).
The project convention is 100% line+branch coverage on every module. This session
executed the Monte Carlo edge-case task assigned by the prior handoff.

## What changed (verified)

- `quant_trading/monte_carlo/simulator.py`: added a private `_ensure_simulations()`
  guard, called at the top of `get_percentile`, `get_confidence_interval`,
  `probability_of_profit`, `probability_of_beat_benchmark`, and
  `expected_shortfall`.
- `tests/test_monte_carlo.py`: added 9 edge-case tests covering:
  - empty-result inputs raising `ValueError("No Simulations available")` on each
    of the five query methods (previously: `ZeroDivisionError` in the two
    probability methods, opaque `IndexError`/`nan` in the percentile/shortfall
    methods);
  - parametric method with a degenerate zero-variance (flat) return distribution;
  - parametric method with an extreme all-negative (-1%/day) distribution;
  - `summary()` output being JSON-serializable (result serialization);
  - `probability_of_beat_benchmark` returning 0.0 / 1.0 at the extremes.

### Root-cause reproduced before fixing
- `probability_of_profit()` / `probability_of_beat_benchmark()` → `ZeroDivisionError`.
- `get_percentile()` / `expected_shortfall()` → `IndexError` (numpy on empty input).
- `get_confidence_interval()` → transitively `IndexError`.

## What was verified

- `python -m pytest tests/test_monte_carlo.py -q` → 24 passed.
- `python -m pytest tests/ -q` → **937 passed**, 13 warnings.
- `python -m pytest tests/test_monte_carlo.py --cov=quant_trading.monte_carlo --cov-report=term-missing`
  → `simulator.py` **100%** (114 stmts, 18 branches, 0 missed).
- `ruff check` clean; `black --check` clean; `mypy` → "Success: no issues found".
- CLI unaffected: `examples/cli.py` only calls `mc.summary()` (which already
  guards empty), and `run_monte_carlo` raises `ValueError` on `< 2` returns
  before constructing any result, so empty results are not reachable via the CLI.

## What remains unresolved

Nothing blocking. The Monte Carlo edge-case task is complete.

## Approaches tried / failed

None. The single guard approach (`_ensure_simulations` raising `ValueError`)
was applied once, covered by tests, and passed all checks on the first attempt.

## Remaining project state (not modified this session)

Project-wide coverage is **99%**. The only module below 100% is
`quant_trading/strategies/examples.py` at 99% — a regression introduced by the
Stochastic commit (the prior handoff recorded 100% across all modules).
Missing: `1186->1097, 1307, 1363->1286`.

## Next precise task

**Restore 100% line+branch coverage on `quant_trading/strategies/examples.py`**
by adding the missing branch tests. Evidence (from
`pytest tests/ --cov=quant_trading --cov-report=term-missing`):

- **Line 1307** (`StochasticOscillatorStrategy.generate_signals`): the
  `# Skip if any values are NaN` `continue` is never reached. With the
  `min_required = k_period + d_period + 1` guard present, k/d on the last bar
  are valid unless the input OHLC contains `NaN`. Add a test feeding OHLC data
  with a `NaN` in the final rows and assert no crash + no signals.
- **Line 1363** (`elif prev_k >= 50 and current_k < 50`, stochastic midline
  cross-down): the *false* branch (no crossover) is uncovered — the existing
  cross-up test short-circuits at the inner `if` (line 1346) so line 1363 is
  never evaluated as false. Add a `use_midline=True` test where both `prev_k`
  and `current_k` are > 50 (rising but already above midline) → no signal,
  exercising the 1363 false branch back to the loop.
- **Line 1186** (`elif prev_price >= prev_ema and current_price < current_ema`,
  Keltner middle cross-down): the *false* branch is uncovered for the same
  reason (an `if`/`elif` chain). Add a Keltner `use_middle_cross=True` test where
  price stays above the EMA on the final bar → no middle signal, exercising the
  1186 false branch.

## Constraints

- Preserve the 100% coverage gate; new tests must fully cover any added lines.
- No network-dependent tests (mock all external calls). All Monte Carlo /
  strategy tests use synthetic in-memory data.
- Run `python -m pytest tests/ -q` and
  `python -m pytest tests/ --cov=quant_trading --cov-report=term-missing`
  and confirm `examples.py` returns to 100% with no regressions.
- Lint/format gates: `ruff check .`, `black --check .`, `mypy quant_trading`.
- Keep changes minimal and reversible; exclude generated artifacts (`.coverage`,
  `*.cover` strays, `__pycache__`, `.mypy_cache`, `.ruff_cache`) from any commit.

## Handoff evidence

- Full suite: 937 passed, 13 warnings (2026-10-14T19:3x Z).
- `quant_trading/monte_carlo` coverage: 100%.
- Project coverage: 99% (`examples.py` 99%, missing `1186->1097, 1307, 1363->1286`).
