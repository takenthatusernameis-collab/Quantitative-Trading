"""Packaging and distribution metadata tests."""

from pathlib import Path

import quant_trading

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

ROOT = Path(__file__).resolve().parent.parent


class TestTypingMarker:
    """PEP 561: package must ship typing information."""

    def test_py_typed_file_exists_in_package(self):
        pkg_dir = Path(quant_trading.__file__).resolve().parent
        marker = pkg_dir / "py.typed"
        assert marker.exists(), f"Missing PEP 561 marker: {marker}"

    def test_py_typed_configured_in_package_data(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "py.typed" in pyproject
        assert "package-data" in pyproject

    def test_typing_typed_classifier_present(self):
        """PEP 561 recommends the Typing :: Typed trove classifier."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert '"Typing :: Typed"' in pyproject


class TestPackageVersion:
    """Version metadata should stay consistent across package and build config."""

    def test_package_version_matches_pyproject(self):
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert quant_trading.__version__ == pyproject["project"]["version"]

    def test_package_version_is_semver_like(self):
        """Version should follow a simple MAJOR.MINOR.PATCH numeric form."""
        import re

        assert re.fullmatch(r"\d+\.\d+\.\d+", quant_trading.__version__), (
            f"Expected MAJOR.MINOR.PATCH version, got: {quant_trading.__version__!r}"
        )


class TestPackageExports:
    """Public API surface declared in __all__ must resolve to attributes."""

    def test_all_exports_resolve(self):
        import quant_trading

        for name in quant_trading.__all__:
            assert hasattr(quant_trading, name), f"Missing public export: {name}"
            assert getattr(quant_trading, name) is not None, f"Null public export: {name}"

    def test_factory_exports_roundtrip(self):
        """Factory functions exported at package root should behave as documented."""
        strategies = quant_trading.list_strategies()
        assert isinstance(strategies, dict)
        assert "ma" in strategies

        strategy = quant_trading.create_strategy("ma", fast_period=5, slow_period=20)
        assert isinstance(strategy, quant_trading.BaseStrategy)
        assert strategy.parameters["fast_period"] == 5
        assert strategy.parameters["slow_period"] == 20
