## What changed (this session)

- Audited the repository for remaining hard-coded strategy/feature counts in
  docs and docstrings (the prior session's suggested follow-up). The README
  Strategy Registry list, its alias list, class names, the "48 registered
  strategies" feature bullet, and both module docstrings are already pinned to
  the live registry by `tests/test_readme.py` and
  `tests/test_strategy_registry_coverage.py`. No numeric strategy count was left
  ungarded.
- Found and closed the one remaining gap in that class: the README "Example
  Scripts" section hard-codes two spelled-out counts that no test pinned:
  - "It runs the three built-in strategies ..." for
    `examples/run_backtest_offline.py`
  - "... prints all three analysis modules" for `examples/run_analysis.py`
- Added `TestReadmeExampleScriptCounts` in `tests/test_readme.py` with two
  guards:
  - `test_offline_example_strategy_count_matches_script` parses
    `run_backtest_offline.py`, counts the `strategies = [...]` list literal, and
    pins the README's number word to it.
  - `test_analysis_module_count_matches_script` counts the analysis-module
    bullet list in `run_analysis.py`'s module docstring and pins the README's
    number word to it.
  - Shared helpers `_word_to_int`, `_offline_example_strategy_count`,
    `_analysis_module_count`, plus `_NUMBER_WORDS` and the two claim regexes.

## What was actually verified (evidence)

- `python -m pytest tests/test_readme.py -q`: 17 passed (was 15; +2 new).
- `python -m pytest tests/test_readme.py tests/test_repository_integrity.py tests/test_strategy_registry_coverage.py tests/test_readme_cli.py tests/test_readme_cli_commands.py -q`: 162 passed, 3 deselected.
- Full suite `python -m pytest -q`: 3993 passed, 144 deselected (was 3991; +2 new).
- `python -m ruff check tests/test_readme.py`: All checks passed.
- `python -m black --check tests/test_readme.py`: 1 file left unchanged.
- `python -m mypy tests/test_readme.py`: Success, no issues.
- Negative checks (temporary README edits, reverted): changing "three built-in"
  to "four built-in" and "all three analysis modules" to "all four" each make
  the corresponding guard fail, confirming they detect drift. README restored
  clean (`git status` clean for README.md).

## What remains unresolved / not verified

- Nothing blocking. Repo is green.
- Environment note: dependencies were not installed in this session; I ran
  `pip install -e ".[dev]"` (Python 3.14, black 26.10.1). `black --check .`
  reports 9 pre-existing files would be reformatted under black 26 (e.g.
  `quant_trading/strategies/factory.py`); this is black-version style drift, not
  a code defect, and was intentionally NOT reformatted to avoid unrelated churn.
  If CI pins an older black this is a non-issue; if it uses latest, it is a
  separate, deliberate decision to make.
- Known redundancy not addressed: `examples/run_klinger.py` and
  `examples/run_klinger_oscillator.py` are functionally identical (same
  `KlingerOscillatorStrategy(fast_period=55, slow_period=200)` and same data);
  the README describes the second as "with explicit fast/slow periods", which is
  misleading because the first already passes explicit periods. No guard covers
  this class of duplicate example scripts.

## Approaches that already failed and why

- No failed approaches this session. The prior count-audit suggestion was
  executed; the only unguarded counts found were the two now pinned.

## One precise next task

- Decide on the duplicate Klinger example scripts. Evidence:
  `diff examples/run_klinger.py examples/run_klinger_oscillator.py` shows only a
  docstring/name-string difference; both construct
  `KlingerOscillatorStrategy(fast_period=55, slow_period=200)` (the defaults).
  README lines ~1097-1113 document both as if distinct. Constraint: keep the
  change minimal and reversible; if consolidating, update README (remove the
  second section), rely on `test_readme.py::test_every_example_script_is_documented`
  and `test_repository_integrity.py::test_no_duplicate_example_script_demos`, and
  re-run `tests/test_example_scripts_run.py`. Alternatively, if the duplicate is
  judged intentional, add a short comment/README note rather than deleting.