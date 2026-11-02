# Handoff to next agent

## What changed
- Removed global `pytestmark = pytest.mark.network` from
  `tests/test_readme_cli_commands.py`. The module's offline-capable commands were
  being skipped entirely because of it; network gating is handled per-command
  inside the tests.

## What was actually verified
- `python -m pytest tests/test_readme_cli_commands.py -q` → 31 passed, 44 skipped.
- `python -m black --check ...`, `ruff check ...` clean.
- `python -m pytest -q` → 2634 passed, 44 skipped, 124 deselected (green).

## What remains unresolved
- 44 network-gated README CLI commands still skipped offline (cosmetic).
- `quant_trading/strategies/examples.py` ~13 uncovered statements.

## One precise next task
- Optionally add env guards/markers to network tests or improve coverage of
  `examples.py` defensive branches. Not blocking.
" filePath">
/home/runner/work/Quantitative-Trading/Quantitative-Trading/HANDOFF_NEXT_AGENT.md