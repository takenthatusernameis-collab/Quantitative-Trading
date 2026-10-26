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
