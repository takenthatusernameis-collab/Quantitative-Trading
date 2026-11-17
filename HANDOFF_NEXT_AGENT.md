## What changed (this session)

- Addressed the 5 pre-existing failures in `tests/test_readme_cli_commands.py` (all
  caused by optional extras not being installed). Root cause: the README command
  harness asserts exit code 0 for every documented invocation, but some commands
  legitimately require optional extras — `--report` needs `reporting`/matplotlib
  and `--optimizer bayesian` / `--wf-optimizer bayesian` need `bayesian`/scikit-optimize
  (both documented in README.md:704-715). With only core deps installed these
  exited 1, so the default `pytest` run failed out of the box.
- Fix (smallest reversible, durable): made the harness **skip** commands that
  require an optional extra when that extra is not importable, with a clear
  reason, instead of failing. Changes are confined to
  `tests/test_readme_cli_commands.py`:
  - new `_module_available(name)` (via `importlib.util.find_spec`)
  - new `_requires_matplotlib(args)` (True when `--report` is present without
    `--report-no-charts`, which is the only chart-free path)
  - new `_requires_skopt(args)` (True when `--optimizer`/`--wf-optimizer` is
    followed by `bayesian`)
  - `_readme_commands()` now appends `pytest.mark.skip(...)` for the relevant
    commands when the extra is missing. No production code changed.

## What was actually verified (evidence)

- Without extras (clean env): `python -m pytest tests/test_readme_cli_commands.py -q -rs`
  -> **114 passed, 5 skipped, 3 deselected**; the 5 skips are exactly the two
  `--report` (charted) commands and three bayesian commands, each with an
  actionable reason.
- Skip selection logic independently checked by simulating missing
  matplotlib/skopt: of 116 extracted commands, exactly 5 get a skip mark.
- With extras installed (`pip install --user matplotlib scikit-optimize`, resolves
  to matplotlib 3.11.2 / scikit-optimize 0.10.2 on Python 3.14): the same module
  -> **119 passed, 3 deselected** — i.e. the commands genuinely work, the skips
  do not hide breakage.
- Full default suite: `python -m pytest -q` -> **4054 passed, 142 deselected**
  (no failures).
- `python -m black --check .` -> **160 files would be left unchanged**.
- `python -m ruff check .` -> **All checks passed** (fixed a SIM102 collapsible-if
  in the new helper).
- `python -m mypy .` -> **Success: no issues found in 160 source files**.

## What remains unresolved / not verified

- The optional extras are installed in *this* session's user site only; the repo
  change makes the suite pass with or without them, but a fresh environment must
  not assume matplotlib/scikit-optimize are present.
- `--combined` commands remain marked `slow` (deselected by default) and were not
  run in the full-suite pass.
- Network-marked tests deselected as usual.

## Approaches that failed

- None. (Initial instinct to only install extras was rejected because it does not
  persist to a fresh checkout; the skip-based fix is the durable one.)

## One precise next task

The optional-extra README-command failures are resolved and the full default
suite is green (4054 passed). If continuing, pick one of:

1. Add a CI check that runs `pytest` in a **core-only** environment to lock in
   that the new skip logic keeps the suite green without optional extras (e.g. a
   GitHub Actions matrix leg with `pip install -e .` and no extras, asserting
   exit 0). Relevant file: `.github/workflows/` + `tests/test_readme_cli_commands.py`.
2. Add coverage for the `--report-no-charts` path (README.md:710) asserting it
   stays green *without* matplotlib — currently it passes implicitly because it
   is not skip-marked, but there is no explicit test that it does not import
   matplotlib. Evidence to build on: `_requires_matplotlib` in
   `tests/test_readme_cli_commands.py`.