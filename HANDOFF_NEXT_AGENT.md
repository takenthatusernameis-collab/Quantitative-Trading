# Handoff to next agent

## What changed

Fixed a real documentation defect in `README.md`: a large block of example-script
demos had been appended *after* the final `## License` section (lines 1804–1970
of the old file), orphaned from the curated `### Example Scripts` section
(lines 670–1056). That trailing block was invisible to readers, duplicated 19
scripts already documented in the proper section, and named 10 scripts that were
not documented anywhere in the section at all.

- Moved the 6 scripts that existed *only* in the orphaned block into the proper
  `### Example Scripts` section, each with its own prose + runnable
  ```bash ... ``` block:
  - `run_accumulation_distribution.py`
  - `run_awesome_oscillator.py`
  - `run_bollinger_percent_b.py`
  - `run_momentum.py`
  - `run_super_trend.py`
  - `run_trix.py`
- Moved the 4 scripts that were *also* orphaned past the Annualization Periods
  section (a second, smaller orphaned block) into the proper section:
  - `run_aroon.py`
  - `run_atr.py`
  - `run_keltner.py`
  - `run_ma_crossover.py`
- Deleted the entire orphaned tail (everything after `## License\n\nMIT License`),
  so the README now ends with the License section.
- Fixed a copy-paste bug introduced by the first edit: the Bollinger %B block's
  code line read `python examples/run_ema_crossover.py`; corrected to
  `python examples/run_bollinger_percent_b.py`.

Added four regression guards to `tests/test_repository_integrity.py`:
- `test_no_duplicate_example_script_demos` — no script referenced twice in the
  section.
- `test_no_example_script_refs_outside_example_scripts_section` — every
  `examples/run_*.py` reference lives inside the `### Example Scripts` section.
- `test_example_scripts_section_has_code_block_for_every_ref` — every script
  referenced *after* the section's lead paragraph carries its own runnable
  ```bash``` line (the lead paragraph is exempt; it legitimately names
  `run_backtest.py`, a networked example outside the offline demo set).
- `test_readme_license_is_the_final_section` — the last section header in the
  file is `## License` and no header of any level appears after it.

## Verified (evidence)

- `python -m pytest tests/test_repository_integrity.py tests/test_readme.py
  tests/test_readme_cli.py tests/test_readme_cli_commands.py
  tests/test_strategy_registry_coverage.py -q` → 115 passed, 3 deselected.
- Full `pytest -q` → 2837 passed, 13 skipped, 131 deselected in 292.76s
  (was 2833 before the change; +4 are the new guards).
- `python -m black --check .` → 141 files unchanged.
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Evidence the new guards actually catch the old defect: a copy of the pre-fix
  README fails `test_no_example_script_refs_outside_example_scripts_section`
  with 10 orphaned refs
  (`run_accumulation_distribution.py`, `run_aroon.py`, `run_atr.py`,
  `run_awesome_oscillator.py`, `run_bollinger_percent_b.py`, `run_keltner.py`,
  `run_ma_crossover.py`, `run_momentum.py`, `run_super_trend.py`,
  `run_trix.py`) and passes after the fix.

## Unresolved

- None. The tree is green on pytest, black, ruff, and mypy.

## Approaches that failed / constraints

- The prior sessions' claim that "the README CLI section documents every flag"
  and "every example script is documented" was accurate for those *narrow*
  checks (`test_readme_cli.py` and `test_readme.py`'s example-script guard both
  pass). The defect was a different, previously unguarded invariant: content
  *after* the final section. No existing test asserted README section ordering,
  which is why the orphaned tail survived several prior edits. Lesson: a
  bidirectional README↔code sync test is not enough; also assert that the file's
  last section is the License header and that example-script references are
  confined to their own section.
- Constraint respected: no tests were modified to make anything pass; the new
  guards were written to fail on the old README and pass on the fixed one.

## Next task (precise)

- Re-run `pytest -q`, `python -m ruff check .`, `python -m black --check .`,
  and `python -m mypy quant_trading/` to confirm the tree is still green, then
  select a new bounded task.
- Candidate directions: hunt for other README structural invariants not yet
  guarded (e.g. every `##` section appearing exactly once, every code-block
  language tag being `bash`/`python`/`yaml`, every backtick-quoted
  `quant_trading.*` import resolving), or extend CLI/README coverage for an
  under-documented feature.
- Constraints: Do not modify tests to make them pass. Keep changes minimal and
  reversible. Any newly documented flag must be a real parser flag and its
  command must exit 0 (or 1 for documented error cases) with no traceback.

(End of file - total 73 lines)