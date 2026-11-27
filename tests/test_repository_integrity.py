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
import inspect
import pkgutil
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

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


def _is_docstring_expr(statement: ast.stmt) -> bool:
    """Return whether a statement is a string-literal expression."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def test_all_source_files_parse() -> None:
    """Every Python file in the package and test tree must be parseable.

    A duplicated keyword argument (e.g. ``total_costs=total_costs,`` passed
    twice to a dataclass constructor) is a syntax error that breaks the whole
    import graph of the package.
    """
    files = _python_files()
    assert files, "expected to find Python source files"
    for path in files:
        _parse(path)


def test_no_duplicate_module_level_definitions() -> None:
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


def test_no_duplicate_methods_or_class_fields() -> None:
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


def test_all_package_modules_import() -> None:
    """Every module of the ``quant_trading`` package must import cleanly."""
    failures: list[str] = []
    for module in pkgutil.walk_packages(quant_trading.__path__, prefix="quant_trading."):
        try:
            importlib.import_module(module.name)
        except Exception as exc:  # noqa: BLE001 - any import-time failure must be reported
            failures.append(f"{module.name}: {exc!r}")
    assert not failures, "modules failed to import:\n" + "\n".join(failures)


def test_no_duplicate_all_entries() -> None:
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


def _tree_validate_parameters_override_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return every ``validate_parameters`` override that drifts from the base signature.

    ``Strategy.validate_parameters`` declares ``(self) -> None``. Overrides must
    keep exactly one parameter named ``self`` and declare ``-> None``.
    """
    mismatches: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name == "Strategy":
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "validate_parameters":
                continue
            args = item.args.args
            if len(args) != 1:
                shown = ", ".join(arg.arg for arg in args) or "no parameters"
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.validate_parameters has {len(args)} "
                    f"parameter(s) ({shown}), expected exactly (self)"
                )
                continue
            if args[0].arg != "self":
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.validate_parameters first parameter is "
                    f"{args[0].arg!r}, expected self"
                )
            returns = item.returns
            if not (
                (isinstance(returns, ast.Name) and returns.id == "None")
                or (isinstance(returns, ast.Constant) and returns.value is None)
            ):
                shown = ast.unparse(returns) if returns is not None else "untyped"
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.validate_parameters returns "
                    f"{shown}, expected None"
                )
    return mismatches


def _documented_validate_parameters_override_mismatches() -> list[str]:
    """Return every ``validate_parameters`` override that drifts from the base signature."""
    mismatches: list[str] = []
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        mismatches.extend(_tree_validate_parameters_override_mismatches(_parse(path), rel))
    return mismatches


def test_validate_parameters_overrides_annotated_none() -> None:
    """Every override of ``validate_parameters`` must keep the base signature.

    ``Strategy.validate_parameters`` declares ``(self) -> None``. Overrides must
    keep exactly one parameter named ``self`` and declare ``-> None``. This
    guard is purely structural (AST) and only checks overrides outside the base
    ``Strategy`` class.

    Negative controls inject a wrong first-parameter name and wrong parameter
    counts (0 and 2), and assert each drift is reported. A positive control with
    the canonical signature passes.
    """
    synthetic_first_param_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def validate_parameters(cls) -> None:\n"
        "        return\n"
    )
    injected = _tree_validate_parameters_override_mismatches(
        ast.parse(synthetic_first_param_mismatch), "synthetic.py"
    )
    assert injected, "guard did not fire on an injected validate_parameters first parameter drift"

    synthetic_arg_count_zero = (
        "class MyStrategy(Strategy):\n"
        "    def validate_parameters() -> None:\n"
        "        return\n"
    )
    injected = _tree_validate_parameters_override_mismatches(
        ast.parse(synthetic_arg_count_zero), "synthetic.py"
    )
    assert (
        injected
    ), "guard did not fire on an injected validate_parameters parameter count drift (0)"

    synthetic_arg_count_two = (
        "class MyStrategy(Strategy):\n"
        "    def validate_parameters(self, extra: int) -> None:\n"
        "        return\n"
    )
    injected = _tree_validate_parameters_override_mismatches(
        ast.parse(synthetic_arg_count_two), "synthetic.py"
    )
    assert (
        injected
    ), "guard did not fire on an injected validate_parameters parameter count drift (2)"

    synthetic_ok = (
        "class MyStrategy(Strategy):\n"
        "    def validate_parameters(self) -> None:\n"
        "        return\n"
    )
    assert not _tree_validate_parameters_override_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a canonical validate_parameters override"

    mismatches = _documented_validate_parameters_override_mismatches()
    assert not mismatches, "validate_parameters override signature drift:\n" + "\n".join(mismatches)


def _normalize_generate_signals_annotation(annotation: ast.expr | None) -> str | None:
    """Normalize a ``generate_signals`` return annotation.

    Only the base-class form ``list[Signal]`` is recognized; any other form
    (including no annotation) is reported as a mismatch so callers that consume
    the result as a list of :class:`Signal` are never silently given a
    different type.
    """
    if annotation is None:
        return None
    if isinstance(annotation, ast.Subscript):
        base = annotation.value
        base_name = base.id if isinstance(base, ast.Name) else None
        if base_name in {"list", "List"}:
            slice_expr = annotation.slice
            if isinstance(slice_expr, ast.Tuple):
                args = slice_expr.elts
            else:
                args = [slice_expr]
            if len(args) == 1 and isinstance(args[0], ast.Name) and args[0].id == "Signal":
                return "list[Signal]"
    return None


def _normalize_generate_signals_data_annotation(annotation: ast.expr | None) -> str | None:
    """Normalize the ``data`` parameter annotation of ``generate_signals``.

    Only the base-class form ``dict[str, pd.DataFrame]`` is recognized.
    """
    if annotation is None:
        return None
    if not isinstance(annotation, ast.Subscript):
        return None
    base = annotation.value
    base_name = base.id if isinstance(base, ast.Name) else None
    if base_name not in {"dict", "Dict"}:
        return None
    slice_expr = annotation.slice
    args = slice_expr.elts if isinstance(slice_expr, ast.Tuple) else [slice_expr]
    if len(args) != 2:
        return None
    key, value = args
    if not (isinstance(key, ast.Name) and key.id == "str"):
        return None
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "pd"
        and value.attr == "DataFrame"
    ):
        return "dict[str, pd.DataFrame]"
    return None


def _tree_generate_signals_annotation_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return every ``generate_signals`` override that drifts from the base signature.

    Checks both the ``data`` parameter annotation (``dict[str, pd.DataFrame]``)
    and the return annotation (``list[Signal]``). Split out so a caller can feed
    it a synthetic tree (the guard's negative control does exactly that) without
    writing to disk.
    """
    mismatches: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name == "Strategy":
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "generate_signals":
                continue
            args = item.args.args
            if len(args) != 2:
                shown = ", ".join(arg.arg for arg in args) or "no parameters"
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.generate_signals has {len(args)} "
                    f"parameter(s) ({shown}), expected exactly (self, data)"
                )
                continue
            first, second = args
            if first.arg != "self":
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.generate_signals first parameter is "
                    f"{first.arg!r}, expected self"
                )
            if second.arg != "data":
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.generate_signals second parameter is "
                    f"{second.arg!r}, expected data"
                )
            data_annotation = second.annotation
            normalized_data = _normalize_generate_signals_data_annotation(data_annotation)
            if normalized_data != "dict[str, pd.DataFrame]":
                shown = ast.unparse(data_annotation) if data_annotation is not None else "untyped"
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.generate_signals data parameter is "
                    f"{shown}, expected dict[str, pd.DataFrame]"
                )
            normalized = _normalize_generate_signals_annotation(item.returns)
            if normalized != "list[Signal]":
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.generate_signals returns "
                    f"{normalized or 'untyped'}, expected list[Signal]"
                )
    return mismatches


def _documented_generate_signals_annotation_mismatches() -> list[str]:
    """Return every strategy ``generate_signals`` override that drifts from the base signature."""
    mismatches: list[str] = []
    for directory in ("quant_trading", "examples"):
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_generate_signals_annotation_mismatches(_parse(path), rel))
    return mismatches


def test_generate_signals_overrides_return_list_signal() -> None:
    """Every ``generate_signals`` override must keep the base signature annotations.

    ``Strategy.generate_signals`` declares
    ``(self, data: dict[str, pd.DataFrame]) -> list[Signal]``. A subclass that
    drifts the ``data`` parameter annotation, the parameter names, the parameter
    count, or the return annotation silently breaks callers and the backtest
    engine. This guard is purely structural (AST, no imports) and only checks
    overrides outside the base ``Strategy`` class.

    Negative controls inject a wrong return annotation, a wrong ``data``
    parameter annotation, a wrong first/second parameter name, and a wrong
    parameter count, and assert each drift is reported. A positive control with
    the canonical signature passes.
    """
    synthetic_return_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[int]:\n"
        "        return []\n"
    )
    injected = _tree_generate_signals_annotation_mismatches(
        ast.parse(synthetic_return_mismatch), "synthetic.py"
    )
    assert injected, "guard did not fire on an injected generate_signals return drift"

    synthetic_data_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def generate_signals(self, data: dict) -> list[Signal]:\n"
        "        return []\n"
    )
    injected = _tree_generate_signals_annotation_mismatches(
        ast.parse(synthetic_data_mismatch), "synthetic.py"
    )
    assert injected, "guard did not fire on an injected generate_signals data parameter drift"

    synthetic_first_param_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def generate_signals(cls, data: dict[str, pd.DataFrame]) -> list[Signal]:\n"
        "        return []\n"
    )
    injected = _tree_generate_signals_annotation_mismatches(
        ast.parse(synthetic_first_param_mismatch), "synthetic.py"
    )
    assert injected, "guard did not fire on an injected generate_signals first parameter drift"

    synthetic_second_param_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def generate_signals(self, market_data: dict[str, pd.DataFrame]) -> list[Signal]:\n"
        "        return []\n"
    )
    injected = _tree_generate_signals_annotation_mismatches(
        ast.parse(synthetic_second_param_mismatch), "synthetic.py"
    )
    assert injected, "guard did not fire on an injected generate_signals second parameter drift"

    synthetic_arg_count_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def generate_signals(self, data: dict[str, pd.DataFrame], extra: int) -> list[Signal]:\n"
        "        return []\n"
    )
    injected = _tree_generate_signals_annotation_mismatches(
        ast.parse(synthetic_arg_count_mismatch), "synthetic.py"
    )
    assert injected, "guard did not fire on an injected generate_signals parameter count drift"

    synthetic_ok = (
        "class MyStrategy(Strategy):\n"
        "    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:\n"
        "        return []\n"
    )
    assert not _tree_generate_signals_annotation_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a canonical generate_signals override"

    mismatches = _documented_generate_signals_annotation_mismatches()
    assert not mismatches, "generate_signals override signature drift:\n" + "\n".join(mismatches)


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


def test_cli_strategy_keys_match_registry() -> None:
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


def test_cli_provider_entries_match_data_providers() -> None:
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


def test_class_docstring_is_first_statement() -> None:
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
            first_is_docstring = _is_docstring_expr(first)
            if first_is_docstring:
                continue
            for stmt in node.body[1:]:
                if _is_docstring_expr(stmt):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno} ({node.name})")
                    break
    assert not offenders, "stray class docstring not first:\n" + "\n".join(offenders)


def test_module_docstring_is_first_statement() -> None:
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
        first_is_docstring = _is_docstring_expr(first)
        if first_is_docstring:
            continue
        for stmt in tree.body[1:]:
            if _is_docstring_expr(stmt):
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


def test_readme_features_list_advertises_all_optimizers() -> None:
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


# Public functions the README's Features list must advertise for the
# parameter sensitivity module. Kept in sync with
# ``quant_trading.optimization.sensitivity.__all__``; the README is the
# user-facing contract and silently dropping a sensitivity entry from it is a
# real regression.
_SENSITIVITY_FEATURE_MARKERS: dict[str, str] = {
    "generate_sensitivity_report_html": "generate_sensitivity_report_html",
    "SensitivityConfig": "SensitivityConfig",
    "create_1d_sensitivity_plot": "1D",
    "create_2d_sensitivity_heatmap": "2D",
    "create_parameter_interaction_heatmap": "interaction heatmap",
}


def test_readme_features_list_advertises_sensitivity_analysis() -> None:
    """The README "Features" bullet must advertise the sensitivity analysis API.

    The Features list is the first thing a reader sees. If a sensitivity
    function is added to the package but the bullet is not updated, users will
    not know it exists, even though it is fully wired into the CLI and tests.
    """
    from quant_trading.optimization import sensitivity

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    features_start = readme.index("**Parameter Optimization**:")
    features_end = readme.index("\n## ", features_start)
    features_line = readme[features_start:features_end]

    exported = set(sensitivity.__all__)
    missing: list[str] = []
    for name, marker in _SENSITIVITY_FEATURE_MARKERS.items():
        if name in exported and marker.lower() not in features_line.lower():
            missing.append(f"{name} (marker '{marker}')")
    assert (
        not missing
    ), "README Features bullet does not advertise every sensitivity function:\n" + "\n".join(
        missing
    )


def test_strategies_init_all_exports_exist() -> None:
    """Every name in quant_trading.strategies.__all__ must be importable."""
    import quant_trading.strategies as mod

    missing = [name for name in mod.__all__ if not hasattr(mod, name)]
    assert not missing, "strategies.__all__ names missing from module: " + ", ".join(missing)


def test_all_package_all_exports_resolve() -> None:
    """Every name in every package's __all__ must be bound to a module attribute.

    A name listed in ``__all__`` that is not defined or imported in the package
    __init__ is a silent export hole: ``from package import name`` raises
    AttributeError even though the package advertises the name.
    """
    failures: list[str] = []
    for init in sorted((REPO_ROOT / "quant_trading").rglob("__init__.py")):
        rel = init.relative_to(REPO_ROOT)
        pkg = init.parent.relative_to(REPO_ROOT / "quant_trading").as_posix().replace("/", ".")
        if pkg == ".":
            pkg = ""
        modname = "quant_trading" + (f".{pkg}" if pkg else "")
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:  # noqa: BLE001 - report any import-time failure
            failures.append(f"{modname}: cannot import: {exc!r}")
            continue
        missing = [name for name in getattr(mod, "__all__", []) if not hasattr(mod, name)]
        if missing:
            failures.append(f"{rel}: unbound __all__ names: {', '.join(missing)}")
    assert not failures, "package __all__ exports not bound:\n" + "\n".join(failures)


def test_package_reexports_are_listed_in_defining_module_all() -> None:
    """A name a package re-exports must also be listed in its defining module's __all__.

    ``test_all_package_all_exports_resolve`` guards the other direction: a name
    advertised by a package ``__init__`` must be bound to an attribute there.
    This guard covers the re-export hole that direction cannot see. A package
    can re-export a name it defines in a submodule (``from .base import
    BaseStrategy``) while that submodule's own ``__all__`` omits it. The
    package still resolves ``from package import BaseStrategy``, so every
    existing check passes, but ``from package.base import *`` silently drops
    the name. The two lists then drift apart and the submodule's declared
    public surface is wrong.

    The check is one-way (package -> defining module) and only applies when the
    defining module declares an ``__all__`` at all; a module that relies on the
    default (every non-underscore global) has no list to keep in sync.
    """
    failures: list[str] = []
    for init in sorted((REPO_ROOT / "quant_trading").rglob("__init__.py")):
        rel = init.relative_to(REPO_ROOT)
        pkg = init.parent.relative_to(REPO_ROOT / "quant_trading").as_posix().replace("/", ".")
        if pkg == ".":
            pkg = ""
        modname = "quant_trading" + (f".{pkg}" if pkg else "")
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:  # noqa: BLE001 - report any import-time failure
            failures.append(f"{modname}: cannot import: {exc!r}")
            continue
        pkg_all = getattr(mod, "__all__", None)
        if pkg_all is None:
            continue

        # Map each name the package re-exports back to the submodule it was
        # imported from, using relative ``from .module import name`` statements.
        tree = _parse(init)
        origin: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level != 1 or not node.module:
                continue
            for alias in node.names:
                origin[alias.asname or alias.name] = f"{modname}.{node.module}"

        for name in pkg_all:
            source_module = origin.get(name)
            if source_module is None:
                continue
            try:
                source = importlib.import_module(source_module)
            except Exception:  # noqa: BLE001, S112 - unimportable module reported by test above
                continue
            source_all = getattr(source, "__all__", None)
            if source_all is None:
                continue
            if name not in source_all:
                failures.append(
                    f"{rel}: re-exports {name} from {source_module}, "
                    f"but it is missing from that module's __all__"
                )
    assert not failures, "package re-exports missing from defining module __all__:\n" + "\n".join(
        failures
    )


def _cli_arg_defaults_node(tree: ast.Module) -> ast.Dict:
    """Return the ``CLI_ARG_DEFAULTS`` dict node parsed from ``examples/cli.py``."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "CLI_ARG_DEFAULTS"
                and isinstance(node.value, ast.Dict)
            ):
                return node.value
    raise AssertionError("CLI_ARG_DEFAULTS not found in examples/cli.py")


def _cli_default_values(tree: ast.Module) -> dict[str, object]:
    """Return the ``CLI_ARG_DEFAULTS`` mapping parsed from ``examples/cli.py``."""
    return cast(dict[str, object], ast.literal_eval(_cli_arg_defaults_node(tree)))


def _cli_strategy_param_map(tree: ast.Module) -> dict[str, list[tuple[str, str]]]:
    """Return the ``strategy_param_map`` parsed from ``examples/cli.py``.

    The map lives inside ``create_strategy`` and is the single authoritative
    mapping from CLI argument names to strategy ``__init__`` parameter names for
    the strategies the CLI exposes with custom flags. It is parsed (not
    imported) so the CLI's optional runtime dependencies are not required.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "create_strategy":
            continue
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "strategy_param_map"
                    and isinstance(stmt.value, ast.Dict)
                ):
                    return cast(dict[str, list[tuple[str, str]]], ast.literal_eval(stmt.value))
    raise AssertionError("strategy_param_map not found in create_strategy")


def test_cli_arg_defaults_match_strategy_init_defaults() -> None:
    """CLI defaults for mapped strategy parameters must match the class defaults.

    ``examples/cli.py`` declares ``CLI_ARG_DEFAULTS`` and maps them onto
    strategy ``__init__`` parameters in ``strategy_param_map``. A mismatch means
    the CLI silently runs with different defaults than the library, so users
    get different behaviour depending on the entry point. This guard locks the
    two in sync for every mapped (strategy, cli_arg, param) triple.

    A small, explicit allowlist documents the intentional exceptions where the
    CLI and class defaults are known to diverge: ``ema`` reuses the shared
    ``--fast-period``/``--slow-period`` flags (whose defaults follow the MA
    convention, 10/30) while ``EMACrossover`` declares its own canonical class
    defaults (12/26). The allowlist is keyed by (strategy, cli_arg, param) so a
    new drift cannot slip in unnoticed.
    """
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    cli_defaults = _cli_default_values(tree)
    param_map = _cli_strategy_param_map(tree)

    # (strategy, cli_arg, param, cli_default, class_default) -> rationale
    # Intentional, documented drifts only. Add an entry here only after
    # deciding which side is canonical and documenting why they differ.
    allowed_drifts: set[tuple[str, str, str]] = {
        # EMA shares --fast-period/--slow-period (MA-style 10/30) but the
        # EMACrossover class declares canonical 12/26 defaults.
        ("ema", "fast_period", "fast_period"),
        ("ema", "slow_period", "slow_period"),
    }

    from quant_trading.strategies import get_strategy

    failures: list[str] = []
    for strategy_key, pairs in sorted(param_map.items()):
        if not pairs:
            continue
        cls = get_strategy(strategy_key)
        assert cls is not None
        signature = inspect.signature(cls)
        for cli_arg, param_name in pairs:
            if cli_arg not in cli_defaults:
                failures.append(f"{strategy_key}: {cli_arg} missing from CLI_ARG_DEFAULTS")
                continue
            if param_name not in signature.parameters:
                failures.append(f"{strategy_key}: {param_name} not a parameter of {cls.__name__}")
                continue
            class_default = signature.parameters[param_name].default
            if class_default is inspect.Parameter.empty:
                continue
            cli_default = cli_defaults[cli_arg]
            if cli_default == class_default:
                continue
            if (strategy_key, cli_arg, param_name) in allowed_drifts:
                continue
            failures.append(
                f"{strategy_key}: CLI {cli_arg}={cli_default!r} "
                f"!= {cls.__name__}.{param_name} default {class_default!r}"
            )
    assert not failures, "CLI defaults drift from strategy __init__ defaults:\n" + "\n".join(
        failures
    )


def _cli_flag_defaults(tree: ast.Module) -> dict[str, dict[str, object]]:
    """Map each argparse ``dest`` to the spec of the flag it defaults from.

    Only flags whose ``default=`` is a ``CLI_ARG_DEFAULTS["..."]`` lookup are
    returned, keyed by the resolved ``dest`` (``--foo-bar`` -> ``foo_bar``).
    Each value is a dict with three keys:

    * ``"default_key"``: the ``CLI_ARG_DEFAULTS`` key the flag's ``default=``
      reads from (always a ``str`` here);
    * ``"type"``: the name of the ``type=`` callable as a string, or ``None``
      when the flag declares no ``type=`` (e.g. ``store_true``/``store_false``
      flags, which are the common case for booleans);
    * ``"action"``: the ``action=`` keyword as a string, or ``None``.

    Parsing the AST (rather than importing the CLI) keeps the guard
    independent of the CLI's optional runtime dependencies.
    """
    flags: dict[str, dict[str, object]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        flag = node.args[0].value
        if not isinstance(flag, str) or not flag.startswith("--"):
            continue
        dest = flag.lstrip("-").replace("-", "_")
        default_key = None
        type_name: str | None = None
        action_name: str | None = None
        for keyword in node.keywords:
            if keyword.arg == "dest" and isinstance(keyword.value, ast.Constant):
                dest = cast(str, keyword.value.value)
            elif keyword.arg == "action" and isinstance(keyword.value, ast.Constant):
                action_name = cast(str | None, keyword.value.value)
            elif keyword.arg == "type" and isinstance(keyword.value, ast.Name):
                type_name = keyword.value.id
            if keyword.arg != "default":
                continue
            value = keyword.value
            if (
                isinstance(value, ast.Subscript)
                and isinstance(value.value, ast.Name)
                and value.value.id == "CLI_ARG_DEFAULTS"
                and isinstance(value.slice, ast.Constant)
            ):
                default_key = value.slice.value
        if default_key is not None:
            flags[dest] = {"default_key": default_key, "type": type_name, "action": action_name}
    return flags


def test_cli_arg_defaults_entries_are_used_by_a_flag() -> None:
    """Every ``CLI_ARG_DEFAULTS`` entry must back a real argparse flag default.

    ``CLI_ARG_DEFAULTS`` is the single source of truth the CLI's argument
    defaults are wired from. An entry with no matching ``--flag`` whose
    ``default=`` reads ``CLI_ARG_DEFAULTS[key]`` is dead configuration: it
    silently drifts from the flag it was meant to document and misleads anyone
    auditing CLI/class default parity. This guard fails when an entry is unused
    or when a flag references a key that no longer exists.
    """
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    defaults_node = _cli_arg_defaults_node(tree)
    defined = {
        key.value
        for key in defaults_node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    flag_defaults = _cli_flag_defaults(tree)
    used_keys: set[str] = {cast(str, spec["default_key"]) for spec in flag_defaults.values()}

    unused = sorted(defined - used_keys)
    dangling = sorted(used_keys - defined)

    failures: list[str] = []
    if unused:
        failures.append(f"CLI_ARG_DEFAULTS entries not used by any flag: {unused}")
    if dangling:
        failures.append(f"flag defaults reference missing CLI_ARG_DEFAULTS keys: {dangling}")
    assert not failures, "CLI_ARG_DEFAULTS wiring is inconsistent:\n" + "\n".join(failures)


def _cli_default_type_mismatches(
    flag_defaults: dict[str, dict[str, object]], cli_defaults: dict[str, object]
) -> list[str]:
    """Return every ``type=``/``action=`` vs default incompatibility found.

    A flag whose ``default=`` reads ``CLI_ARG_DEFAULTS[key]`` is only meaningful
    if the ``type=`` callable it declares can consume that default value. A
    mismatch (e.g. an ``int`` default wired to a ``type=str`` flag, or a
    non-boolean default wired to a ``store_true`` flag) is a latent bug: the
    flag would coerce user input differently from the documented default, so
    the CLI would silently run with a different value than the class.

    A ``None`` default is allowed for any type: argparse uses the default only
    when the flag is absent, so ``None`` means "not supplied" (the only such
    entry in ``CLI_ARG_DEFAULTS`` is ``dc_exit_period``).
    """
    failures: list[str] = []
    for dest, spec in sorted(flag_defaults.items()):
        key = cast(str, spec["default_key"])
        default_value = cli_defaults[key]
        type_name = spec["type"]
        action = spec["action"]

        if action in ("store_true", "store_false"):
            if not isinstance(default_value, bool):
                failures.append(
                    f"{dest}: {action} flag defaults to {default_value!r} "
                    f"({key}), which is not a bool"
                )
            continue

        if type_name is None:
            continue

        if default_value is None:
            continue

        if type_name == "int":
            if isinstance(default_value, bool) or not isinstance(default_value, int):
                failures.append(
                    f"{dest}: type=int flag defaults to {default_value!r} ({key}), "
                    "which is not an int"
                )
        elif type_name == "float":
            if isinstance(default_value, bool) or not isinstance(default_value, (int, float)):
                failures.append(
                    f"{dest}: type=float flag defaults to {default_value!r} ({key}), "
                    "which is not a float"
                )
        elif type_name == "str":
            if not isinstance(default_value, str):
                failures.append(
                    f"{dest}: type=str flag defaults to {default_value!r} ({key}), "
                    "which is not a str"
                )
        else:
            failures.append(
                f"{dest}: unknown type={type_name!r} for default {default_value!r} ({key})"
            )
    return failures


def test_cli_arg_defaults_type_matches_default() -> None:
    """Each ``CLI_ARG_DEFAULTS``-backed flag's ``type=`` must fit its default.

    A flag whose ``default=`` reads ``CLI_ARG_DEFAULTS[key]`` is only meaningful
    if the ``type=`` callable it declares can consume that default value. A
    mismatch (e.g. an ``int`` default wired to a ``type=str`` flag, or a
    non-boolean default wired to a ``store_true`` flag) is a latent bug: the
    flag would coerce user input differently from the documented default, so
    the CLI would silently run with a different value than the class.

    The check is purely structural (AST), not runtime, so it stays cheap and
    independent of the CLI's optional runtime dependencies. The only ``None``
    default in ``CLI_ARG_DEFAULTS`` is ``dc_exit_period``; argparse accepts a
    ``None`` default for an ``int`` flag because the flag is optional and the
    default is only used when the flag is absent.
    """
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    cli_defaults = _cli_default_values(tree)
    flag_defaults = _cli_flag_defaults(tree)

    # Negative control: mutate a parsed default in memory (no source edit) and
    # confirm the guard fires, proving it detects the drift it guards against.
    original = cli_defaults["rsi_period"]
    cli_defaults["rsi_period"] = "fourteen"
    try:
        injected = _cli_default_type_mismatches(flag_defaults, cli_defaults)
        assert injected, "guard did not fire on injected type/default drift"
    finally:
        cli_defaults["rsi_period"] = original

    failures = _cli_default_type_mismatches(flag_defaults, cli_defaults)
    assert not failures, "CLI_ARG_DEFAULTS type/default mismatch:\n" + "\n".join(failures)


def _cli_range_flags(tree: ast.Module) -> dict[str, str]:
    """Map each ``--*-range`` flag's dest to its string default.

    Range arguments are declared with ``type=str`` and an inline string default
    such as ``"5,15,5"`` rather than a ``CLI_ARG_DEFAULTS["..."]`` lookup, so
    they are not covered by the ``CLI_ARG_DEFAULTS`` guards. This helper parses
    them out directly from the AST.
    """
    flags: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        flag = node.args[0].value
        if not isinstance(flag, str) or not flag.startswith("--") or not flag.endswith("-range"):
            continue
        dest = flag.lstrip("-").replace("-", "_")
        default_value: str | None = None
        for keyword in node.keywords:
            if (
                keyword.arg == "default"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                default_value = keyword.value.value
        if default_value is not None:
            flags[dest] = default_value
    return flags


def _parse_range_default(default: str) -> tuple[float, float, float] | None:
    """Validate a range default string ``min,max,step`` and return its parts.

    Mirrors the runtime ``parse_range`` contract: exactly three comma-separated
    numbers, a step greater than zero, and a minimum not greater than the
    maximum. Returns ``None`` for any malformed value so callers can treat it
    as a failure.
    """
    parts = default.split(",")
    if len(parts) != 3:
        return None
    try:
        minimum, maximum, step = (float(part) for part in parts)
    except ValueError:
        return None
    if step <= 0:
        return None
    if minimum > maximum:
        return None
    return minimum, maximum, step


def _cli_range_default_failures(range_flags: dict[str, str]) -> list[str]:
    """Return every ``--*-range`` flag whose default is not a valid range."""
    failures: list[str] = []
    for dest, default in sorted(range_flags.items()):
        if _parse_range_default(default) is None:
            failures.append(
                f"--{dest.replace('_', '-')}: default {default!r} "
                "is not a valid 'min,max,step' range"
            )
    return failures


def test_cli_range_defaults_match_parse_range_format() -> None:
    """Every ``--*-range`` flag default must be a valid ``min,max,step`` range.

    Range flags are parsed at runtime by ``parse_range``, which requires
    exactly three comma-separated numbers, a step greater than zero, and a
    minimum not greater than the maximum. A malformed default would slip past
    argument parsing and surface as a runtime ``ValueError`` mid-run instead of
    being caught when the parser is built. This guard validates every
    ``--*-range`` default at parse time so a drifted default cannot reach a run.

    The check is purely structural (AST): it parses ``examples/cli.py`` without
    importing it, keeping the guard independent of the CLI's optional runtime
    dependencies.
    """
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    range_flags = _cli_range_flags(tree)
    assert range_flags, "no --*-range flags found in examples/cli.py"

    # Negative control: corrupt one parsed default in memory (no source edit)
    # and confirm the guard fires, proving it detects malformed range defaults.
    first_dest = next(iter(range_flags))
    original = range_flags[first_dest]
    range_flags[first_dest] = "not,a,range"
    try:
        injected = _cli_range_default_failures(range_flags)
        assert injected, "guard did not fire on injected malformed range default"
    finally:
        range_flags[first_dest] = original

    failures = _cli_range_default_failures(range_flags)
    assert not failures, "malformed --*-range defaults:\n" + "\n".join(failures)


def _tunable_init_params(strategy_cls: type) -> list[str]:
    """Return the ``__init__`` parameters a caller can tune, in declaration order.

    ``name`` and ``parameters`` are framework plumbing rather than strategy
    tunables, and ``*args``/``**kwargs`` cannot be set by name, so all three are
    excluded. A parameter counts as tunable when it declares a default; required
    parameters are also returned because callers must be able to supply them.
    """
    signature = inspect.signature(strategy_cls)
    tunables: list[str] = []
    for name, parameter in signature.parameters.items():
        if name in ("self", "name", "parameters"):
            continue
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        tunables.append(name)
    return tunables


# Registered strategies that intentionally expose no dedicated CLI flag for
# their tunable ``__init__`` parameters.
#
# ``create_strategy`` only wires custom flags for strategies listed in
# ``strategy_param_map``; every other registered strategy is constructed via
# ``factory_create_strategy(args.strategy)`` and therefore always runs with its
# class defaults. Users tune those strategies through ``--strategy-config``,
# whose ``parameters`` mapping is forwarded verbatim to the constructor by
# ``Strategy.from_config``.
#
# This is a deliberate design choice, not an oversight: adding a dedicated
# ``--<name>-period`` flag for each of these strategies would duplicate the
# class API and bloat the parser. The allowlist makes the choice explicit so a
# newly registered strategy cannot silently ship with an accidental CLI coverage
# gap. Add an entry here only after deciding the strategy is intentionally
# config-file-only; add flags + ``strategy_param_map`` entries instead when the
# parameter is a common enough knob to deserve a first-class flag.
_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS: frozenset[str] = frozenset(
    {
        "adl",
        "ao",
        "bbpct",
        "cci",
        "cho",
        "cmf",
        "cmo",
        "dpo",
        "elder_ray",
        "eom",
        "fisher",
        "force_index",
        "hma",
        "klinger",
        "kst",
        "ma_envelope",
        "mfi",
        "momentum",
        "nvi",
        "obv",
        "ppo",
        "pvi",
        "pvo",
        "roc",
        "smi",
        "stochrsi",
        "trix",
        "ultimate_oscillator",
        "vol",
        "vortex",
        "vpt",
        "vroc",
        "williamsr",
        "tsi",
        "rvi",
    }
)


def test_registered_strategies_have_documented_cli_coverage() -> None:
    """Every strategy with tunable defaults is CLI-mapped or allowlisted.

    ``create_strategy`` exposes dedicated flags only for strategies in
    ``strategy_param_map``; all other registered strategies are built from their
    class defaults and tuned via ``--strategy-config``. That is a valid design,
    but the choice must be explicit so a newly registered strategy cannot ship
    with an accidental coverage gap.

    The guard fails when a registered strategy declares tunable ``__init__``
    parameters but is neither mapped to dedicated flags nor listed in
    ``_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS``. It also rejects stale allowlist
    entries (unregistered, already mapped, or no longer tunable) and mapping
    entries that do not correspond to a registered strategy. For mapped
    strategies it requires every tunable parameter to be exposed by a flag, so a
    partial mapping cannot hide a parameter behind the class default.
    """
    cli_path = REPO_ROOT / "examples" / "cli.py"
    tree = _parse(cli_path)
    param_map = _cli_strategy_param_map(tree)

    from quant_trading.strategies import list_strategies

    registered = list_strategies()
    failures: list[str] = []

    for strategy_key, pairs in sorted(param_map.items()):
        strategy_cls = registered.get(strategy_key)
        if strategy_cls is None:
            failures.append(f"strategy_param_map key {strategy_key!r} is not a registered strategy")
            continue
        tunables = _tunable_init_params(strategy_cls)
        mapped = {param_name for _, param_name in pairs}
        unmapped = sorted(set(tunables) - mapped)
        if unmapped:
            failures.append(
                f"{strategy_key}: tunable __init__ params not exposed by a dedicated "
                f"CLI flag: {unmapped}"
            )

    for strategy_key, strategy_cls in sorted(registered.items()):
        if strategy_key in param_map:
            continue
        tunables = _tunable_init_params(strategy_cls)
        if not tunables:
            continue
        if strategy_key in _STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS:
            continue
        failures.append(
            f"{strategy_key} ({strategy_cls.__name__}) has tunable __init__ params "
            f"{tunables} but is neither in strategy_param_map nor in "
            f"_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS"
        )

    for strategy_key in sorted(_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS):
        strategy_cls = registered.get(strategy_key)
        if strategy_cls is None:
            failures.append(f"allowlist entry {strategy_key!r} is not a registered strategy")
            continue
        if strategy_key in param_map:
            failures.append(
                f"allowlist entry {strategy_key!r} is already wired to dedicated CLI flags"
            )
            continue
        if not _tunable_init_params(strategy_cls):
            failures.append(
                f"allowlist entry {strategy_key!r} has no tunable __init__ params; remove it"
            )

    assert not failures, "CLI strategy coverage is incomplete:\n" + "\n".join(failures)


def test_cli_strategy_imports_exist() -> None:
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


def test_example_scripts_import_from_strategies_examples_exist() -> None:
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


def test_example_scripts_quant_trading_imports_exist() -> None:
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


def test_cli_quant_trading_imports_exist() -> None:
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


def test_readme_quant_trading_imports_exist() -> None:
    """Names imported from quant_trading.* in README code blocks must exist."""
    import ast
    import importlib
    import re

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    failures: list[str] = []
    # Collect import statements from fenced code blocks.
    for block in re.finditer(r"```(?:python|bash)?\n(?P<body>.*?)```", readme, re.DOTALL):
        for line in block.group("body").splitlines():
            line = line.strip()
            if not line.startswith("from quant_trading") and not line.startswith(
                "import quant_trading"
            ):
                continue
            try:
                tree = ast.parse(line)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("quant_trading")
                ):
                    try:
                        mod = importlib.import_module(node.module)
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"README: cannot import {node.module}: {exc!r}")
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        if not hasattr(mod, alias.name):
                            failures.append(f"README: {alias.name} missing from {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("quant_trading"):
                            try:
                                importlib.import_module(alias.name)
                            except Exception as exc:  # noqa: BLE001
                                failures.append(f"README: cannot import {alias.name}: {exc!r}")
    assert not failures, "README imports missing:\n" + "\n".join(failures)


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


def test_no_duplicate_example_script_demos() -> None:
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


# A strategy-constructor signature: (class name, positional args, keyword args).
# ``ast.dump`` gives a stable, location-independent representation of each
# argument so two calls can be compared for structural equality.
_StrategySignature = tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]


def _strategy_demo_signature(call: ast.Call, class_name: str) -> _StrategySignature:
    """Return a hashable signature for a strategy constructor call.

    The signature is the class name, the positional arguments, and the keyword
    arguments sorted by name. The cosmetic ``name=`` keyword is excluded so two
    demos that differ only in the strategy's display name still compare equal.
    """
    positional = tuple(ast.dump(arg) for arg in call.args)
    keywords: list[tuple[str, str]] = []
    for keyword in call.keywords:
        if keyword.arg is None or keyword.arg == "name":
            continue
        keywords.append((keyword.arg, ast.dump(keyword.value)))
    keywords.sort()
    return (class_name, positional, tuple(keywords))


def _strategy_demo_signatures(tree: ast.Module) -> list[_StrategySignature]:
    """Return the signature of every direct strategy constructor call in a module."""
    signatures: list[_StrategySignature] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id.endswith("Strategy")
        ):
            signatures.append(_strategy_demo_signature(node, node.func.id))
    return signatures


def _duplicate_single_strategy_signatures(
    scripts: dict[str, list[_StrategySignature]],
) -> list[str]:
    """Return a description of every signature shared by two or more scripts.

    Only scripts that construct exactly one strategy are considered. Scripts
    that construct several strategies (the ``run_backtest*`` demos) or none
    (the analysis/optimization demos) are exempt, because those legitimately
    reuse a strategy configuration as one part of a broader demonstration.
    """
    seen: dict[_StrategySignature, list[str]] = {}
    for name, signatures in scripts.items():
        if len(signatures) != 1:
            continue
        seen.setdefault(signatures[0], []).append(name)
    offenders: list[str] = []
    for signature, names in seen.items():
        if len(names) > 1:
            offenders.append(f"{signature[0]} {signature[2]}: {names}")
    return offenders


def test_no_duplicate_single_strategy_example_scripts() -> None:
    """Two example scripts must not demo the same strategy the same way.

    A pair of example scripts that each construct exactly one strategy with the
    same class and arguments are functional duplicates: the second is dead
    documentation that drifts out of sync with the first (the defect that left
    ``run_klinger.py`` and ``run_klinger_oscillator.py`` as byte-for-byte
    equivalents apart from their docstrings). This guard fails when such a pair
    exists so the redundancy cannot silently return.

    The check is purely structural (AST): it parses each script without
    importing it, keeping the guard independent of runtime dependencies.
    """
    scripts: dict[str, list[_StrategySignature]] = {}
    for path in sorted((REPO_ROOT / "examples").glob("run_*.py")):
        scripts[path.name] = _strategy_demo_signatures(_parse(path))

    # Negative control: a synthetic pair that shares one signature must be
    # reported, proving the detector fires on the defect it guards against.
    synthetic: dict[str, list[_StrategySignature]] = {
        "run_a.py": [("RSIStrategy", (), (("period", "Constant(value=14)"),))],
        "run_b.py": [("RSIStrategy", (), (("period", "Constant(value=14)"),))],
    }
    assert _duplicate_single_strategy_signatures(
        synthetic
    ), "guard did not fire on an injected duplicate single-strategy demo"

    offenders = _duplicate_single_strategy_signatures(scripts)
    assert not offenders, "duplicate single-strategy example scripts:\n" + "\n".join(offenders)


def test_no_example_script_refs_outside_example_scripts_section() -> None:
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


def test_example_scripts_section_has_code_block_for_every_ref() -> None:
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


def test_readme_license_is_the_final_section() -> None:
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


def test_no_duplicate_section_titles() -> None:
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


_CODE_BLOCK_LANGUAGE = re.compile(r"^\s*```(?P<lang>\w*)")
_SUPPORTED_CODE_BLOCK_LANGUAGES: frozenset[str] = frozenset({"", "bash", "python", "yaml"})


def _readme_opening_fences() -> list[tuple[int, str]]:
    """Return ``(line_number, language)`` for each opening fenced code block.

    Closing fences are ignored by tracking whether a block is currently open,
    so a block's own closing fence (which carries no language) is not mistaken
    for an untagged opening block.
    """
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    fences: list[tuple[int, str]] = []
    in_block = False
    for index, line in enumerate(text.splitlines(), 1):
        match = _CODE_BLOCK_LANGUAGE.match(line)
        if not match:
            continue
        if in_block:
            in_block = False
            continue
        fences.append((index, match.group("lang")))
        in_block = True
    return fences


def test_readme_code_block_language_tags_are_supported() -> None:
    """Every fenced code block must use a supported language tag.

    Supported tags are ``bash``, ``python``, ``yaml`` and an untagged block
    (console output, tree diagrams). A misspelled or unsupported tag renders
    the block as plain text and hides syntax highlighting from readers.
    """
    offenders = [
        f"README:{line}: unsupported code-block language {tag!r}"
        for line, tag in _readme_opening_fences()
        if tag and tag not in _SUPPORTED_CODE_BLOCK_LANGUAGES
    ]
    assert not offenders, "unsupported README code-block language tags:\n" + "\n".join(offenders)


def test_readme_backtick_quant_trading_names_resolve() -> None:
    """Every ``quant_trading.*`` dotted name in README backticks must resolve."""
    import importlib

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    failures: list[str] = []
    for span in re.finditer(r"`[^`]*`", readme):
        for match in re.finditer(r"quant_trading(?:\.[A-Za-z_][A-Za-z0-9_]*)+", span.group(0)):
            dotted = match.group(0)
            try:
                importlib.import_module(dotted)
            except (ImportError, AttributeError) as exc:
                failures.append(f"{dotted}: {exc!r}")
    assert not failures, "README backtick quant_trading names unresolvable:\n" + "\n".join(failures)


# User-facing source the docstring-default guard scans. The library API and the
# copyable examples are what a reader trusts; internal test helpers are excluded
# so the guard cannot misfire on a test-local docstring.
_DOC_SCAN_DIRS = ("quant_trading", "examples")


# Existing functions with empty or malformed Examples/Example sections.
# Grandfathered in so the guard prevents new debt without failing on today's state.
# Remove an entry when the section is fixed; never add entries for new code --
# new Examples/Example sections must be non-empty and have parseable doctests.
_EXAMPLES_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("examples/cli.py", "_default_param_grid"),
        ("examples/cli.py", "_get_monte_carlo_analysis"),
        ("examples/cli.py", "_get_regime_analysis"),
        ("examples/cli.py", "_get_trade_analysis"),
        ("examples/cli.py", "_is_supported_interval"),
        ("examples/cli.py", "_print_monte_carlo_analysis"),
        ("examples/cli.py", "_print_regime_analysis"),
        ("examples/cli.py", "_print_trade_analysis"),
        ("examples/cli.py", "_run_cli"),
        ("examples/cli.py", "_save_json_output"),
        ("examples/cli.py", "_save_strategy_config"),
        ("examples/cli.py", "_validate_range_arguments"),
        ("examples/cli.py", "_write_report"),
        ("examples/cli.py", "create_config"),
        ("examples/cli.py", "create_param_grid"),
        ("examples/cli.py", "create_strategy"),
        ("examples/cli.py", "init_config"),
        ("examples/cli.py", "main"),
        ("examples/cli.py", "parse_range"),
        ("examples/cli.py", "run_combined"),
        ("examples/cli.py", "run_optimization"),
        ("examples/cli.py", "run_walk_forward"),
        ("examples/cli.py", "validate_config"),
        ("examples/run_analysis.py", "main"),
        ("examples/run_optimization.py", "main"),
        ("quant_trading/backtest/analysis.py", "analyze_regimes"),
        ("quant_trading/backtest/analysis.py", "current_regime"),
        ("quant_trading/backtest/analysis.py", "n_segments"),
        ("quant_trading/backtest/analysis.py", "regime_for_backtest"),
        ("quant_trading/backtest/analysis.py", "segments"),
        ("quant_trading/backtest/analysis.py", "summary"),
        ("quant_trading/backtest/analysis.py", "to_dataframe"),
        ("quant_trading/backtest/analysis.py", "to_dict"),
        ("quant_trading/backtest/engine.py", "_benchmark_returns"),
        ("quant_trading/backtest/engine.py", "_cover_short"),
        ("quant_trading/backtest/engine.py", "_open_long"),
        ("quant_trading/backtest/engine.py", "_open_short"),
        ("quant_trading/backtest/engine.py", "_process_signal"),
        ("quant_trading/backtest/engine.py", "_process_stop_exits"),
        ("quant_trading/backtest/engine.py", "_reduce_long"),
        ("quant_trading/backtest/engine.py", "_resolve_backtest_config"),
        ("quant_trading/backtest/engine.py", "_resolve_data_interval"),
        ("quant_trading/backtest/engine.py", "fee"),
        ("quant_trading/backtest/engine.py", "run_backtest"),
        ("quant_trading/backtest/report.py", "_build_comparison_risk_attribution"),
        ("quant_trading/backtest/report.py", "_build_comparison_summary_cards"),
        ("quant_trading/backtest/report.py", "_build_comparison_table"),
        ("quant_trading/backtest/report.py", "_build_metrics_table"),
        ("quant_trading/backtest/report.py", "_build_risk_attribution_table"),
        ("quant_trading/backtest/report.py", "_build_trades_table"),
        ("quant_trading/backtest/report.py", "_check_matplotlib"),
        ("quant_trading/backtest/report.py", "_create_comparison_drawdown_chart"),
        ("quant_trading/backtest/report.py", "_create_comparison_equity_chart"),
        ("quant_trading/backtest/report.py", "_create_comparison_monthly_returns_heatmap"),
        ("quant_trading/backtest/report.py", "_create_comparison_risk_attribution_chart"),
        ("quant_trading/backtest/report.py", "_create_comparison_rolling_sharpe_chart"),
        ("quant_trading/backtest/report.py", "_create_comparison_rolling_volatility_chart"),
        ("quant_trading/backtest/report.py", "_create_comparison_trade_distribution_chart"),
        ("quant_trading/backtest/report.py", "_create_drawdown_chart"),
        ("quant_trading/backtest/report.py", "_create_equity_curve_chart"),
        ("quant_trading/backtest/report.py", "_create_monthly_returns_heatmap"),
        ("quant_trading/backtest/report.py", "_create_rolling_sharpe_chart"),
        ("quant_trading/backtest/report.py", "_create_rolling_volatility_chart"),
        ("quant_trading/backtest/report.py", "_create_trade_distribution_chart"),
        ("quant_trading/backtest/report.py", "_drawdown_series"),
        ("quant_trading/backtest/report.py", "_finite_series"),
        ("quant_trading/backtest/report.py", "_fig_to_base64"),
        ("quant_trading/backtest/report.py", "_get_css"),
        ("quant_trading/backtest/report.py", "_get_theme_colors"),
        ("quant_trading/backtest/report.py", "generate_comparison_report"),
        ("quant_trading/backtest/report.py", "generate_html_report"),
        ("quant_trading/backtest/report.py", "generate_report_from_dict"),
        ("quant_trading/backtest/report.py", "to_dict"),
        ("quant_trading/config/settings.py", "_check_field_types"),
        ("quant_trading/config/settings.py", "_to_dict"),
        ("quant_trading/config/settings.py", "_type_matches"),
        ("quant_trading/data/yfinance_provider.py", "_build_batch_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_commodity_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_crypto_daily_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_crypto_intraday_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_crypto_monthly_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_crypto_weekly_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_currency_exchange_rate_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_daily_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_economic_indicator_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_fx_daily_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_fx_intraday_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_global_quote_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_gold_history_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_gold_spot_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_intraday_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_market_status_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_monthly_adjusted_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_monthly_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_sector_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_symbol_search_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_technical_indicator_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_weekly_adjusted_params"),
        ("quant_trading/data/yfinance_provider.py", "_build_weekly_params"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_batch"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_commodity"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_crypto_daily"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_crypto_intraday"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_crypto_monthly"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_crypto_weekly"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_currency_exchange_rate"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_economic_indicator"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_fx_daily"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_fx_intraday"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_global_quote"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_gold"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_group"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_intraday"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_market_status"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_monthly"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_monthly_adjusted"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_sector_performance"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_single"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_symbol_search"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_technical_indicator"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_weekly"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_weekly_adjusted"),
        ("quant_trading/data/yfinance_provider.py", "_get_yf"),
        ("quant_trading/data/yfinance_provider.py", "_parse_batch_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_crypto_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_currency_exchange_rate_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_daily_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_download"),
        ("quant_trading/data/yfinance_provider.py", "_parse_fx_daily_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_fx_intraday_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_global_quote_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_intraday_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_market_status_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_monthly_adjusted_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_monthly_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_sector_performance_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_single_series_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_symbol_search_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_technical_indicator_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_weekly_adjusted_response"),
        ("quant_trading/data/yfinance_provider.py", "_parse_weekly_response"),
        ("quant_trading/data/yfinance_provider.py", "_slice_group_result"),
        ("quant_trading/data/yfinance_provider.py", "fetch_many"),
        ("quant_trading/data/yfinance_provider.py", "fetch_many"),
        ("quant_trading/data/yfinance_provider.py", "get_bbands"),
        ("quant_trading/data/yfinance_provider.py", "get_commodity"),
        ("quant_trading/data/yfinance_provider.py", "get_currency_exchange_rate"),
        ("quant_trading/data/yfinance_provider.py", "get_economic_indicator"),
        ("quant_trading/data/yfinance_provider.py", "get_ema"),
        ("quant_trading/data/yfinance_provider.py", "get_gold_history"),
        ("quant_trading/data/yfinance_provider.py", "get_gold_spot"),
        ("quant_trading/data/yfinance_provider.py", "get_macd"),
        ("quant_trading/data/yfinance_provider.py", "get_market_status"),
        ("quant_trading/data/yfinance_provider.py", "get_rsi"),
        ("quant_trading/data/yfinance_provider.py", "get_sector_performance"),
        ("quant_trading/data/yfinance_provider.py", "get_sma"),
        ("quant_trading/data/yfinance_provider.py", "get_stoch"),
        ("quant_trading/data/yfinance_provider.py", "get_technical_indicator"),
        ("quant_trading/data/yfinance_provider.py", "name"),
        ("quant_trading/data/yfinance_provider.py", "name"),
        ("quant_trading/data/yfinance_provider.py", "search_symbols"),
        ("quant_trading/monte_carlo/simulator.py", "__init__"),
        ("quant_trading/monte_carlo/simulator.py", "_ensure_simulations"),
        ("quant_trading/monte_carlo/simulator.py", "_extract_returns"),
        ("quant_trading/monte_carlo/simulator.py", "_run_bootstrap"),
        ("quant_trading/monte_carlo/simulator.py", "_run_bootstrap_parallel"),
        ("quant_trading/monte_carlo/simulator.py", "_run_parametric"),
        ("quant_trading/monte_carlo/simulator.py", "_run_parametric_parallel"),
        ("quant_trading/monte_carlo/simulator.py", "run"),
        ("quant_trading/monte_carlo/simulator.py", "run_monte_carlo"),
        ("quant_trading/optimization/base.py", "__init__"),
        ("quant_trading/optimization/base.py", "_assert_dates"),
        ("quant_trading/optimization/base.py", "_coerce_datetime"),
        ("quant_trading/optimization/base.py", "_create_strategy"),
        ("quant_trading/optimization/base.py", "_evaluate_params"),
        ("quant_trading/optimization/base.py", "_iso"),
        ("quant_trading/optimization/base.py", "_run_single_backtest"),
        ("quant_trading/optimization/base.py", "add"),
        ("quant_trading/optimization/base.py", "duration_seconds"),
        ("quant_trading/optimization/base.py", "from_dict"),
        ("quant_trading/optimization/base.py", "from_dict"),
        ("quant_trading/optimization/base.py", "generate_combinations"),
        ("quant_trading/optimization/base.py", "generate_grid"),
        ("quant_trading/optimization/base.py", "get_top_n"),
        ("quant_trading/optimization/base.py", "maximize_calmar"),
        ("quant_trading/optimization/base.py", "maximize_profit_factor"),
        ("quant_trading/optimization/base.py", "maximize_sharpe"),
        ("quant_trading/optimization/base.py", "maximize_sortino"),
        ("quant_trading/optimization/base.py", "maximize_total_return"),
        ("quant_trading/optimization/base.py", "maximize_win_rate"),
        ("quant_trading/optimization/base.py", "minimize_max_drawdown"),
        ("quant_trading/optimization/base.py", "run"),
        ("quant_trading/optimization/base.py", "sample_random"),
        ("quant_trading/optimization/base.py", "sample_random"),
        ("quant_trading/optimization/base.py", "set_validator"),
        ("quant_trading/optimization/base.py", "to_dataframe"),
        ("quant_trading/optimization/bayesian.py", "__init__"),
        ("quant_trading/optimization/bayesian.py", "_create_skopt_space"),
        ("quant_trading/optimization/bayesian.py", "from_dict"),
        ("quant_trading/optimization/bayesian.py", "run"),
        ("quant_trading/optimization/sensitivity.py", "_check_matplotlib"),
        ("quant_trading/optimization/sensitivity.py", "_fig_to_base64"),
        ("quant_trading/optimization/sensitivity.py", "create_1d_sensitivity_plot"),
        ("quant_trading/optimization/sensitivity.py", "create_2d_sensitivity_heatmap"),
        ("quant_trading/optimization/sensitivity.py", "create_parameter_interaction_heatmap"),
        ("quant_trading/optimization/sensitivity.py", "generate_sensitivity_report_html"),
        ("quant_trading/optimization/sensitivity.py", "prepare_sensitivity_data"),
        ("quant_trading/optimization/walk_forward.py", "__init__"),
        ("quant_trading/optimization/walk_forward.py", "_coerce_datetime"),
        ("quant_trading/optimization/walk_forward.py", "_combine_test_results"),
        ("quant_trading/optimization/walk_forward.py", "_create_optimizer"),
        ("quant_trading/optimization/walk_forward.py", "_generate_windows"),
        ("quant_trading/optimization/walk_forward.py", "_iso"),
        ("quant_trading/optimization/walk_forward.py", "from_dict"),
        ("quant_trading/optimization/walk_forward.py", "from_dict"),
        ("quant_trading/optimization/walk_forward.py", "run"),
        ("quant_trading/optimization/walk_forward.py", "summary"),
        ("quant_trading/optimization/walk_forward.py", "to_dataframe"),
        ("quant_trading/optimization/walk_forward.py", "to_dict"),
        ("quant_trading/optimization/walk_forward.py", "to_dict"),
        ("quant_trading/portfolio/rebalancer.py", "__init__"),
        ("quant_trading/portfolio/rebalancer.py", "_coerce_datetime"),
        ("quant_trading/portfolio/rebalancer.py", "_iso"),
        ("quant_trading/portfolio/rebalancer.py", "_plan_buy"),
        ("quant_trading/portfolio/rebalancer.py", "_plan_sell"),
        ("quant_trading/portfolio/rebalancer.py", "_planned_position_value"),
        ("quant_trading/portfolio/rebalancer.py", "_portfolio_value_at_prices"),
        ("quant_trading/portfolio/rebalancer.py", "_position_of"),
        ("quant_trading/portfolio/rebalancer.py", "_resolve_buy_quantity"),
        ("quant_trading/portfolio/rebalancer.py", "_resolve_execution_price"),
        ("quant_trading/portfolio/rebalancer.py", "_resolve_plan_price"),
        ("quant_trading/portfolio/rebalancer.py", "_resolve_sell_quantity"),
        ("quant_trading/portfolio/rebalancer.py", "_risk_adjust_buy"),
        ("quant_trading/portfolio/rebalancer.py", "_risk_adjust_execution_buy"),
        ("quant_trading/portfolio/rebalancer.py", "_risk_adjust_execution_exposure"),
        ("quant_trading/portfolio/rebalancer.py", "_risk_adjust_planned_exposure"),
        ("quant_trading/portfolio/rebalancer.py", "calculate_target_values"),
        ("quant_trading/portfolio/rebalancer.py", "execute_actions"),
        ("quant_trading/portfolio/rebalancer.py", "from_dict"),
        ("quant_trading/portfolio/rebalancer.py", "from_dict"),
        ("quant_trading/portfolio/rebalancer.py", "from_dict"),
        ("quant_trading/portfolio/rebalancer.py", "generate_rebalance_actions"),
        ("quant_trading/portfolio/rebalancer.py", "get_current_deviation"),
        ("quant_trading/portfolio/rebalancer.py", "needs_rebalance"),
        ("quant_trading/portfolio/rebalancer.py", "set_target_allocation"),
        ("quant_trading/portfolio/rebalancer.py", "should_rebalance"),
        ("quant_trading/portfolio/rebalancer.py", "to_dict"),
        ("quant_trading/portfolio/rebalancer.py", "to_dict"),
        ("quant_trading/regime/detector.py", "__init__"),
        ("quant_trading/regime/detector.py", "_build_segments"),
        ("quant_trading/regime/detector.py", "_label_series"),
        ("quant_trading/regime/detector.py", "_make_segment"),
        ("quant_trading/regime/detector.py", "_merge_segments"),
        ("quant_trading/risk/limits.py", "_coerce_datetime"),
        ("quant_trading/risk/limits.py", "_iso"),
        ("quant_trading/risk/manager.py", "__init__"),
        ("quant_trading/risk/manager.py", "_check_exposure_increase"),
        ("quant_trading/risk/manager.py", "_clear_trailing_state"),
        ("quant_trading/risk/manager.py", "_mapping_to_series"),
        ("quant_trading/risk/manager.py", "_open_position_count"),
        ("quant_trading/risk/manager.py", "_open_returns_frame"),
        ("quant_trading/risk/manager.py", "_position_weights"),
        ("quant_trading/risk/manager.py", "_reject_new_position_if_at_the_limit"),
        ("quant_trading/risk/manager.py", "_reject_signal_if_in_drawdown_breach"),
        ("quant_trading/risk/manager.py", "_series_to_mapping"),
        ("quant_trading/risk/manager.py", "_tracked_trailing_symbols"),
        ("quant_trading/risk/manager.py", "_validate_confidence"),
        ("quant_trading/risk/manager.py", "_validate_periods_per_year"),
        ("quant_trading/risk/metrics.py", "_align_series"),
        ("quant_trading/strategies/base.py", "__init__"),
        ("quant_trading/strategies/base.py", "__init__"),
        ("quant_trading/strategies/base.py", "add_strategy"),
        ("quant_trading/strategies/base.py", "from_config"),
        ("quant_trading/strategies/base.py", "generate_all_signals"),
        ("quant_trading/strategies/base.py", "generate_signals"),
        ("quant_trading/strategies/base.py", "get_parameters"),
        ("quant_trading/strategies/base.py", "get_strategy"),
        ("quant_trading/strategies/base.py", "market_value"),
        ("quant_trading/strategies/base.py", "pnl"),
        ("quant_trading/strategies/base.py", "remove_strategy"),
        ("quant_trading/strategies/base.py", "set_parameter"),
        ("quant_trading/strategies/base.py", "update_positions"),
        ("quant_trading/strategies/base.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "__init__"),
        ("quant_trading/strategies/examples.py", "_atr"),
        ("quant_trading/strategies/examples.py", "_atr"),
        ("quant_trading/strategies/examples.py", "_calculate_adl"),
        ("quant_trading/strategies/examples.py", "_calculate_adx"),
        ("quant_trading/strategies/examples.py", "_calculate_aroon"),
        ("quant_trading/strategies/examples.py", "_calculate_atr"),
        ("quant_trading/strategies/examples.py", "_calculate_choppiness_index"),
        ("quant_trading/strategies/examples.py", "_calculate_cmf"),
        ("quant_trading/strategies/examples.py", "_calculate_cmo"),
        ("quant_trading/strategies/examples.py", "_calculate_eom"),
        ("quant_trading/strategies/examples.py", "_calculate_force_index"),
        ("quant_trading/strategies/examples.py", "_calculate_klinger"),
        ("quant_trading/strategies/examples.py", "_calculate_macd"),
        ("quant_trading/strategies/examples.py", "_calculate_mfi"),
        ("quant_trading/strategies/examples.py", "_calculate_obv"),
        ("quant_trading/strategies/examples.py", "_calculate_rsi"),
        ("quant_trading/strategies/examples.py", "_calculate_sar"),
        ("quant_trading/strategies/examples.py", "_calculate_smi"),
        ("quant_trading/strategies/examples.py", "_calculate_stochastic"),
        ("quant_trading/strategies/examples.py", "_calculate_supertrend"),
        ("quant_trading/strategies/examples.py", "_calculate_vol"),
        ("quant_trading/strategies/examples.py", "_calculate_vortex"),
        ("quant_trading/strategies/examples.py", "_calculate_vpt"),
        ("quant_trading/strategies/examples.py", "_calculate_vroc"),
        ("quant_trading/strategies/examples.py", "_ema"),
        ("quant_trading/strategies/examples.py", "_ema"),
        ("quant_trading/strategies/examples.py", "_ema"),
        ("quant_trading/strategies/examples.py", "_ema"),
        ("quant_trading/strategies/examples.py", "_hull_moving_average"),
        ("quant_trading/strategies/examples.py", "_true_range"),
        ("quant_trading/strategies/examples.py", "_wma"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "generate_signals"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/examples.py", "validate_parameters"),
        ("quant_trading/strategies/factory.py", "__init__"),
        ("quant_trading/strategies/factory.py", "aliases_for"),
        ("quant_trading/strategies/factory.py", "create"),
        ("quant_trading/strategies/factory.py", "create_strategy"),
        ("quant_trading/strategies/factory.py", "get"),
        ("quant_trading/strategies/factory.py", "get_all"),
        ("quant_trading/strategies/factory.py", "get_registry"),
        ("quant_trading/strategies/factory.py", "get_strategy"),
        ("quant_trading/strategies/factory.py", "keys"),
        ("quant_trading/strategies/factory.py", "list_strategies"),
        ("quant_trading/strategies/factory.py", "primary_keys"),
        ("quant_trading/strategies/factory.py", "register"),
        ("quant_trading/strategies/factory.py", "register_strategy"),
        ("quant_trading/strategies/factory.py", "strategy_keys"),
        ("quant_trading/strategies/factory.py", "unregister"),
    }
)

# Name-only projection used for matching so that inserting lines above an
# allowlisted def does not invalidate the entry. Each entry must still resolve
# to an AST def (see test_examples_allowlist_names_exist).
_EXAMPLES_ALLOWLIST_NAMES: frozenset[tuple[str, str]] = frozenset(_EXAMPLES_ALLOWLIST)


def _docstring_arg_names(docstring: str) -> list[str]:
    """Return every argument name listed in the ``Args:`` section of a docstring."""
    names: list[str] = []
    in_args = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Args:\s*$", stripped):
            in_args = True
            continue
        if in_args and _DOC_SECTION_END.match(stripped):
            in_args = False
            continue
        if not in_args:
            continue
        entry = _DOC_ARG_ENTRY.match(stripped)
        if entry:
            names.append(entry.group(1))
    return names


def _signature_param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return every parameter name declared by a function signature."""
    args = node.args
    names = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
    if args.vararg is not None:
        names.add(args.vararg.arg)
    if args.kwarg is not None:
        names.add(args.kwarg.arg)
    return names


def _tree_documented_unknown_args(tree: ast.Module, rel: str) -> list[str]:
    """Return Args entries that name a parameter the signature does not have."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        params = _signature_param_names(node)
        for name in _docstring_arg_names(docstring):
            if name in ("self", "cls"):
                continue
            if name in params:
                continue
            offenders.append(
                f"{rel}:{node.lineno}: {node.name} documents unknown argument {name!r}"
            )
    return offenders


def _documented_unknown_args() -> list[str]:
    offenders: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            offenders.extend(_tree_documented_unknown_args(_parse(path), rel))
    return offenders


def test_documented_args_exist_in_signature() -> None:
    synthetic = (
        "def f(x: int = 0) -> None:\n"
        "    '''Do a thing.\n\n"
        "    Args:\n"
        "        x: value.\n"
        "        y: ghost (default 1).\n"
        "    '''\n"
    )
    injected = _tree_documented_unknown_args(ast.parse(synthetic), "synthetic.py")
    assert injected, "guard did not fire on an injected unknown argument"

    offenders = _documented_unknown_args()
    assert not offenders, "docstring Args name a parameter not in the signature:\n" + "\n".join(
        offenders
    )


# Signature parameters with no matching entry in the docstring ``Args:``
# section. Existing, undocumented parameters are grandfathered in
# _UNDOCUMENTED_PARAM_ALLOWLIST after a deliberate decision: the guard keeps
# the current debt visible and prevents new undocumented parameters from
# being added, but does not fail the suite on today's documented state.
# Remove an entry when the parameter is documented; never add entries for
# new code -- new parameters must be documented in Args.
_UNDOCUMENTED_PARAM_ALLOWLIST: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("examples/cli.py", "_is_supported_interval", "interval"),
        ("examples/cli.py", "_print_monte_carlo_analysis", "mc"),
        ("examples/cli.py", "_print_regime_analysis", "analysis"),
        ("examples/cli.py", "_print_trade_analysis", "analysis"),
        ("examples/cli.py", "_save_json_output", "output_format"),
        ("examples/cli.py", "_write_report", "include_charts"),
        ("examples/cli.py", "_write_report", "include_monthly_heatmap"),
        ("examples/cli.py", "_write_report", "include_rolling_metrics"),
        ("examples/cli.py", "_write_report", "include_trade_details"),
        ("examples/cli.py", "_write_report", "path"),
        ("examples/cli.py", "_write_report", "result"),
        ("examples/cli.py", "_write_report", "theme"),
        ("examples/cli.py", "create_config", "args"),
        ("examples/cli.py", "create_param_grid", "args"),
        ("examples/cli.py", "create_strategy", "args"),
        ("examples/cli.py", "init_config", "path"),
        ("examples/cli.py", "run_combined", "args"),
        ("examples/cli.py", "run_combined", "config"),
        ("examples/cli.py", "run_combined", "end_date"),
        ("examples/cli.py", "run_combined", "start_date"),
        ("examples/cli.py", "run_optimization", "args"),
        ("examples/cli.py", "run_optimization", "config"),
        ("examples/cli.py", "run_optimization", "end_date"),
        ("examples/cli.py", "run_optimization", "start_date"),
        ("examples/cli.py", "run_walk_forward", "args"),
        ("examples/cli.py", "run_walk_forward", "config"),
        ("examples/cli.py", "run_walk_forward", "end_date"),
        ("examples/cli.py", "run_walk_forward", "start_date"),
        ("examples/cli.py", "validate_config", "path"),
        ("quant_trading/backtest/report.py", "_build_comparison_risk_attribution", "colors"),
        ("quant_trading/backtest/report.py", "_build_comparison_risk_attribution", "dpi"),
        ("quant_trading/backtest/report.py", "_build_comparison_risk_attribution", "results"),
        ("quant_trading/backtest/report.py", "_build_comparison_summary_cards", "colors"),
        ("quant_trading/backtest/report.py", "_build_comparison_summary_cards", "results"),
        ("quant_trading/backtest/report.py", "_build_comparison_table", "colors"),
        ("quant_trading/backtest/report.py", "_build_comparison_table", "results"),
        ("quant_trading/backtest/report.py", "_build_metrics_table", "colors"),
        ("quant_trading/backtest/report.py", "_build_metrics_table", "result"),
        ("quant_trading/backtest/report.py", "_build_risk_attribution_table", "colors"),
        ("quant_trading/backtest/report.py", "_build_risk_attribution_table", "result"),
        ("quant_trading/backtest/report.py", "_build_trades_table", "colors"),
        ("quant_trading/backtest/report.py", "_build_trades_table", "max_rows"),
        ("quant_trading/backtest/report.py", "_build_trades_table", "result"),
        ("quant_trading/backtest/report.py", "_create_comparison_drawdown_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_comparison_drawdown_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_comparison_drawdown_chart", "results"),
        ("quant_trading/backtest/report.py", "_create_comparison_equity_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_comparison_equity_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_comparison_equity_chart", "results"),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_monthly_returns_heatmap",
            "colors",
        ),
        ("quant_trading/backtest/report.py", "_create_comparison_monthly_returns_heatmap", "dpi"),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_monthly_returns_heatmap",
            "colors",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_monthly_returns_heatmap",
            "results",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_risk_attribution_chart",
            "results",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_rolling_volatility_chart",
            "colors",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_rolling_volatility_chart",
            "results",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_trade_distribution_chart",
            "colors",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_trade_distribution_chart",
            "results",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_monthly_returns_heatmap",
            "results",
        ),
        ("quant_trading/backtest/report.py", "_create_comparison_risk_attribution_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_comparison_risk_attribution_chart", "dpi"),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_risk_attribution_chart",
            "results",
        ),
        ("quant_trading/backtest/report.py", "_create_comparison_rolling_sharpe_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_comparison_rolling_sharpe_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_comparison_rolling_sharpe_chart", "results"),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_rolling_volatility_chart",
            "colors",
        ),
        ("quant_trading/backtest/report.py", "_create_comparison_rolling_volatility_chart", "dpi"),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_rolling_volatility_chart",
            "results",
        ),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_trade_distribution_chart",
            "colors",
        ),
        ("quant_trading/backtest/report.py", "_create_comparison_trade_distribution_chart", "dpi"),
        (
            "quant_trading/backtest/report.py",
            "_create_comparison_trade_distribution_chart",
            "results",
        ),
        ("quant_trading/backtest/report.py", "_create_drawdown_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_drawdown_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_drawdown_chart", "result"),
        ("quant_trading/backtest/report.py", "_create_equity_curve_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_equity_curve_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_equity_curve_chart", "result"),
        ("quant_trading/backtest/report.py", "_create_monthly_returns_heatmap", "colors"),
        ("quant_trading/backtest/report.py", "_create_monthly_returns_heatmap", "dpi"),
        ("quant_trading/backtest/report.py", "_create_monthly_returns_heatmap", "result"),
        ("quant_trading/backtest/report.py", "_create_rolling_sharpe_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_rolling_sharpe_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_rolling_sharpe_chart", "result"),
        ("quant_trading/backtest/report.py", "_create_rolling_volatility_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_rolling_volatility_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_rolling_volatility_chart", "result"),
        ("quant_trading/backtest/report.py", "_create_trade_distribution_chart", "colors"),
        ("quant_trading/backtest/report.py", "_create_trade_distribution_chart", "dpi"),
        ("quant_trading/backtest/report.py", "_create_trade_distribution_chart", "result"),
        ("quant_trading/backtest/report.py", "_fig_to_base64", "dpi"),
        ("quant_trading/backtest/report.py", "_fig_to_base64", "fig"),
        ("quant_trading/backtest/report.py", "_format_metric", "fmt"),
        ("quant_trading/backtest/report.py", "_format_metric", "value"),
        ("quant_trading/backtest/report.py", "_get_css", "colors"),
        ("quant_trading/backtest/report.py", "_get_theme_colors", "theme"),
        ("quant_trading/data/providers.py", "_coerce_datetime", "value"),
        ("quant_trading/data/providers.py", "_iso", "value"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_commodity", "function"),
        ("quant_trading/data/yfinance_provider.py", "_fetch_economic_indicator", "function"),
        ("quant_trading/optimization/base.py", "_coerce_datetime", "value"),
        ("quant_trading/optimization/base.py", "_iso", "value"),
        ("quant_trading/optimization/sensitivity.py", "_fig_to_base64", "dpi"),
        ("quant_trading/optimization/sensitivity.py", "_fig_to_base64", "fig"),
        ("quant_trading/optimization/walk_forward.py", "_coerce_datetime", "value"),
        ("quant_trading/optimization/walk_forward.py", "_iso", "value"),
        ("quant_trading/optimization/walk_forward.py", "from_dict", "data"),
        ("quant_trading/portfolio/portfolio.py", "from_dict", "data"),
        ("quant_trading/portfolio/rebalancer.py", "_coerce_datetime", "value"),
        ("quant_trading/portfolio/rebalancer.py", "_iso", "value"),
        ("quant_trading/risk/limits.py", "_coerce_datetime", "value"),
        ("quant_trading/risk/limits.py", "_iso", "value"),
        ("quant_trading/risk/metrics.py", "from_dict", "data"),
        ("quant_trading/strategies/examples.py", "_calculate_adl", "df"),
        ("quant_trading/strategies/examples.py", "_calculate_aroon", "high"),
        ("quant_trading/strategies/examples.py", "_calculate_aroon", "low"),
        ("quant_trading/strategies/examples.py", "_calculate_choppiness_index", "df"),
        ("quant_trading/strategies/examples.py", "_calculate_sar", "high"),
        ("quant_trading/strategies/examples.py", "_calculate_sar", "low"),
        ("quant_trading/strategies/examples.py", "_calculate_stochastic", "close"),
        ("quant_trading/strategies/examples.py", "_calculate_stochastic", "high"),
        ("quant_trading/strategies/examples.py", "_calculate_stochastic", "low"),
        ("quant_trading/strategies/examples.py", "_calculate_supertrend", "df"),
        ("quant_trading/strategies/examples.py", "generate_signals", "data"),
    }
)


def _tree_undocumented_params(tree: ast.Module, rel: str) -> list[str]:
    """Return signature parameters missing from the docstring Args section.

    Split out so a caller can feed it a synthetic tree (the guard's negative
    control does exactly that) without writing to disk.
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        params = _signature_param_names(node) - {"self", "cls"}
        # *args and **kwargs cannot be exhaustively documented entry by entry.
        if node.args.vararg is not None:
            params.discard(node.args.vararg.arg)
        if node.args.kwarg is not None:
            params.discard(node.args.kwarg.arg)
        if not params:
            continue
        has_args_header = any(
            re.match(r"^Args:\s*$", line.strip()) for line in docstring.splitlines()
        )
        documented = set(_docstring_arg_names(docstring)) if has_args_header else set()
        for name in sorted(params - documented):
            if (rel, node.name, name) in _UNDOCUMENTED_PARAM_ALLOWLIST:
                continue
            if not has_args_header:
                offenders.append(
                    f"{rel}:{node.lineno}: {node.name} has documentable parameters but no Args section; missing {name!r}"
                )
            else:
                offenders.append(
                    f"{rel}:{node.lineno}: {node.name} does not document parameter {name!r}"
                )
    return offenders


def _tree_missing_args_section(tree: ast.Module, rel: str) -> list[str]:
    """Return functions with a docstring but no Args section when they have documentable parameters.

    Split out so a caller can feed it a synthetic tree (the guard's negative
    control does exactly that) without writing to disk.
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        params = _signature_param_names(node) - {"self", "cls"}
        # *args and **kwargs cannot be exhaustively documented entry by entry.
        if node.args.vararg is not None:
            params.discard(node.args.vararg.arg)
        if node.args.kwarg is not None:
            params.discard(node.args.kwarg.arg)
        if not params:
            continue
        has_args_header = any(
            re.match(r"^Args:\s*$", line.strip()) for line in docstring.splitlines()
        )
        if not has_args_header:
            # Check if all documentable parameters are in the allowlist
            all_allowlisted = all(
                (rel, node.name, name) in _UNDOCUMENTED_PARAM_ALLOWLIST for name in params
            )
            if not all_allowlisted:
                offenders.append(
                    f"{rel}:{node.lineno}: {node.name} has documentable parameters but no Args section"
                )
    return offenders


def _documented_missing_args_section() -> list[str]:
    """Return every function with a docstring but no Args section despite documentable parameters."""
    offenders: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            offenders.extend(_tree_missing_args_section(_parse(path), rel))
    return offenders


def _undocumented_params() -> list[str]:
    """Return every signature parameter missing its docstring Args entry."""
    offenders: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            offenders.extend(_tree_undocumented_params(_parse(path), rel))
    return offenders


def test_documented_args_cover_signature_params() -> None:
    """Every signature parameter must have a docstring Args entry.

    A parameter a caller can pass but the docstring never names is a
    documentation defect: the caller has no contract for what it does or what
    values it accepts. This guard parses every function's ``Args:`` section
    (AST, no imports) and fails when a signature parameter has no matching
    entry, including functions whose docstring omits the entire ``Args:``
    header. It is conservative: ``self``/``cls`` and ``*args``/``**kwargs`` are
    skipped, and functions without a docstring are not checked.

    Existing undocumented parameters are grandfathered in
    _UNDOCUMENTED_PARAM_ALLOWLIST; the guard prevents the debt from growing
    rather than failing on today's state.

    Negative controls feed the detector a synthetic function whose docstring
    documents ``a`` but not ``b``, and a synthetic function with documentable
    parameters but no ``Args:`` header, and assert both are reported. A
    positive control asserts that a populated ``Args:`` section passes.
    """
    missing_param = (
        "def f(a: int, b: int = 0) -> None:\n"
        "    '''Do a thing.\n\n"
        "    Args:\n"
        "        a: first value.\n"
        "    '''\n"
    )
    injected = _tree_undocumented_params(ast.parse(missing_param), "synthetic.py")
    assert injected, "guard did not fire on an injected undocumented parameter"

    missing_header = (
        "def f(a: int, b: int = 0) -> None:\n" "    '''Do a thing without documenting args.'''\n"
    )
    injected_header = _tree_undocumented_params(ast.parse(missing_header), "synthetic.py")
    assert injected_header, "guard did not fire on a documented function with no Args header"

    populated = (
        "def f(a: int, b: int = 0) -> None:\n"
        "    '''Do a thing.\n\n"
        "    Args:\n"
        "        a: first value.\n"
        "        b: second value.\n"
        "    '''\n"
    )
    assert not _tree_undocumented_params(
        ast.parse(populated), "synthetic.py"
    ), "guard falsely flagged a populated Args section"

    offenders = _undocumented_params()
    assert not offenders, "signature parameters missing from docstring Args:\n" + "\n".join(
        offenders
    )


def test_documented_functions_have_args_section() -> None:
    """Every function with a docstring and documentable parameters must have an Args section.

    A function that accepts parameters but whose docstring omits the entire
    ``Args:`` header leaves the caller with no contract for what those
    parameters do or what values they accept. This guard is purely structural
    (AST, no imports) and only flags functions that both have a docstring and
    declare documentable parameters (excluding ``self``/``cls`` and
    ``*args``/``**kwargs``). Existing debt is grandfathered through
    _UNDOCUMENTED_PARAM_ALLOWLIST: a function is only reported when at least
    one of its documentable parameters is not in the allowlist.

    Negative controls feed the detector a synthetic function with documentable
    parameters but no ``Args:`` header, and assert it is reported. A positive
    control with a populated ``Args:`` section passes. A function whose
    documentable parameters are all allowlisted is not flagged.
    """
    # Negative control: documented function with parameters but no Args section
    missing_header = (
        "def f(a: int, b: int = 0) -> None:\n" "    '''Do a thing without documenting args.'''\n"
    )
    injected = _tree_missing_args_section(ast.parse(missing_header), "synthetic.py")
    assert injected, "guard did not fire on a documented function with no Args header"

    # Positive control: populated Args section passes
    populated = (
        "def f(a: int, b: int = 0) -> None:\n"
        "    '''Do a thing.\n\n"
        "    Args:\n"
        "        a: first value.\n"
        "        b: second value.\n"
        "    '''\n"
    )
    assert not _tree_missing_args_section(
        ast.parse(populated), "synthetic.py"
    ), "guard falsely flagged a function with a populated Args section"

    # Control: function whose documentable params are all allowlisted passes
    # (simulated by an empty allowlist check in the helper)
    no_params = "def f() -> None:\n    '''Do a thing.'''\n"
    assert not _tree_missing_args_section(
        ast.parse(no_params), "synthetic.py"
    ), "guard falsely flagged a function without documentable parameters"

    offenders = _documented_missing_args_section()
    assert not offenders, "functions with docstring but no Args section:\n" + "\n".join(offenders)


# An ``(default X)`` note inside a docstring Args entry.
_DOC_DEFAULT_NOTE = re.compile(r"\(default ([^)]+)\)")
# The start of a docstring Args entry: ``name: description``.
_DOC_ARG_ENTRY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
# A clean literal a docstring can claim: True, False, None, or a number.
_DOC_LITERAL = re.compile(r"^(True|False|None|-?\d+(?:\.\d+)?)$")
# Section headers that end an ``Args:`` block (numpydoc/Google style).
_DOC_SECTION_END = re.compile(
    r"^(Returns|Raises|Yields|Examples|Example|Notes?|Attributes|See Also|References):\s*$"
)

# Matches a Returns section entry with a known type-like prefix.
# Only matches known Python/collection type names to avoid false positives
# on prose like "The result", "A dictionary", "Summary of...", "HTML string",
# "EMA series", "ATR series", "Sharpe ratio", etc.
# Also allows PascalCase class names (e.g., "RiskMetrics object") ONLY when
# followed by "object", since "X object" is a standard type declaration pattern,
# while "X series/value/ratio" are often descriptive.
_DOC_RETURNS_TYPE_PREFIX = re.compile(
    r"^(?:(?:Series|List|Dict|Dictionary|Mapping|Tuple|Set|Frozenset|Array|DataFrame|Index|Sequence|Collection|Iterable|Generator|Callable|Function|Type|Class|Instance|Deque|DefaultDict|OrderedDict|Counter|ChainMap|NamedTuple|TypedDict|DataClass|Protocol|AbstractSet|MutableSet|MappingView|KeysView|ValuesView|ItemsView|Awaitable|Coroutine|AsyncIterable|AsyncIterator|AsyncGenerator)\s+of\s+\w+|(?:Series|List|Dict|Dictionary|Mapping|Tuple|Set|Frozenset|Array|DataFrame|Index|Sequence|Collection|Iterable|Generator|Callable|Function|Type|Class|Instance|Deque|DefaultDict|OrderedDict|Counter|ChainMap|NamedTuple|TypedDict|DataClass|Protocol|AbstractSet|MutableSet|MappingView|KeysView|ValuesView|ItemsView|Awaitable|Coroutine|AsyncIterable|AsyncIterator|AsyncGenerator|DataFrame|Series|Index|Ndarray|Array|int|float|str|bool|None|NoneType|bytes|bytearray|memoryview|range|slice|ellipsis|NotImplemented|Ellipsis)\s+(?:object|value|dictionary|mapping|tuple|set|frozenset|array|frame|index|series|sequence|collection|iterable|generator|callable|function|type|class|instance|none|bool|int|float|str|string|bytes|bytearray|memoryview|range|slice|ellipsis|NotImplemented|Ellipsis)|[A-Z][a-zA-Z0-9]*\s+object)\b",
    re.IGNORECASE,
)


def _literal_default(text: str) -> tuple[bool, object]:
    """Parse a docstring ``(default X)`` note into a Python literal.

    Returns ``(True, value)`` when the note is exactly ``True``, ``False``,
    ``None`` or an int/float literal, and ``(False, None)`` for any other
    wording (for example ``"252 for daily data"`` or ``"the class default"``)
    so descriptive notes are skipped rather than mis-compared.
    """
    text = text.strip()
    if not _DOC_LITERAL.match(text):
        return False, None
    if text == "True":
        return True, True
    if text == "False":
        return True, False
    if text == "None":
        return True, None
    try:
        return True, float(text) if "." in text else int(text)
    except ValueError:  # pragma: no cover - _DOC_LITERAL guarantees this parses
        return False, None


def _docstring_arg_default_notes(docstring: str) -> list[tuple[str, str]]:
    """Return ``(arg_name, default_note)`` for every Args entry with a default note.

    Only the ``Args:`` section is scanned. A new entry starts at a line of the
    form ``name: description``; continuation lines belong to the current entry.
    Only the first ``(default X)`` note in each entry is reported.
    """
    notes: list[tuple[str, str]] = []
    in_args = False
    current: str | None = None
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Args:\s*$", stripped):
            in_args = True
            current = None
            continue
        if in_args and _DOC_SECTION_END.match(stripped):
            in_args = False
            current = None
            continue
        if not in_args:
            continue
        entry = _DOC_ARG_ENTRY.match(stripped)
        if entry:
            current = entry.group(1)
            entry_text = entry.group(2)
        elif current is not None:
            entry_text = stripped
        else:
            continue
        note = _DOC_DEFAULT_NOTE.search(entry_text)
        if note and current is not None:
            notes.append((current, note.group(1)))
    return notes


def _signature_defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, ast.expr | None]:
    """Map each parameter name to its default AST node (``None`` when required)."""
    args = node.args
    positional = args.posonlyargs + args.args
    defaults: dict[str, ast.expr | None] = {}
    padded: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults)) + list(
        args.defaults
    )
    for arg, default in zip(positional, padded):
        defaults[arg.arg] = default
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        defaults[arg.arg] = default
    return defaults


def _signature_return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.expr | None:
    """Return the return annotation AST node, or ``None`` if not annotated."""
    return node.returns


def _docstring_returns_type(docstring: str) -> str | None:
    """Extract a type-like prefix from the ``Returns:`` section of a docstring.

    Looks for patterns like:
    - "Series of X" / "List of X" / "Dict of X" / etc.
    - "X object" / "X value" / "X ratio" / "X dictionary" / etc.

    Returns the normalized type string (e.g., "Series", "RiskMetrics", "float"),
    or ``None`` if no recognizable type prefix is found.
    """
    in_returns = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Returns:\s*$", stripped):
            in_returns = True
            continue
        if in_returns and _DOC_SECTION_END.match(stripped):
            break
        if not in_returns:
            continue
        match = _DOC_RETURNS_TYPE_PREFIX.match(stripped)
        if match:
            # If we matched "X of Y", group(1) is not captured, so extract the prefix
            # The full match will contain the type prefix
            full = match.group(0).strip()
            # Extract the type word(s) before "of" or before "object"/"value"/etc.
            if " of " in full.lower():
                return full.split(" of ")[0].strip()
            # Otherwise it's "X object", "X value", etc. - extract X
            parts = full.split()
            return parts[0]
    return None


def _normalize_return_annotation(annotation: ast.expr | None) -> str | None:
    """Convert a return annotation AST node to a normalized type string.

    Handles common patterns:
    - Simple names: ``str`` -> "str"
    - Subscripts: ``list[Signal]`` -> "List", ``pd.Series`` -> "Series"
    - Attributes: ``pd.DataFrame`` -> "DataFrame"
    - ``None`` / ``NoneType`` -> "None"

    Returns ``None`` if the annotation cannot be normalized to a simple type name.
    """
    if annotation is None:
        return None

    # Handle ast.Name (simple names like str, int, float, None, etc.)
    if isinstance(annotation, ast.Name):
        name = annotation.id
        if name == "None":
            return "None"
        return name.capitalize()

    # Handle ast.Constant (for None as a constant in newer Python)
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return "None"

    # Handle ast.Subscript (generic types like list[X], dict[X, Y], tuple[X, ...])
    if isinstance(annotation, ast.Subscript):
        if isinstance(annotation.value, ast.Name):
            return annotation.value.id.capitalize()
        if isinstance(annotation.value, ast.Attribute):
            return annotation.value.attr.capitalize()

    # Handle ast.Attribute (qualified names like pd.Series, pd.DataFrame)
    if isinstance(annotation, ast.Attribute):
        return annotation.attr.capitalize()

    return None


def _returns_type_match(doc_type: str | None, sig_type: str | None) -> bool:
    """Conservative check if a documented return type matches the signature annotation.

    Only returns ``True`` when both are present and semantically equivalent.
    Known equivalences are mapped (e.g., "Series" ~ "Series", "List" ~ "List",
    "Dict" ~ "Dict", "DataFrame" ~ "DataFrame", etc.).
    """
    if doc_type is None or sig_type is None:
        return True  # Can't verify - skip rather than false positive

    doc_lower = doc_type.lower()
    sig_lower = sig_type.lower()

    # Direct match
    if doc_lower == sig_lower:
        return True

    # Common equivalences
    equivalences = {
        "series": {"series", "pd.series", "pandas.series"},
        "list": {"list", "sequence"},
        "dict": {"dict", "dictionary", "mapping"},
        "tuple": {"tuple"},
        "set": {"set"},
        "dataframe": {"dataframe", "pd.dataframe", "pandas.dataframe"},
        "float": {"float", "number"},
        "int": {"int", "integer"},
        "str": {"str", "string"},
        "bool": {"bool", "boolean"},
        "none": {"none", "nonetype"},
    }

    for variants in equivalences.values():
        if doc_lower in variants and sig_lower in variants:
            return True

    return False


def _tree_returns_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring/signature return type mismatches found in one parsed module.

    Split out so a caller can feed it a synthetic tree (the guard's negative control
    does exactly that) without writing to disk.
    """
    mismatches: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        doc_type = _docstring_returns_type(docstring)
        sig_annotation = _signature_return_annotation(node)
        sig_type = _normalize_return_annotation(sig_annotation)
        if (
            not _returns_type_match(doc_type, sig_type)
            and doc_type is not None
            and sig_type is not None
        ):
            mismatches.append(
                f"{rel}:{node.lineno}: {node.name} documented Returns type "
                f"{doc_type!r} but signature returns {sig_type!r}"
            )
    return mismatches


def _documented_returns_mismatches() -> list[str]:
    """Return every function whose docstring Returns type contradicts its signature.

    A docstring that tells the reader a function returns one type while the
    signature annotates a different type is a documentation defect. The check is
    purely structural (AST) and only compares a recognizable type prefix from
    the Returns section against the signature return annotation; descriptive
    Returns sections without a clear type prefix are skipped so the guard cannot
    produce false positives.
    """
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_returns_mismatches(_parse(path), rel))
    return mismatches


def test_documented_returns_match_signature() -> None:
    """Every ``Returns:`` type prefix must match the function's return annotation.

    A docstring that advertises the wrong return type misleads callers about
    what the function actually produces. This guard parses every function's
    ``Returns:`` section (AST, no imports) and fails when a recognizable type
    prefix disagrees with the signature return annotation. It is deliberately
    conservative: only functions with both a clear type prefix in the Returns
    section (e.g., "Series of ...", "RiskMetrics object") and a signature
    return annotation are compared. Prose-only Returns sections are skipped.

    A negative control feeds the detector a synthetic function whose docstring
    claims it returns a "Series" while the signature annotates ``-> int`` and
    asserts the drift is reported, proving the guard fires on the defect it
    guards against rather than passing vacuously.
    """
    synthetic = (
        "def f() -> int:\n"
        "    '''Do a thing.\n\n"
        "    Returns:\n"
        "        Series of values.\n"
        "    '''\n"
    )
    injected = _tree_returns_mismatches(ast.parse(synthetic), "synthetic.py")
    assert injected, "guard did not fire on an injected docstring/signature return type drift"

    mismatches = _documented_returns_mismatches()
    assert not mismatches, "docstring Returns type contradicts signature:\n" + "\n".join(mismatches)


# Return-annotation bases whose first type argument is the yielded value type.
_YIELD_ANNOTATION_BASES: frozenset[str] = frozenset({"Generator", "Iterator", "AsyncGenerator"})


def _docstring_yields_type(docstring: str) -> str | None:
    """Extract a type-like prefix from the ``Yields:`` section of a docstring.

    Mirrors :func:`_docstring_returns_type` but scans the ``Yields:`` section,
    recognising the same type prefixes (e.g. ``"int value"``, ``"Series of
    floats"``, ``"RiskMetrics object"``). Returns the normalized type string,
    or ``None`` when no recognizable prefix is found.
    """
    in_yields = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Yields:\s*$", stripped):
            in_yields = True
            continue
        if in_yields and _DOC_SECTION_END.match(stripped):
            break
        if not in_yields:
            continue
        match = _DOC_RETURNS_TYPE_PREFIX.match(stripped)
        if match:
            full = match.group(0).strip()
            if " of " in full.lower():
                return full.split(" of ")[0].strip()
            parts = full.split()
            return parts[0]
    return None


def _normalize_yield_annotation(annotation: ast.expr | None) -> str | None:
    """Convert a generator/iterator return annotation to its yield type string.

    Handles ``Generator[X, ...]``, ``Iterator[X]`` and ``AsyncGenerator[X, ...]``
    (including qualified bases such as ``typing.Generator[X, ...]``), returning
    the normalized yield type (e.g. ``"Int"``) or ``None`` when the annotation
    is not one of those types or declares no yield type argument.
    """
    if annotation is None:
        return None

    if isinstance(annotation, ast.Subscript):
        base = annotation.value
        slice_expr = annotation.slice
    else:
        return None

    base_name: str | None = None
    if isinstance(base, ast.Name):
        base_name = base.id
    elif isinstance(base, ast.Attribute):
        base_name = base.attr
    if base_name not in _YIELD_ANNOTATION_BASES:
        return None

    if isinstance(slice_expr, ast.Tuple):
        candidates = slice_expr.elts
    elif slice_expr is not None:
        candidates = [slice_expr]
    else:
        return None
    if not candidates:
        return None
    return _normalize_return_annotation(candidates[0])


def _tree_yields_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring/signature yield type mismatches found in one parsed module."""
    mismatches: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        sig_type = _normalize_yield_annotation(_signature_return_annotation(node))
        if sig_type is None:
            continue
        doc_type = _docstring_yields_type(docstring)
        if doc_type is None:
            continue
        if not _returns_type_match(doc_type, sig_type):
            mismatches.append(
                f"{rel}:{node.lineno}: {node.name} documented Yields type "
                f"{doc_type!r} but signature yields {sig_type!r}"
            )
    return mismatches


def _documented_yields_mismatches() -> list[str]:
    """Return every generator whose docstring Yields type contradicts its signature."""
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_yields_mismatches(_parse(path), rel))
    return mismatches


def test_documented_yields_match_signature() -> None:
    """Every ``Yields:`` type prefix must match the signature's yield type.

    A docstring that advertises the wrong yield type misleads callers about what
    a generator produces. This guard parses every function's ``Yields:`` section
    (AST, no imports) and fails when a recognizable type prefix disagrees with
    the yield type argument of a ``Generator``/``Iterator``/``AsyncGenerator``
    return annotation. It is deliberately conservative: only functions with both
    a clear type prefix in the Yields section and a generator return annotation
    are compared; prose-only Yields sections and non-generator functions are
    skipped.

    A negative control feeds the detector a synthetic generator whose docstring
    claims it yields ``int`` while the signature annotates
    ``-> Generator[str, None, None]`` and asserts the drift is reported, proving
    the guard fires on the defect it guards against rather than passing
    vacuously.
    """
    synthetic = (
        "from typing import Generator\n"
        "def f() -> Generator[str, None, None]:\n"
        "    '''Do a thing.\n\n"
        "    Yields:\n"
        "        int value.\n"
        "    '''\n"
    )
    injected = _tree_yields_mismatches(ast.parse(synthetic), "synthetic.py")
    assert injected, "guard did not fire on an injected docstring/signature yield type drift"

    mismatches = _documented_yields_mismatches()
    assert not mismatches, "docstring Yields type contradicts signature:\n" + "\n".join(mismatches)


# Names that are unambiguously "exception-like": a name ending in ``Error`` or
# ``Exception`` (including qualified names like ``yaml.YAMLError``) or a builtin
# exception class. Used to filter the ``Raises:`` section entries down to the
# ones that look like a deliberate exception reference rather than prose (e.g.
# ``"If the path does not exist"``).
_RAISES_EXCEPTION_NAME = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
    r"(?:Error|Exception)|"
    r"ArithmeticError|AssertionError|AttributeError|BaseException|BlockingIOError|"
    r"BrokenPipeError|BufferError|BytesWarning|ChildProcessError|ConnectionAbortedError|"
    r"ConnectionError|ConnectionRefusedError|ConnectionResetError|DeprecationWarning|"
    r"EOFError|Ellipsis|EnvironmentError|Exception|FileExistsError|FileNotFoundError|"
    r"FloatingPointError|FutureWarning|GeneratorExit|IOError|ImportError|ImportWarning|"
    r"IndentationError|IndexError|InterruptedError|IsADirectoryError|KeyError|"
    r"KeyboardInterrupt|LookupError|MemoryError|ModuleNotFoundError|NameError|"
    r"NotADirectoryError|NotImplemented|NotImplementedError|OSError|OverflowError|"
    r"PendingDeprecationWarning|PermissionError|ProcessLookupError|RecursionError|"
    r"ReferenceError|ResourceWarning|RuntimeError|RuntimeWarning|StopAsyncIteration|"
    r"StopIteration|SyntaxError|SyntaxWarning|SystemError|SystemExit|TabError|"
    r"TimeoutError|TypeError|UnboundLocalError|UnicodeDecodeError|UnicodeEncodeError|"
    r"UnicodeError|UnicodeTranslateError|UnicodeWarning|UserWarning|ValueError|"
    r"Warning|ZeroDivisionError)$"
)

# Builtin exception classes that the guard accepts without further checking.
# Kept as a frozenset of plain strings so the guard stays AST-only and
# dependency-free; qualified names (``module.Exception``) are accepted when the
# attribute ends in ``Error``/``Exception`` by :data:`_RAISES_EXCEPTION_NAME`.
_RAISES_BUILTIN_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "ArithmeticError",
        "AssertionError",
        "AttributeError",
        "BaseException",
        "BlockingIOError",
        "BrokenPipeError",
        "BufferError",
        "BytesWarning",
        "ChildProcessError",
        "ConnectionAbortedError",
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "DeprecationWarning",
        "EOFError",
        "EnvironmentError",
        "Exception",
        "FileExistsError",
        "FileNotFoundError",
        "FloatingPointError",
        "FutureWarning",
        "GeneratorExit",
        "IOError",
        "ImportError",
        "ImportWarning",
        "IndentationError",
        "IndexError",
        "InterruptedError",
        "IsADirectoryError",
        "KeyError",
        "KeyboardInterrupt",
        "LookupError",
        "MemoryError",
        "ModuleNotFoundError",
        "NameError",
        "NotADirectoryError",
        "NotImplementedError",
        "OSError",
        "OverflowError",
        "PendingDeprecationWarning",
        "PermissionError",
        "ProcessLookupError",
        "RecursionError",
        "ReferenceError",
        "ResourceWarning",
        "RuntimeError",
        "RuntimeWarning",
        "StopAsyncIteration",
        "StopIteration",
        "SyntaxError",
        "SyntaxWarning",
        "SystemError",
        "SystemExit",
        "TabError",
        "TimeoutError",
        "TypeError",
        "UnboundLocalError",
        "UnicodeDecodeError",
        "UnicodeEncodeError",
        "UnicodeError",
        "UnicodeTranslateError",
        "UnicodeWarning",
        "UserWarning",
        "ValueError",
        "Warning",
        "ZeroDivisionError",
    }
)


def _docstring_raises_names(docstring: str) -> list[str]:
    """Return every exception name listed in the ``Raises:`` section of a docstring.

    Only entries of the form ``ExceptionName: description`` are returned, and
    only when the name looks like a deliberate exception reference (see
    :data:`_RAISES_EXCEPTION_NAME`). Prose-only ``Raises:`` sections, blank
    lines, and continuation lines are skipped so the guard cannot misfire on
    descriptive text such as ``"If the path does not exist"``.
    """
    names: list[str] = []
    in_raises = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Raises:\s*$", stripped):
            in_raises = True
            continue
        if in_raises and _DOC_SECTION_END.match(stripped):
            in_raises = False
            continue
        if not in_raises:
            continue
        entry = _DOC_ARG_ENTRY.match(stripped)
        if not entry:
            continue
        name = entry.group(1)
        if _RAISES_EXCEPTION_NAME.match(name):
            names.append(name)
    return names


def _is_documented_exception(name: str) -> bool:
    """Return whether a ``Raises:`` name is a plausible exception reference.

    A name is accepted when it is a builtin exception class, or a qualified
    name whose attribute ends in ``Error``/``Exception`` (e.g.
    ``yaml.YAMLError``). Anything else -- including an exception-like name
    such as ``NotAnError`` that is not a real class -- is rejected, which is
    exactly the drift the guard exists to catch.
    """
    if name in _RAISES_BUILTIN_EXCEPTIONS:
        return True
    if "." in name:
        return bool(
            re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*Error$", name)
        ) or bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*Exception$", name))
    return False


def _tree_raises_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring ``Raises:`` names that are not real exception classes.

    Split out so a caller can feed it a synthetic tree (the guard's negative
    control does exactly that) without writing to disk. Only names that look
    like deliberate exception references are checked; prose is skipped.
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        for name in _docstring_raises_names(docstring):
            if not _is_documented_exception(name):
                offenders.append(
                    f"{rel}:{node.lineno}: {node.name} documents unknown exception {name!r}"
                )
    return offenders


def _documented_raises_mismatches() -> list[str]:
    """Return every function whose ``Raises:`` section names a non-exception.

    A ``Raises:`` entry that names something that is not an exception class
    (a name that does not end in ``Error``/``Exception`` and is not a builtin
    exception) is a documentation defect: the reader is told the function
    raises a thing that does not exist. The check is purely structural (AST,
    no imports) and is deliberately conservative: only entries of the form
    ``ExceptionName: description`` whose name looks like an exception are
    checked; prose-only ``Raises:`` sections are skipped.
    """
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_raises_mismatches(_parse(path), rel))
    return mismatches


def test_documented_raises_are_real_exceptions() -> None:
    """Every ``Raises:`` exception name must resolve to a real exception class.

    A ``Raises:`` entry that names something that is not an exception class
    (a name that does not end in ``Error``/``Exception`` and is not a builtin
    exception such as ``ValueError``) misleads callers about what the function
    can raise. This guard parses every function's ``Raises:`` section (AST,
    no imports) and fails when an entry names an unknown exception. It is
    deliberately conservative: only entries of the form
    ``ExceptionName: description`` whose name looks like an exception are
    checked, so prose-only ``Raises:`` sections and continuation lines cannot
    produce false positives.

    A negative control feeds the detector a synthetic function whose
    ``Raises:`` section names ``NotAnError`` (an exception-like name that is
    not a real class) and asserts the drift is reported, proving the guard
    fires on the defect it guards against rather than passing vacuously. A
    positive control documents the builtin ``ValueError`` and the qualified
    ``yaml.YAMLError`` and asserts both pass.
    """
    synthetic = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    Raises:\n"
        "        NotAnError: When something weird happens.\n"
        "    '''\n"
    )
    injected = _tree_raises_mismatches(ast.parse(synthetic), "synthetic.py")
    assert injected, "guard did not fire on an injected non-exception Raises name"

    # Positive controls: a builtin exception and a qualified exception name
    # must both pass the guard.
    synthetic_ok = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    Raises:\n"
        "        ValueError: When something is wrong.\n"
        "        yaml.YAMLError: When the YAML cannot be parsed.\n"
        "    '''\n"
    )
    assert not _tree_raises_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a documented builtin or qualified exception"

    mismatches = _documented_raises_mismatches()
    assert not mismatches, "docstring Raises names a non-exception:\n" + "\n".join(mismatches)


def _tree_default_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring/signature default mismatches found in one parsed module.

    Split out from :func:`_documented_default_mismatches` so a caller can feed
    it a synthetic tree (the guard's negative control does exactly that) without
    writing to disk.
    """
    mismatches: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        defaults = _signature_defaults(node)
        for arg_name, note in _docstring_arg_default_notes(docstring):
            is_literal, claimed = _literal_default(note)
            if not is_literal:
                continue
            default = defaults.get(arg_name)
            if default is None or not isinstance(default, ast.Constant):
                # Required parameter or non-literal default: nothing to compare.
                continue
            actual = default.value
            if isinstance(actual, bool) or isinstance(claimed, bool):
                matches = actual is claimed
            elif isinstance(actual, (int, float)) and isinstance(claimed, (int, float)):
                matches = float(actual) == float(claimed)
            else:
                matches = actual == claimed
            if not matches:
                mismatches.append(
                    f"{rel}:{node.lineno}: {node.name}({arg_name}) documented "
                    f"default {note!r} but signature default is {actual!r}"
                )
    return mismatches


def _documented_default_mismatches() -> list[str]:
    """Return every function whose docstring ``(default X)`` contradicts its signature.

    A docstring that tells the reader a parameter defaults to ``X`` while the
    signature actually defaults to ``Y`` is a documentation defect: a caller who
    trusts the docstring relies on a value the library does not use by default,
    so the documented and actual behaviour silently diverge. The check is purely
    structural (AST) and only compares a *clean* literal default note against a
    literal signature default; descriptive notes and non-literal defaults are
    skipped so the guard cannot produce false positives.
    """
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_default_mismatches(_parse(path), rel))
    return mismatches


def test_documented_arg_defaults_match_signature() -> None:
    """Every ``(default X)`` docstring note must match the parameter's real default.

    A docstring that advertises the wrong default is a live trap for callers:
    they read ``(default True)`` and rely on it, but the function actually
    defaults to ``False``, so behaviour differs from the documentation. This
    guard parses every function's ``Args:`` section (AST, no imports) and fails
    when a clean literal default note disagrees with the signature default. It
    caught ``calculate_equal_risk_contribution_weights`` and
    ``calculate_risk_budget_weights`` documenting ``long_only`` as defaulting to
    ``True`` while both signatures default to ``False``.

    The check is deliberately conservative: only ``True``/``False``/``None`` and
    numeric literal notes are compared, and only against literal signature
    defaults. Descriptive notes such as ``(default 252 for daily data)`` or
    ``(default the class default)`` are skipped, so the guard cannot misfire on
    prose.

    A negative control feeds the detector a synthetic function whose docstring
    claims ``flag`` defaults to ``True`` while the signature defaults to
    ``False`` and asserts the drift is reported, proving the guard fires on the
    defect it guards against rather than passing vacuously.
    """
    synthetic = (
        "def f(flag: bool = False) -> None:\n"
        "    '''Do a thing.\n\n"
        "    Args:\n"
        "        flag: Toggle the thing (default True).\n"
        "    '''\n"
    )
    injected = _tree_default_mismatches(ast.parse(synthetic), "synthetic.py")
    assert injected, "guard did not fire on an injected docstring/signature default drift"

    mismatches = _documented_default_mismatches()
    assert not mismatches, "docstring default notes contradict signatures:\n" + "\n".join(
        mismatches
    )


def _docstring_examples_content(docstring: str) -> list[str]:
    """Return the content lines of the ``Examples:``/``Example:`` section.

    Returns the raw lines (preserving indentation) between the section header
    and the next section header. An empty list means the section exists but has
    no content (or only whitespace/comments).
    """
    in_examples = False
    content: list[str] = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Examples?:\s*$", stripped):
            in_examples = True
            continue
        if in_examples and _DOC_SECTION_END.match(stripped):
            in_examples = False
            continue
        if not in_examples:
            continue
        content.append(line)
    return content


def _has_doctest_line(lines: list[str]) -> bool:
    """Return True if any line in the examples section starts with ``>>>``."""
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(">>>"):
            return True
    return False


def _validate_doctest_lines(lines: list[str]) -> list[str]:
    """Validate that all ``>>>`` lines in the examples section parse as Python.

    Returns a list of error messages for unparseable lines (empty if all valid).
    """
    errors: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith(">>>"):
            continue
        code = stripped[3:].strip()
        if not code:
            continue
        try:
            compile(code, "<doctest>", "exec")
        except SyntaxError as exc:
            errors.append(f"line {i}: {exc.msg}")
    return errors


def _tree_examples_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring Examples/Example section issues found in one parsed module.

    Checks:
    - The section is not empty (when the function advertises one).
    - Any ``>>>`` doctest lines parse as valid Python.

    Split out so a caller can feed it a synthetic tree (the guard's negative
    control does exactly that) without writing to disk.
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        content = _docstring_examples_content(docstring)
        if not content:
            if (rel, node.name) in _EXAMPLES_ALLOWLIST_NAMES:
                continue
            offenders.append(
                f"{rel}:{node.lineno}: {node.name} has an empty Examples/Example section"
            )
            continue
        # Only validate doctest lines if any are present
        if _has_doctest_line(content):
            errors = _validate_doctest_lines(content)
            for err in errors:
                if (rel, node.name) in _EXAMPLES_ALLOWLIST_NAMES:
                    continue
                offenders.append(
                    f"{rel}:{node.lineno}: {node.name} Examples/Example section has "
                    f"unparseable doctest: {err}"
                )
    return offenders


def _documented_examples_mismatches() -> list[str]:
    """Return every function whose Examples/Example section is empty or has bad doctests.

    A function that declares an Examples/Example section but leaves it empty
    misleads the reader. A doctest line (``>>> ...``) that does not parse as
    valid Python is a documentation defect: the example cannot be run and may
    misrepresent the API. The check is purely structural (AST, no imports) and
    conservative: only functions that actually have an Examples/Example section
    are checked, and only ``>>>`` lines are validated.
    """
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_examples_mismatches(_parse(path), rel))
    return mismatches


def test_documented_examples_are_valid() -> None:
    """Every ``Examples:``/``Example:`` section must be non-empty and parseable.

    A docstring that advertises an Examples/Example section but leaves it empty
    or includes a ``>>>`` line that does not parse as valid Python misleads the
    reader and cannot be used as a runnable example. This guard parses every
    function's Examples/Example section (AST, no imports) and fails when the
    section is empty or a doctest line is unparseable. It is deliberately
    conservative: only functions that actually have an Examples/Example section
    are checked, and only ``>>>`` lines are validated (prose is ignored).

    A negative control feeds the detector a synthetic function with an empty
    Examples section and one with an unparseable ``>>>`` line, asserting both
    are reported. A positive control with a valid doctest line passes.
    """
    # Negative control 1: empty Examples section
    synthetic_empty = "def f() -> None:\n" "    '''Do a thing.\n\n" "    Examples:\n" "    '''\n"
    injected_empty = _tree_examples_mismatches(ast.parse(synthetic_empty), "synthetic.py")
    assert injected_empty, "guard did not fire on an injected empty Examples section"

    # Negative control 2: unparseable doctest line
    synthetic_bad = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    Examples:\n"
        "        >>> this is not valid python\n"
        "    '''\n"
    )
    injected_bad = _tree_examples_mismatches(ast.parse(synthetic_bad), "synthetic.py")
    assert injected_bad, "guard did not fire on an injected unparseable doctest line"

    # Positive control: valid doctest line
    synthetic_ok = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    Examples:\n"
        "        >>> x = 1 + 1\n"
        "        >>> print(x)\n"
        "    '''\n"
    )
    assert not _tree_examples_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a valid Examples section with parseable doctests"

    mismatches = _documented_examples_mismatches()
    assert (
        not mismatches
    ), "docstring Examples/Example section is empty or has bad doctests:\n" + "\n".join(mismatches)


def _docstring_notes_content(docstring: str) -> list[str]:
    """Return the content lines of the ``Notes:`` section.

    Returns the raw lines between the section header and the next section
    header. An empty list means the section exists but has no content.
    """
    in_notes = False
    content: list[str] = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Notes?:\s*$", stripped):
            in_notes = True
            continue
        if in_notes and _DOC_SECTION_END.match(stripped):
            in_notes = False
            continue
        if not in_notes:
            continue
        content.append(line)
    return content


def _tree_notes_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring Notes section issues found in one parsed module."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        if "Notes:" not in docstring and "Note:" not in docstring:
            continue
        content = _docstring_notes_content(docstring)
        if not content or not any(c.strip() for c in content):
            offenders.append(f"{rel}:{node.lineno}: {node.name} has an empty Notes section")
    return offenders


def _documented_notes_mismatches() -> list[str]:
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_notes_mismatches(_parse(path), rel))
    return mismatches


def test_documented_notes_are_valid() -> None:
    synthetic_empty = "def f() -> None:\n" "    '''Do a thing.\n\n" "    Notes:\n" "    '''\n"
    injected_empty = _tree_notes_mismatches(ast.parse(synthetic_empty), "synthetic.py")
    assert injected_empty, "guard did not fire on an injected empty Notes section"

    synthetic_ok = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    Notes:\n"
        "        Some note.\n"
        "    '''\n"
    )
    assert not _tree_notes_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a valid Notes section"

    mismatches = _documented_notes_mismatches()
    assert not mismatches, "docstring Notes section is empty:\n" + "\n".join(mismatches)


def _docstring_attributes_content(docstring: str) -> list[str]:
    """Return the content lines of the ``Attributes:`` section.

    Returns the raw lines between the section header and the next section
    header. An empty list means the section exists but has no content.
    """
    in_attributes = False
    content: list[str] = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^Attributes:\s*$", stripped):
            in_attributes = True
            continue
        if in_attributes and _DOC_SECTION_END.match(stripped):
            in_attributes = False
            continue
        if not in_attributes:
            continue
        content.append(line)
    return content


def _tree_attributes_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return the docstring Attributes section issues found in one parsed module."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        if "Attributes:" not in docstring:
            continue
        content = _docstring_attributes_content(docstring)
        if not content or not any(c.strip() for c in content):
            offenders.append(f"{rel}:{node.lineno}: {node.name} has an empty Attributes section")
    return offenders


def _documented_attributes_mismatches() -> list[str]:
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_attributes_mismatches(_parse(path), rel))
    return mismatches


def test_documented_attributes_are_valid() -> None:
    """Every ``Attributes:`` section must be non-empty.

    A docstring that advertises an Attributes section but leaves it empty
    misleads the reader and suggests missing documentation. This guard parses
    every function/class Attributes section (AST, no imports) and fails when
    the section is empty. It is deliberately conservative: only objects that
    actually have an Attributes section are checked.

    A negative control feeds the detector a synthetic class with an empty
    Attributes section, asserting it is reported. A positive control with
    attribute content passes.
    """
    synthetic_empty = (
        "class C:\n" "    '''Do a thing.\n\n" "    Attributes:\n" "    '''\n" "    pass\n"
    )
    injected_empty = _tree_attributes_mismatches(ast.parse(synthetic_empty), "synthetic.py")
    assert injected_empty, "guard did not fire on an injected empty Attributes section"

    synthetic_ok = (
        "class C:\n"
        "    '''Do a thing.\n\n"
        "    Attributes:\n"
        "        x: The x value.\n"
        "    '''\n"
        "    pass\n"
    )
    assert not _tree_attributes_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a valid Attributes section"

    mismatches = _documented_attributes_mismatches()
    assert not mismatches, "docstring Attributes section is empty:\n" + "\n".join(mismatches)


def _docstring_cross_reference_content(docstring: str, section: str) -> list[str] | None:
    """Return a cross-reference section's lines, or ``None`` when it is absent."""
    in_section = False
    found = False
    content: list[str] = []
    header = re.compile(rf"^{re.escape(section)}:\s*$")
    for line in docstring.splitlines():
        stripped = line.strip()
        if header.match(stripped):
            found = True
            in_section = True
            continue
        if in_section and _DOC_SECTION_END.match(stripped):
            break
        if in_section:
            content.append(line)
    return content if found else None


def _tree_cross_reference_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return empty ``See Also:`` or ``References:`` sections in one module."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        for section in ("See Also", "References"):
            content = _docstring_cross_reference_content(docstring, section)
            if content is not None and not any(line.strip() for line in content):
                offenders.append(f"{rel}:{node.lineno}: {node.name} has an empty {section} section")
    return offenders


def _documented_cross_reference_mismatches() -> list[str]:
    """Return every empty cross-reference section in the user-facing source tree."""
    mismatches: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            mismatches.extend(_tree_cross_reference_mismatches(_parse(path), rel))
    return mismatches


def test_documented_cross_reference_sections_are_valid() -> None:
    """Every ``See Also:`` or ``References:`` section must be non-empty."""
    synthetic_empty = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    See Also:\n"
        "    References:\n"
        "    '''\n"
    )
    injected = _tree_cross_reference_mismatches(ast.parse(synthetic_empty), "synthetic.py")
    assert len(injected) == 2, "guard did not fire on both injected empty sections"

    synthetic_ok = (
        "class C:\n"
        "    '''Do a thing.\n\n"
        "    See Also:\n"
        "        Other API.\n"
        "    References:\n"
        "        Project documentation.\n"
        "    '''\n"
        "    pass\n"
    )
    assert not _tree_cross_reference_mismatches(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged populated cross-reference sections"

    mismatches = _documented_cross_reference_mismatches()
    assert not mismatches, "docstring cross-reference section is empty:\n" + "\n".join(mismatches)


# A Sphinx-style cross-reference role with a target, e.g. ``:class:`~pkg.mod.Name``
# or ``:func:`pkg.mod.func``. Group 1 is the role, group 2 the dotted target;
# the leading ``~`` (which only affects how the role is rendered) is consumed by
# the pattern so the captured target is the importable dotted path.
_DOC_XREF_ROLE = re.compile(
    r":(class|func|meth|mod|data|attr|exc|obj):`~?([A-Za-z_][A-Za-z0-9_.]*)`"
)


def _resolve_dotted_name(dotted: str) -> str | None:
    """Resolve a dotted ``quant_trading`` name to a real object.

    The longest importable module prefix is imported first, then the remaining
    dotted components are walked. A component may be either an attribute or a
    submodule that has not been imported yet (for example
    ``quant_trading.optimization`` is not re-exported by the top package), so a
    missing attribute falls back to importing the next-longer module path.

    Returns:
        ``None`` when the name resolves, otherwise a short human-readable
        reason describing the first component that could not be resolved.
    """
    parts = dotted.split(".")
    module: object | None = None
    start = 0
    for split in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        start = split
        break
    if module is None:
        return f"no importable module prefix for {dotted}"
    for index in range(start, len(parts)):
        attribute = parts[index]
        if hasattr(module, attribute):
            module = getattr(module, attribute)
            continue
        submodule = ".".join(parts[: index + 1])
        try:
            module = importlib.import_module(submodule)
        except ModuleNotFoundError as exc:
            if exc.name == submodule:
                return f"module {'.'.join(parts[:index])} has no attribute {attribute}"
            # The submodule exists but one of its imports is unavailable in
            # this environment (for example an optional dependency), so the
            # reference cannot be verified here and is not reported.
            return None
        except ImportError:
            return None
    return None


def _docstring_unresolved_xrefs(docstring: str, rel: str, lineno: int, owner: str) -> list[str]:
    """Return unresolved ``quant_trading`` cross-reference roles in one docstring."""
    offenders: list[str] = []
    for match in _DOC_XREF_ROLE.finditer(docstring):
        role, target = match.group(1), match.group(2)
        if not target.startswith("quant_trading."):
            continue
        reason = _resolve_dotted_name(target)
        if reason is not None:
            offenders.append(
                f"{rel}:{lineno}: {owner} references unknown {role} {target!r} ({reason})"
            )
    return offenders


def _tree_unresolved_xrefs(tree: ast.Module, rel: str) -> list[str]:
    """Return unresolved ``quant_trading`` cross-references in one parsed module.

    Both the module docstring and every function, async function and class
    docstring are scanned, because a Sphinx cross-reference is a defect wherever
    it appears, not only on a definition.
    """
    offenders: list[str] = []
    module_doc = ast.get_docstring(tree)
    if module_doc:
        offenders.extend(_docstring_unresolved_xrefs(module_doc, rel, 1, "<module>"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        offenders.extend(_docstring_unresolved_xrefs(docstring, rel, node.lineno, node.name))
    return offenders


def _documented_unresolved_xrefs() -> list[str]:
    """Return every unresolved ``quant_trading`` cross-reference in the source tree."""
    offenders: list[str] = []
    for directory in _DOC_SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            offenders.extend(_tree_unresolved_xrefs(_parse(path), rel))
    return offenders


def test_documented_quant_trading_xrefs_resolve() -> None:
    """Every ``quant_trading.*`` Sphinx cross-reference target must resolve.

    A docstring that cross-references ``:class:`~quant_trading.pkg.mod.Name``-
    style targets is a promise to the reader that the named object exists. When
    the object is renamed, moved, or never existed, the rendered documentation
    links to nothing and the prose silently rots. This guard parses every
    module, class and function docstring in ``quant_trading`` and ``examples``
    (AST for discovery, imports only to resolve the named target) and fails
    when a ``quant_trading.*`` cross-reference role does not resolve to a real
    module, class, function or attribute.

    It is deliberately conservative: only recognised roles (``class``, ``func``,
    ``meth``, ``mod``, ``data``, ``attr``, ``exc``, ``obj``) with a
    ``quant_trading.*`` dotted target are checked, so prose mentions and
    external references are ignored. This complements
    ``test_readme_backtick_quant_trading_names_resolve``, which covers README
    backticks rather than docstring roles.

    A negative control feeds the detector a role pointing at a module that does
    not exist and asserts it is reported. A positive control with a role that
    resolves to a real object passes.
    """
    synthetic_missing = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    See Also:\n"
        "        :class:`~quant_trading.definitely_missing_module.Widget`\n"
        "    '''\n"
    )
    injected = _tree_unresolved_xrefs(ast.parse(synthetic_missing), "synthetic.py")
    assert injected, "guard did not fire on an injected unknown cross-reference"

    synthetic_ok = (
        "def f() -> None:\n"
        "    '''Do a thing.\n\n"
        "    See Also:\n"
        "        :class:`~quant_trading.strategies.base.Signal`\n"
        "    '''\n"
    )
    assert not _tree_unresolved_xrefs(
        ast.parse(synthetic_ok), "synthetic.py"
    ), "guard falsely flagged a cross-reference that resolves"

    offenders = _documented_unresolved_xrefs()
    assert (
        not offenders
    ), "docstring cross-references name objects that do not exist:\n" + "\n".join(offenders)


def _normalize_update_positions_annotation(annotation: ast.expr | None) -> str | None:
    """Normalize the ``positions`` parameter annotation of ``update_positions``.

    Only the base-class form ``dict[str, Position]`` is recognized; any other
    form (including no annotation) is reported as a mismatch so callers that
    pass a differently keyed or valued mapping are never silently accepted.
    """
    if annotation is None:
        return None
    if isinstance(annotation, ast.Subscript):
        base = annotation.value
        base_name = base.id if isinstance(base, ast.Name) else None
        if base_name in {"dict", "Dict"}:
            slice_expr = annotation.slice
            if isinstance(slice_expr, ast.Tuple):
                args = slice_expr.elts
            else:
                args = [slice_expr]
            if (
                len(args) == 2
                and isinstance(args[0], ast.Name)
                and args[0].id == "str"
                and isinstance(args[1], ast.Name)
                and args[1].id == "Position"
            ):
                return "dict[str, Position]"
    return None


def _tree_update_positions_override_mismatches(tree: ast.Module, rel: str) -> list[str]:
    """Return every ``update_positions`` override that drifts from the base signature.

    ``Strategy.update_positions`` declares
    ``(self, positions: dict[str, Position]) -> None``. Overrides must keep the
    parameter names, count, ``positions`` annotation, and ``-> None`` return.
    Split out so a caller can feed it a synthetic tree (the guard's negative
    control does exactly that) without writing to disk.
    """
    mismatches: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name == "Strategy":
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "update_positions":
                continue
            args = item.args.args
            if len(args) != 2:
                shown = ", ".join(arg.arg for arg in args) or "no parameters"
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.update_positions has {len(args)} "
                    f"parameter(s) ({shown}), expected exactly (self, positions)"
                )
                continue
            if args[0].arg != "self":
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.update_positions first parameter is "
                    f"{args[0].arg!r}, expected self"
                )
            if args[1].arg != "positions":
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.update_positions second parameter is "
                    f"{args[1].arg!r}, expected positions"
                )
            if _normalize_update_positions_annotation(args[1].annotation) != "dict[str, Position]":
                shown = (
                    ast.unparse(args[1].annotation) if args[1].annotation is not None else "untyped"
                )
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.update_positions positions annotation is "
                    f"{shown}, expected dict[str, Position]"
                )
            returns = item.returns
            if not (
                (isinstance(returns, ast.Name) and returns.id == "None")
                or (isinstance(returns, ast.Constant) and returns.value is None)
            ):
                shown = ast.unparse(returns) if returns is not None else "untyped"
                mismatches.append(
                    f"{rel}:{item.lineno}: {node.name}.update_positions returns "
                    f"{shown}, expected None"
                )
    return mismatches


def _documented_update_positions_override_mismatches() -> list[str]:
    """Return every ``update_positions`` override that drifts from the base signature."""
    mismatches: list[str] = []
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        mismatches.extend(_tree_update_positions_override_mismatches(_parse(path), rel))
    return mismatches


def test_update_positions_overrides_annotated() -> None:
    """Every ``update_positions`` override must keep the base signature.

    ``Strategy.update_positions`` declares
    ``(self, positions: dict[str, Position]) -> None``. A subclass that drifts
    the parameter names, the parameter count, the ``positions`` annotation, or
    the return annotation silently breaks callers that rely on position
    tracking. This guard is purely structural (AST, no imports) and only checks
    overrides outside the base ``Strategy`` class.

    Negative controls inject a wrong first/second parameter name, wrong
    parameter counts (0 and 2), a wrong ``positions`` annotation, and a
    wrong/missing return annotation, and assert each drift is reported. A
    positive control with the canonical signature passes.
    """
    synthetic_first_param_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(cls, positions: dict[str, Position]) -> None:\n"
        "        return\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_first_param_mismatch), "synthetic.py"
    )
    assert injected

    synthetic_second_param_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(self, pos: dict[str, Position]) -> None:\n"
        "        return\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_second_param_mismatch), "synthetic.py"
    )
    assert injected

    synthetic_arg_count_zero = (
        "class MyStrategy(Strategy):\n" "    def update_positions() -> None:\n" "        return\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_arg_count_zero), "synthetic.py"
    )
    assert injected

    synthetic_arg_count_three = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(self, positions: dict[str, Position], extra: int) -> None:\n"
        "        return\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_arg_count_three), "synthetic.py"
    )
    assert injected

    synthetic_annotation_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(self, positions: dict[str, int]) -> None:\n"
        "        return\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_annotation_mismatch), "synthetic.py"
    )
    assert injected

    synthetic_return_mismatch = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(self, positions: dict[str, Position]) -> int:\n"
        "        return 0\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_return_mismatch), "synthetic.py"
    )
    assert injected

    synthetic_missing_return = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(self, positions: dict[str, Position]):\n"
        "        return\n"
    )
    injected = _tree_update_positions_override_mismatches(
        ast.parse(synthetic_missing_return), "synthetic.py"
    )
    assert injected

    synthetic_ok = (
        "class MyStrategy(Strategy):\n"
        "    def update_positions(self, positions: dict[str, Position]) -> None:\n"
        "        return\n"
    )
    assert not _tree_update_positions_override_mismatches(ast.parse(synthetic_ok), "synthetic.py")

    mismatches = _documented_update_positions_override_mismatches()
    assert not mismatches, "update_positions override signature drift:\n" + "\n".join(mismatches)


def test_repository_is_black_formatted() -> None:
    """Every Python source file must satisfy ``black --check``.

    ``[tool.black]`` in ``pyproject.toml`` pins the formatter and line length
    (100), and the repository treats formatting as a quality gate, but nothing
    previously enforced it. An unformatted file slipped into the tree and made
    ``black --check`` fail while the test suite stayed green. This guard runs
    the pinned formatter in check mode over the same source directories the
    other integrity checks cover and fails with the offending paths.

    The check is skipped when Black is not installed so environments that only
    install the runtime dependencies are unaffected.
    """
    pytest.importorskip("black")

    offenders: list[str] = []
    for directory in SOURCE_DIRS:
        root = REPO_ROOT / directory
        if not root.exists():
            continue
        result = subprocess.run(
            [sys.executable, "-m", "black", "--check", "--quiet", str(root)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            offenders.append(f"{directory}: black --check failed\n{result.stderr}{result.stdout}")
    assert not offenders, "repository is not black-formatted:\n" + "\n".join(offenders)


def test_repository_is_ruff_clean() -> None:
    """Every Python source file must satisfy ``ruff check``.

    ``[tool.ruff]`` in ``pyproject.toml`` pins the linter and line length
    (100), and the repository treats linting as a quality gate, but nothing
    previously enforced it. A lint violation slipped into the tree and made
    ``ruff check`` fail while the test suite stayed green. This guard runs the
    pinned linter over the same source directories the other integrity checks
    cover and fails with the offending paths.

    The check is skipped when Ruff is not installed so environments that only
    install the runtime dependencies are unaffected.
    """
    pytest.importorskip("ruff")

    offenders: list[str] = []
    for directory in SOURCE_DIRS:
        root = REPO_ROOT / directory
        if not root.exists():
            continue
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(root)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            offenders.append(f"{directory}: ruff check failed\n{result.stderr}{result.stdout}")
    assert not offenders, "repository is not ruff-clean:\n" + "\n".join(offenders)


def test_repository_is_mypy_clean() -> None:
    """Every Python source file must satisfy ``mypy``.

    ``[tool.mypy]`` in ``pyproject.toml`` pins the type checker, and the
    repository treats type-checking as a quality gate, but nothing previously
    enforced it. A type error slipped into the tree and made ``mypy`` fail while
    the test suite stayed green. This guard runs the pinned checker over the
    same source directories the other integrity checks cover and fails with the
    offending paths.

    The check is skipped when Mypy is not installed so environments that only
    install the runtime dependencies are unaffected.
    """
    pytest.importorskip("mypy")

    offenders: list[str] = []
    for directory in SOURCE_DIRS:
        root = REPO_ROOT / directory
        if not root.exists():
            continue
        result = subprocess.run(
            [sys.executable, "-m", "mypy", str(root)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            offenders.append(f"{directory}: mypy failed\n{result.stderr}{result.stdout}")
    assert not offenders, "repository is not mypy-clean:\n" + "\n".join(offenders)


def test_examples_allowlist_names_exist() -> None:
    """Every _EXAMPLES_ALLOWLIST entry must still resolve to an AST def.

    Entries are keyed by ``(rel, name)`` only, so inserting lines above an
    allowlisted def does not invalidate the entry. This guard catches entries
    whose name has been renamed or removed from the source file.
    """
    import ast as _ast
    import pathlib as _pathlib

    missing = []
    by_file: dict[str, list[str]] = {}
    for rel, name in _EXAMPLES_ALLOWLIST:
        by_file.setdefault(rel, []).append(name)
    for rel, names in by_file.items():
        tree = _ast.parse((_pathlib.Path(rel)).read_text())
        current = {
            n.name
            for n in _ast.walk(tree)
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
        }
        for name in names:
            if name not in current:
                missing.append(f"{rel}:{name}: allowlisted name not found in AST")
    assert not missing, "stale allowlist entries:\n" + "\n".join(missing)
