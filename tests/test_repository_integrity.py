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


def test_all_package_all_exports_resolve():
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


def test_package_reexports_are_listed_in_defining_module_all():
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
            except Exception:  # noqa: BLE001, S112 - an unimportable module is reported by the test above
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
    return ast.literal_eval(_cli_arg_defaults_node(tree))


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
                    return ast.literal_eval(stmt.value)
    raise AssertionError("strategy_param_map not found in create_strategy")


def test_cli_arg_defaults_match_strategy_init_defaults():
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
        signature = inspect.signature(cls.__init__)
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
                dest = keyword.value.value
            elif keyword.arg == "action" and isinstance(keyword.value, ast.Constant):
                action_name = keyword.value.value
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


def test_cli_arg_defaults_entries_are_used_by_a_flag():
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
    used_keys = {spec["default_key"] for spec in flag_defaults.values()}

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
        key = spec["default_key"]
        if not isinstance(key, str):
            continue
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
            if isinstance(default_value, bool) or not isinstance(
                default_value, (int, float)
            ):
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


def test_cli_arg_defaults_type_matches_default():
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
        "force_index",
        "hma",
        "klinger",
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
    }
)


def test_registered_strategies_have_documented_cli_coverage():
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
        tunables = set(_tunable_init_params(strategy_cls))
        mapped = {param_name for _, param_name in pairs}
        unmapped = sorted(tunables - mapped)
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


def test_readme_quant_trading_imports_exist():
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


def test_readme_code_block_language_tags_are_supported():
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


def test_readme_backtick_quant_trading_names_resolve():
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
