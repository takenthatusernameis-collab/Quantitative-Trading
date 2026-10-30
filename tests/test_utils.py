"""Tests for utility helpers."""

import logging

from quant_trading.utils import (
    format_basis_points,
    format_currency,
    format_number,
    format_percent,
    get_logger,
    setup_logger,
)


def test_format_currency():
    assert format_currency(1234.5) == "$1,234.50"
    assert format_currency(0.0) == "$0.00"
    assert format_currency(-500.0, decimals=0) == "-$500"


def test_format_currency_custom_symbol():
    assert format_currency(1234.5, currency="€") == "€1,234.50"


def test_format_percent():
    assert format_percent(0.05) == "5.00%"
    assert format_percent(0.123456, decimals=2) == "12.35%"
    assert format_percent(1.0) == "100.00%"


def test_format_number():
    assert format_number(1234567.89) == "1,234,568"
    assert format_number(1234.5, decimals=2) == "1,234.50"


def test_format_basis_points():
    assert format_basis_points(100) == "1.0%"
    assert format_basis_points(25, decimals=2) == "0.25%"
    assert format_basis_points(150) == "1.5%"


def test_setup_logger_console_only(tmp_path):
    name = "_test_utils_console_logger"
    logger = setup_logger(name=name, level="WARNING")
    try:
        assert logger.level == logging.WARNING
        assert len(logger.handlers) == 1
    finally:
        logging.getLogger(name).handlers.clear()


def test_setup_logger_with_file(tmp_path):
    name = "_test_utils_file_logger"
    log_file = str(tmp_path / "logs" / "test.log")
    logger = setup_logger(name=name, level="DEBUG", log_file=log_file)
    try:
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 2
        logger.info("hello world")
        with open(log_file) as f:
            assert "hello world" in f.read()
    finally:
        logging.getLogger(name).handlers.clear()


def test_setup_logger_idempotent(tmp_path):
    name = "_test_utils_idempotent_logger"
    log_file = str(tmp_path / "test.log")
    logger = setup_logger(name=name, level="DEBUG", log_file=log_file)
    handler_count = len(logger.handlers)
    logger2 = setup_logger(name=name, level="INFO")
    try:
        assert logger2 is logger
        assert len(logger.handlers) == handler_count
    finally:
        logging.getLogger(name).handlers.clear()


def test_get_logger_creates_or_returns_existing():
    """get_logger exercises both the no-handler and existing-handler arms (logging.py:44)."""
    name = "_test_utils_get_logger_both"
    logging.getLogger(name).handlers.clear()
    fresh = get_logger(name)  # no handlers -> setup_logger invoked
    try:
        assert fresh.name == name
        assert len(fresh.handlers) >= 1
        again = get_logger(name)  # handlers present -> returns existing logger
        assert again is fresh
    finally:
        logging.getLogger(name).handlers.clear()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
