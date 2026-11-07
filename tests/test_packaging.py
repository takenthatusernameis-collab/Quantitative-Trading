"""Packaging and distribution metadata tests."""

from pathlib import Path

import quant_trading

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
