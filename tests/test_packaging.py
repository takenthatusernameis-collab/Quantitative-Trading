"""Packaging and distribution metadata tests."""

import importlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import tomllib

import quant_trading

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

ROOT = Path(__file__).resolve().parent.parent


class TestTypingMarker:
    """PEP 561: package must ship typing information."""

    def test_py_typed_file_exists_in_package(self) -> None:
        pkg_dir = Path(quant_trading.__file__).resolve().parent
        marker = pkg_dir / "py.typed"
        assert marker.exists(), f"Missing PEP 561 marker: {marker}"

    def test_py_typed_configured_in_package_data(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "py.typed" in pyproject
        assert "package-data" in pyproject

    def test_typing_typed_classifier_present(self) -> None:
        """PEP 561 recommends the Typing :: Typed trove classifier."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert '"Typing :: Typed"' in pyproject


class TestPackageVersion:
    """Version metadata should stay consistent across package and build config."""

    def test_package_version_matches_pyproject(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert quant_trading.__version__ == pyproject["project"]["version"]

    def test_package_version_is_semver_like(self) -> None:
        """Version should follow a simple MAJOR.MINOR.PATCH numeric form."""
        import re

        assert re.fullmatch(
            r"\d+\.\d+\.\d+", quant_trading.__version__
        ), f"Expected MAJOR.MINOR.PATCH version, got: {quant_trading.__version__!r}"


class TestConsoleScript:
    """The documented ``quant-trading`` console script must resolve to the CLI.

    ``[project.scripts]`` is how users launch the tool after
    ``pip install quant-trading``; a renamed ``main`` or a typo in the target
    would only surface at install time. Resolve the declared target here so a
    drift fails fast in the test suite instead.
    """

    def test_console_script_target_is_declared(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = pyproject["project"]["scripts"]
        assert scripts.get("quant-trading"), "missing quant-trading entry point"

    def test_console_script_target_resolves_to_callable(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        module_path, _, attribute = pyproject["project"]["scripts"]["quant-trading"].partition(":")
        assert module_path and attribute, "entry point must be '<module>:<attr>'"
        entry = getattr(importlib.import_module(module_path), attribute)
        assert callable(entry)


class TestPackageExports:
    """Public API surface declared in __all__ must resolve to attributes."""

    def test_all_exports_resolve(self) -> None:
        import quant_trading

        for name in quant_trading.__all__:
            assert hasattr(quant_trading, name), f"Missing public export: {name}"
            assert getattr(quant_trading, name) is not None, f"Null public export: {name}"

    def test_factory_exports_roundtrip(self) -> None:
        """Factory functions exported at package root should behave as documented."""
        strategies = quant_trading.list_strategies()
        assert isinstance(strategies, dict)
        assert "ma" in strategies

        strategy = quant_trading.create_strategy("ma", fast_period=5, slow_period=20)
        assert isinstance(strategy, quant_trading.BaseStrategy)
        assert strategy.parameters["fast_period"] == 5
        assert strategy.parameters["slow_period"] == 20


class TestWheelContents:
    """The built wheel must ship everything the console script needs.

    Automates the handoff confirmation that the wheel (not the editable
    install) contains ``examples/`` (the entry point depends on it) and
    ``quant_trading/py.typed``, and that the CLI runs from outside the
    source tree. Marked slow because it builds a wheel via ``pip``.
    """

    @pytest.mark.slow
    def test_built_wheel_ships_cli_and_typing_marker(self, tmp_path: Path) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        name = pyproject["project"]["name"].replace("-", "_")
        version = pyproject["project"]["version"]
        wheel_name = f"{name}-{version}-py3-none-any.whl"

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                ".",
                "--no-deps",
                "--no-build-isolation",
                "-w",
                str(tmp_path),
            ],
            check=True,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )

        wheel_path = tmp_path / wheel_name
        assert wheel_path.exists(), f"Wheel not produced: {wheel_path}"

        with zipfile.ZipFile(wheel_path) as wheel:
            names = set(wheel.namelist())
            assert f"{name}/py.typed" in names, "wheel missing quant_trading/py.typed"
            assert "examples/__init__.py" in names, "wheel missing examples package"
            assert "examples/cli.py" in names, "wheel missing examples/cli.py"
            entry_points = wheel.read(f"{name}-{version}.dist-info/entry_points.txt").decode(
                "utf-8"
            )
            assert "quant-trading = examples.cli:main" in entry_points
