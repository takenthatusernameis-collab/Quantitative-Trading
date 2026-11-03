"""Tests for utility helpers."""

import logging

from quant_trading.utils import (
    clear_loggers,
    format_basis_points,
    format_currency,
    format_duration_days,
    format_number,
    format_percent,
    format_shares,
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


def test_format_shares():
    assert format_shares(100) == "100"
    assert format_shares(10.5) == "10.5"
    assert format_shares(100, decimals=2) == "100.00"
    assert format_shares(100, decimals=0) == "100"
    assert format_shares(10.5, decimals=2) == "10.50"
    assert format_shares(-100) == "-100"
    assert format_shares(-10.5) == "-10.5"


def test_format_duration_days():
    assert format_duration_days(3) == "3 days"
    assert format_duration_days(1) == "1 day"
    assert format_duration_days(7) == "1 week"
    assert format_duration_days(14) == "2 weeks"
    assert format_duration_days(15) == "2.1 weeks"
    assert format_duration_days(30) == "1 month"
    assert format_duration_days(30.44) == "1 month"
    assert format_duration_days(59) == "1.9 months"
    assert format_duration_days(60.88) == "2 months"
    assert format_duration_days(365) == "1 year"
    assert format_duration_days(365.25) == "1 year"
    assert format_duration_days(730.5) == "2 years"
    assert format_duration_days(800) == "2.2 years"
    assert format_duration_days(0) == "0 days"
    assert format_duration_days(-3) == "-3 days"


def test_format_currency_negative_and_zero_decimals():
    assert format_currency(-1234.5) == "-$1,234.50"
    assert format_currency(1234.5, decimals=0) == "$1,234"


def test_format_percent_negative_and_zero_decimals():
    assert format_percent(-0.05) == "-5.00%"
    assert format_percent(0.5, decimals=0) == "50%"


def test_format_number_negative_and_zero_decimals():
    assert format_number(-1234.5) == "-1,234"
    assert format_number(1234.5, decimals=0) == "1,234"


def test_format_basis_points_negative_zero_and_zero_decimals():
    assert format_basis_points(-100) == "-1.0%"
    assert format_basis_points(0) == "0.0%"
    assert format_basis_points(100, decimals=0) == "1%"


def test_format_shares_whole_with_decimals_and_negative():
    assert format_shares(100, decimals=2) == "100.00"
    assert format_shares(-100, decimals=2) == "-100.00"


def test_format_duration_days_fractional_and_negative_fractional():
    assert format_duration_days(2.5) == "2.5 days"
    assert format_duration_days(-2.5) == "-2.5 days"


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


def test_format_shares_fractional_and_edge_cases():
    assert format_shares(10.5, decimals=0) == "10.5"
    assert format_shares(1000.25, decimals=0) == "1000.25"
    assert format_shares(0) == "0"
    assert format_shares(0, decimals=2) == "0.00"
    assert format_shares(-10.5, decimals=0) == "-10.5"


def test_format_duration_days_weeks_months_years_edge_cases():
    assert format_duration_days(2) == "2 days"
    assert format_duration_days(2.5) == "2.5 days"
    assert format_duration_days(14) == "2 weeks"
    assert format_duration_days(10.5) == "1.5 weeks"
    assert format_duration_days(60) == "2.0 months"
    assert format_duration_days(90) == "3.0 months"
    assert format_duration_days(730) == "2.0 years"
    assert format_duration_days(-7) == "-1 week"
    assert format_duration_days(365.25) == "1 year"


def test_clear_loggers_named_and_root():
    name = "_test_utils_clear_loggers"
    logger = setup_logger(name=name, level="INFO")
    assert len(logger.handlers) >= 1
    clear_loggers(name)
    assert len(logging.getLogger(name).handlers) == 0

    root = logging.getLogger()
    root.addHandler(logging.StreamHandler())
    try:
        assert len(root.handlers) >= 1
        clear_loggers()
        assert len(root.handlers) == 0
    finally:
        root.handlers.clear()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
