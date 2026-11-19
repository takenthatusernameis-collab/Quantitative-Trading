## Status

**Task complete (this session).** Audited `quant_trading/risk/metrics.py` and
`quant_trading/backtest/metrics.py` for any metric that mixes a numerator/mean
computed over the raw (unaligned) sample with a denominator computed over the
`_align_series` sample. No divergence found; nothing to fix.

## What changed

- No source changes (audit only).
- `HANDOFF_NEXT_AGENT.md`: recorded the audit result below.

## What was actually verified (this session)

- `grep _align_series quant_trading/risk/metrics.py` -> the helper is used only
  by `calculate_beta`, `calculate_alpha`, `calculate_treynor_ratio`, and
  `calculate_information_ratio`; each computes both its numerator and its
  denominator from the aligned sample (`quant_trading/risk/metrics.py:408`,
  `:450`, `:536`, `:572`). `calculate_alpha`, `calculate_information_ratio`, and
  `calculate_treynor_ratio` already use the aligned sample (the prior-session
  fix); `calculate_beta` was already aligned.
- `quant_trading/backtest/metrics.py` does not call `_align_series`; its
  market-relative metrics delegate to the above risk functions, which align
  internally.
- Result: **no further instances found** — no metric mixes a raw-sample
  numerator/mean with an aligned-sample denominator.
- `python -m pytest tests/test_risk_metrics.py tests/test_backtest_metrics.py -m "not slow and not network"` -> `183 passed`.
- `python -m black --check tests/ quant_trading/ examples/` -> unchanged.
- `python -m ruff check tests/ quant_trading/ examples/` -> `All checks passed!`.
- `python -m mypy tests/ quant_trading/ examples/` -> `Success: no issues found`.

## Gotchas (do not repeat)

- Do **not** modify `.github/workflows/*` from an agent session; the controller
  reverts/removes those files and excludes them from checkpoint commits.
- `pytest --cov` (`pytest-cov`) fails at collection; use `python -m coverage run`
  + `python -m coverage report` instead.
- Invoke `black`/`ruff`/`mypy` as `python -m <tool>` (not on PATH).

## One precise next task

Extend the aligned-sample audit beyond the two audited metric files: grep the
whole `quant_trading/` package for any other place that computes a ratio-like
metric where the numerator/mean is taken over a raw (un-aligned) return series
while the denominator (beta, tracking error, volatility, etc.) is taken over an
`_align_series`/aligned sample — the same class of bug fixed in
`calculate_treynor_ratio` (`quant_trading/risk/metrics.py`). Candidates to
check: `quant_trading/risk/manager.py`, `quant_trading/backtest/engine.py`,
and any other caller of `calculate_beta`/`calculate_alpha`/`calculate_treynor_ratio`
that recomputes a mean over the raw series. If a divergence is found, align it
and add a focused regression test under `tests/test_risk_metrics.py`; otherwise
record "no further instances found outside the two audited files." Verify with
the focused test files plus black/ruff/mypy. Do not touch workflow files.
