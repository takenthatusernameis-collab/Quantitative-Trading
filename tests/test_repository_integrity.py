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
            returns = node.returns
            if not ((isinstance(returns, ast.Name) and returns.id == "None") or (isinstance(returns, ast.Constant) and returns.value is None)):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "validate_parameters without -> None:\n" + "\n".join(offenders)
