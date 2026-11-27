## Session 2026-11-27 (allowlist cleanup - data/synthetic.py)

### What changed
- Added valid, single-line doctest examples to four methods in `quant_trading/data/synthetic.py`:
  - `SyntheticDataProvider.__init__`
  - `SyntheticDataProvider.name` (property; uses a custom `name="custom"` to show it is configurable)
  - `SyntheticDataProvider.fetch`
  - `SyntheticDataProvider.fetch_latest`
- Removed the four corresponding entries from `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py`.
- Remaining allowlist size dropped by 4 (was 457 -> 453 across the file).

### What was verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/synthetic.py` -> 60 passed, 1 skipped.
- `python -m pytest --doctest-modules quant_trading/data/synthetic.py` -> 10 passed.
- `python -m ruff check .` -> all checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `python -m pytest` -> 5296 passed, 260 skipped, 151 deselected in 192.06s (was 5292 before; +4 from the new doctests).
- `git diff --check` -> passed.

### Approach that FAILED / constraints (do not repeat unchanged)
- Do not remove allowlist entries without first adding valid examples; the integrity guard will fail.
- Each `>>>` line must be a single parseable Python statement (`compile(code, "<doctest>", "exec")`). Do not split a call across multiple `>>>` lines.
- Do not leave a blank line where adjacent allowlist entries were removed; Black rejects the resulting extra blank line.
- Do not de-allowlist a multi-line doctest without first converting each `>>>` statement to a single parseable line.
- Mypy is not available in this environment (`No module named mypy`); do not block on it.

### Next task
Clean the six remaining `quant_trading/data/providers.py` allowlist entries:
`__init__` (appears twice), `_coerce_datetime`, `_ensure_initialized`, `_iso`, and `to_dict`.
Add concise, single-line doctests to each corresponding def and remove their entries from `_EXAMPLES_ALLOWLIST`.
Note: `__init__` appears twice in the allowlist for providers.py, so both occurrences must be removed together.
Then run: focused integrity+module doctests, module doctests alone, `ruff check .`, `black --check`, and the full `pytest`.
Do not add allowlist entries for new code.