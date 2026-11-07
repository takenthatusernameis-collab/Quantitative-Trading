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
