"""Structural integrity checks for the repository source tree.

These are cheap, deterministic guards against a failure mode that has
repeatedly broken this repository: a patch that gets applied twice. A
duplicated keyword argument is a ``SyntaxError`` that makes an entire package
unimportable (every test module that touches it then fails at collection
time), a duplicated dataclass field silently overrides the earlier one, and a
duplicated module-level test function shadows the earlier definition so it is
never collected or executed.

The checks below are cheap enough to run on every test invocation and assert
the invariants that would have caught those regressions.
"""

import ast
import importlib
import pkgutil
import re
from pathlib import Path

import pytest

import quant_trading

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("quant_trading", "examples", "tests")


def _python_files() -> list[Path]:
    """Return every tracked Python source file in the repository."""
    files: list[Path] = []
    for directory in SOURCE_DIRS:
        files.extend(sorted((REPO_ROOT / directory).rglob("*.py")))
    return files


def _parse(path: Path) -> ast.Module:
    """Compile and parse a Python file, failing the test on any error.

    ``compile`` is used in addition to ``ast.parse`` because some errors only
    surface during compilation, such as a keyword argument that is repeated
    in a call (``f(a=1, a=2)``), which is the regression this guards against.
    """
    source = path.read_text(encoding="utf-8")
    rel = path.relative_to(REPO_ROOT)
    try:
        compile(source, str(rel), "exec")
    except SyntaxError as exc:  # pragma: no cover - only triggers on a regression
        pytest.fail(f"{rel} does not compile: {exc}")
    return ast.parse(source, filename=str(rel))


def test_all_source_files_parse():
    """Every Python file in the package and test tree must be parseable.

    A duplicated keyword argument (e.g. ``total_costs=total_costs,`` passed
    twice to a dataclass constructor) is a syntax error that breaks the whole
    import graph of the package.
    """
    files = _python_files()
    assert files, "expected to find Python source files"
    for path in files:
        _parse(path)


def test_no_duplicate_module_level_definitions():
    """No module may define the same top-level function or class twice.

    A second definition silently replaces the first one, so the earlier
    version is never collected by pytest and never executed.
    """
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        seen: dict[str, list[int]] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                seen.setdefault(node.name, []).append(node.lineno)
        for name, lines in seen.items():
            if len(lines) > 1:
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}: {name} defined at lines {lines}")
    assert not offenders, "duplicate module-level definitions:\n" + "\n".join(offenders)


def test_no_duplicate_methods_or_class_fields():
    """No class may define the same method or annotated field twice.

    Duplicated dataclass fields are legal Python but the later annotation
    silently replaces the earlier one, so the earlier default value is lost.
    """
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods: dict[str, list[int]] = {}
            fields: dict[str, list[int]] = {}
            for statement in node.body:
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.setdefault(statement.name, []).append(statement.lineno)
                elif isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    fields.setdefault(statement.target.id, []).append(statement.lineno)
            for name, lines in methods.items():
                if len(lines) > 1:
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}: {node.name}.{name} at lines {lines}")
            for name, lines in fields.items():
                if len(lines) > 1:
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}: {node.name}.{name} field at lines {lines}")
    assert not offenders, "duplicate class members:\n" + "\n".join(offenders)


def test_all_package_modules_import():
    """Every module of the ``quant_trading`` package must import cleanly."""
    failures: list[str] = []
    for module in pkgutil.walk_packages(quant_trading.__path__, prefix="quant_trading."):
        try:
            importlib.import_module(module.name)
        except Exception as exc:  # noqa: BLE001 - any import-time failure must be reported
            failures.append(f"{module.name}: {exc!r}")
    assert not failures, "modules failed to import:\n" + "\n".join(failures)


def test_no_duplicate_all_entries():
    """No module may list the same name twice in ``__all__``."""
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "__all__"
                        and isinstance(node.value, (ast.List, ast.Tuple))
                    ):
                        seen: set[str] = set()
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                if elt.value in seen:
                                    rel = path.relative_to(REPO_ROOT)
                                    offenders.append(f"{rel}: duplicate {elt.value} in __all__")
                                    break
                                seen.add(elt.value)
    assert not offenders, "duplicate __all__ entries:\n" + "\n".join(offenders)


def test_validate_parameters_overrides_annotated_none():
    """Every override of validate_parameters must declare -> None."""
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "validate_parameters":
                continue
            # Skip if it's the base class definition (Strategy.validate_parameters)
            # Only enforce on overrides in subclasses
            parent_class = None
            for ancestor in ast.walk(tree):
                if isinstance(ancestor, ast.ClassDef):
                    for item in ancestor.body:
                        if item is node:
                            parent_class = ancestor.name
                            break
                    if parent_class:
                        break
            returns = node.returns
            if not (
                (isinstance(returns, ast.Name) and returns.id == "None")
                or (isinstance(returns, ast.Constant) and returns.value is None)
            ):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno} ({parent_class}.{node.name})")
    assert not offenders, "validate_parameters without -> None:\n" + "\n".join(offenders)


def _cli_strategy_keys(tree: ast.Module) -> set[str]:
    """Extract the string literals of the CLI's ``BUILTIN_STRATEGY_KEYS`` list."""
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "BUILTIN_STRATEGY_KEYS"
            and isinstance(node.value, ast.List)
        ):
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    keys.add(elt.value)
    return keys


def test_cli_strategy_keys_match_registry():
    """The CLI's hardcoded strategy keys must match the live registry.

    ``examples/cli.py`` duplicates the registry's primary keys in the
    hardcoded ``BUILTIN_STRATEGY_KEYS`` list, which drives the ``--strategy``
    argparse choices and the strategies run by ``--combined`` mode. If a
    strategy is added to the registry but not to that list, the CLI silently
    rejects or excludes it. This test locks the two in sync.

    The CLI module is parsed with AST rather than imported, because importing
    it pulls in the Yahoo Finance provider (an optional dependency that may be
    absent).
    """
    from quant_trading.strategies import list_strategies

    registry_keys = set(list_strategies().keys())
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    cli_keys = _cli_strategy_keys(tree)
    rel = cli_path.relative_to(REPO_ROOT)
    offenders: list[str] = []
    missing = sorted(registry_keys - cli_keys)
    extra = sorted(cli_keys - registry_keys)
    if missing:
        offenders.append(f"{rel}: registry keys missing from BUILTIN_STRATEGY_KEYS: {missing}")
    if extra:
        offenders.append(f"{rel}: BUILTIN_STRATEGY_KEYS keys not in the registry: {extra}")
    assert not offenders, "CLI strategy keys out of sync with the registry:\n" + "\n".join(
        offenders
    )


def _cli_provider_entries(tree: ast.Module) -> dict[str, str]:
    entries: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PROVIDERS"
            and isinstance(node.value, ast.Dict)
        ):
            for key, val in zip(node.value.keys, node.value.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(val, ast.Tuple)
                    and val.elts
                    and isinstance(val.elts[0], ast.Constant)
                    and isinstance(val.elts[0].value, str)
                ):
                    entries[key.value] = val.elts[0].value
    return entries


def test_cli_provider_entries_match_data_providers():
    import quant_trading.data.providers as providers_mod
    import quant_trading.data.synthetic as synthetic_mod
    import quant_trading.data.yfinance_provider as yf_mod

    available = {
        name
        for mod in (providers_mod, synthetic_mod, yf_mod)
        for name in dir(mod)
        if name.endswith("Provider") and name != "DataProvider"
    }
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    entries = _cli_provider_entries(tree)
    assert entries, "could not parse PROVIDERS from examples/cli.py"
    offenders = []
    for key, cls_name in entries.items():
        if cls_name not in available:
            offenders.append(f"{key}: {cls_name} not found in data providers")
    assert not offenders, "CLI providers out of sync:\\n" + "\\n".join(offenders)


def test_class_docstring_is_first_statement():
    """A class docstring must be the first statement in the class body.

    A docstring placed after assignments or methods is a dead ``Expr``
    statement: ``cls.__doc__`` stays ``None`` and any ``__init_subclass__``
    logic that derives metadata from the docstring silently no-ops. This
    only flags classes that actually contain a stray string literal.
    """
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.body:
                continue
            first = node.body[0]
            first_is_docstring = (
                isinstance(first, ast.Expr)
                and isinstance(getattr(first, "value", None), ast.Constant)
                and isinstance(first.value.value, str)
            )
            if first_is_docstring:
                continue
            for stmt in node.body[1:]:
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(getattr(stmt, "value", None), ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno} ({node.name})")
                    break
    assert not offenders, "stray class docstring not first:\n" + "\n".join(offenders)


def test_module_docstring_is_first_statement():
    """A module docstring must be the first statement in the module body.

    A docstring placed after imports or other statements is a dead ``Expr``
    statement and is not recognized as the module docstring (``module.__doc__``
    stays ``None``). This only flags modules that actually contain a stray
    string literal after the first statement.
    """
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        if not tree.body:
            continue
        first = tree.body[0]
        first_is_docstring = (
            isinstance(first, ast.Expr)
            and isinstance(getattr(first, "value", None), ast.Constant)
            and isinstance(first.value.value, str)
        )
        if first_is_docstring:
            continue
        for stmt in tree.body[1:]:
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(getattr(stmt, "value", None), ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{stmt.lineno}")
                break
    assert not offenders, "stray module docstring not first:\n" + "\n".join(offenders)


# Optimizer classes the README's Features list must advertise. Kept in sync
# with ``quant_trading.optimization.__all__``; the README is the user-facing
# contract and silently dropping an optimizer from it is a real regression.
_OPTIMIZER_FEATURE_MARKERS: dict[str, str] = {
    "GridSearch": "Grid search",
    "RandomSearch": "random search",
    "BayesianOptimizer": "Bayesian optimization",
    "WalkForwardOptimizer": "walk-forward",
}


def test_readme_features_list_advertises_all_optimizers():
    """The README "Features" bullet must name every exported optimizer class.

    The Features list is the first thing a reader sees. If an optimizer is
    added to the package but the bullet is not updated, users will not know
    it exists, even though it is fully wired into the CLI and tests.
    """
    from quant_trading import optimization

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    features_start = readme.index("**Parameter Optimization**:")
    features_end = readme.index("\n", features_start)
    features_line = readme[features_start:features_end]

    exported = set(optimization.__all__)
    missing: list[str] = []
    for cls_name, marker in _OPTIMIZER_FEATURE_MARKERS.items():
        if cls_name in exported and marker.lower() not in features_line.lower():
            missing.append(f"{cls_name} (marker '{marker}')")
    assert (
        not missing
    ), "README Features bullet does not advertise every exported optimizer:\n" + "\n".join(missing)


def test_strategies_init_all_exports_exist():
    """Every name in quant_trading.strategies.__all__ must be importable."""
    import quant_trading.strategies as mod

    missing = [name for name in mod.__all__ if not hasattr(mod, name)]
    assert not missing, "strategies.__all__ names missing from module: " + ", ".join(missing)


def test_cli_strategy_imports_exist():
    """Names imported from quant_trading.strategies by examples/cli.py must exist."""
    import ast

    import quant_trading.strategies as mod

    tree = ast.parse((REPO_ROOT / "examples" / "cli.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "quant_trading.strategies":
            for alias in node.names:
                imported.add(alias.name)
    missing = sorted(name for name in imported if not hasattr(mod, name))
    assert not missing, "examples/cli.py imports missing from strategies: " + ", ".join(missing)


def test_example_scripts_import_from_strategies_examples_exist():
    """Names imported from quant_trading.strategies.examples by example scripts must exist."""
    import ast

    import quant_trading.strategies.examples as mod

    failures: list[str] = []
    for path in sorted((REPO_ROOT / "examples").glob("run_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "quant_trading.strategies.examples"
            ):
                for alias in node.names:
                    imported.add(alias.name)
        for name in sorted(imported):
            if not hasattr(mod, name):
                failures.append(
                    f"{path.name}: {name} missing from quant_trading.strategies.examples"
                )
    assert not failures, "example script imports missing:\n" + "\n".join(failures)


def test_example_scripts_quant_trading_imports_exist():
    """Names imported from quant_trading.* by example scripts must exist."""
    import ast
    import importlib

    failures: list[str] = []
    for path in sorted((REPO_ROOT / "examples").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("quant_trading")
            ):
                continue
            try:
                mod = importlib.import_module(node.module)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{path.name}: cannot import {node.module}: {exc!r}")
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if not hasattr(mod, alias.name):
                    failures.append(f"{path.name}: {alias.name} missing from {node.module}")
    assert not failures, "example script imports missing:\n" + "\n".join(failures)


def test_cli_quant_trading_imports_exist():
    """Names imported from quant_trading.* by examples/cli.py must exist."""
    import ast
    import importlib

    path = REPO_ROOT / "examples" / "cli.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("quant_trading")
        ):
            continue
        try:
            mod = importlib.import_module(node.module)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path.name}: cannot import {node.module}: {exc!r}")
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            if not hasattr(mod, alias.name):
                failures.append(f"{path.name}: {alias.name} missing from {node.module}")
    assert not failures, "CLI imports missing:\n" + "\n".join(failures)


# Matches a backtick-quoted example-script path such as
# ``examples/run_rsi.py``. Kept in sync with ``test_readme.py``'s pattern.
_EXAMPLE_SCRIPT_REF = re.compile(r"`(?P<path>examples/run_[a-z_]+\.py)`")
# Matches a runnable example-script line inside a bash code block, e.g.
# ``python examples/run_rsi.py``.
_EXAMPLE_SCRIPT_RUN = re.compile(r"python examples/run_[a-z_]+\.py")


def _readme_sections() -> list[tuple[int, int, str]]:
    """Return ``(header_line, level, title)`` for every README section header.

    ``level`` is the number of ``#`` characters (2 for ``##``, 3 for ``###``).
    """
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    sections: list[tuple[int, int, str]] = []
    for index, line in enumerate(text.splitlines()):
        match = re.match(r"^(#+)\s+(?P<title>.+?)\s*$", line)
        if match:
            sections.append((index + 1, len(match.group(1)), match.group("title")))
    return sections


def _example_scripts_section_bounds() -> tuple[int, int]:
    """Return the 1-indexed start and end line of the "Example Scripts" section.

    The section starts at its ``###`` header and ends just before the next
    ``##`` (or end of file). Raises ``AssertionError`` if the section is absent.
    """
    sections = _readme_sections()
    start = end = None
    for index, (line, level, title) in enumerate(sections):
        if title == "Example Scripts":
            start = line
            if index + 1 < len(sections):
                end = sections[index + 1][0] - 1
            else:
                end = (REPO_ROOT / "README.md").read_text(encoding="utf-8").count("\n")
            break
    assert start is not None, "README has no 'Example Scripts' section"
    assert end is not None, "README 'Example Scripts' section has no end"
    return start, end


def test_no_duplicate_example_script_demos():
    """Every example script must be documented at most once in the Example Scripts section.

    A script advertised twice (once in prose and once in a stray duplicate block,
    or twice in prose) is a documentation defect: the second occurrence is dead
    text that drifts out of sync with the first. This guard collapses the
    references inside the section to a set and fails on any duplicate.
    """
    start, end = _example_scripts_section_bounds()
    lines = (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()[start - 1 : end]
    section = "\n".join(lines)
    seen: dict[str, int] = {}
    for match in _EXAMPLE_SCRIPT_REF.finditer(section):
        name = Path(match.group("path")).name
        seen[name] = seen.get(name, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    assert not duplicates, "example scripts documented more than once:\n" + "\n".join(duplicates)


def test_no_example_script_refs_outside_example_scripts_section():
    """Every ``examples/run_*.py`` reference must live in the Example Scripts section.

    References that appear in other sections (or in a trailing orphaned block
    past the final section) are invisible to readers and drift out of sync with
    the curated list. This guard fails if any reference sits outside the section.
    """
    start, end = _example_scripts_section_bounds()
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = "\n".join(text.splitlines()[start - 1 : end])
    section_names = {Path(m.group("path")).name for m in _EXAMPLE_SCRIPT_REF.finditer(section)}
    outside: list[str] = []
    for match in _EXAMPLE_SCRIPT_REF.finditer(text):
        name = Path(match.group("path")).name
        if name not in section_names:
            outside.append(name)
    assert (
        not outside
    ), "example-script references outside the Example Scripts section:\n" + "\n".join(
        sorted(set(outside))
    )


def test_example_scripts_section_has_code_block_for_every_ref():
    """Every example script referenced after the section lead must have a runnable code block.

    A prose mention without a ``python examples/run_*.py`` line gives readers no
    copy-pasteable invocation, so the reference is incomplete. The section's
    lead paragraph (the text before the first `````bash`` block) is exempt: it
    is an overview that legitimately names scripts without invoking them, as
    with ``run_backtest.py`` (a networked example that is not part of the
    offline demo set). Every script referenced after the first code block must
    carry its own runnable line.
    """
    start, end = _example_scripts_section_bounds()
    section = "\n".join(
        (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()[start - 1 : end]
    )
    first_code = section.find("```bash")
    if first_code == -1:
        lead, body = section, ""
    else:
        lead, body = section[:first_code], section[first_code:]
    lead_names = {Path(m.group("path")).name for m in _EXAMPLE_SCRIPT_REF.finditer(lead)}
    prose = {Path(m.group("path")).name for m in _EXAMPLE_SCRIPT_REF.finditer(body)}
    runnable = {Path(m).name for m in _EXAMPLE_SCRIPT_RUN.findall(body)}
    missing = sorted((prose - lead_names) - runnable)
    assert not missing, "example scripts referenced in prose without a code block:\n" + "\n".join(
        missing
    )


def test_readme_license_is_the_final_section():
    """The README must end with the License section and nothing after it.

    A trailing block of orphaned example-script demos past the final section is
    invisible to readers and duplicates the curated list. The last section header
    in the file must be ``## License`` (two hashes), and no header of any level
    may appear after it (which is what an orphaned block would reintroduce).
    """
    sections = _readme_sections()
    assert sections, "README has no section headers"
    last_line, last_level, last_title = sections[-1]
    assert last_title == "License", f"last README section is {last_title!r}, expected 'License'"
    assert last_level == 2, f"License header is h{last_level}, expected h2"
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    # No header of any level may appear after the License header.
    for index in range(last_line, len(lines)):
        assert not re.match(r"^#+\s+", lines[index]), (
            f"header found at line {index + 1} after the License header at line {last_line}; "
            "an orphaned block follows the final section"
        )


def test_no_duplicate_section_titles():
    """Every README section title must appear exactly once, at any level.

    The same title used at two different heading levels (for example a ``###``
    subsection nested under the CLI section and a top-level ``##`` section) is
    a structural defect: a reader following the title lands on an ambiguous or
    wrong section, and the duplicate can drift out of sync. This guard folds
    all section titles into a single set and fails on any repeat, regardless
    of heading level.
    """
    seen: dict[str, list[tuple[int, int]]] = {}
    for line, level, title in _readme_sections():
        seen.setdefault(title, []).append((line, level))
    offenders = sorted(
        f"{title} at {occurrences}" for title, occurrences in seen.items() if len(occurrences) > 1
    )
    assert not offenders, "duplicate README section titles:\n" + "\n".join(offenders)
