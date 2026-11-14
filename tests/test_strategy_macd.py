"""Tests for MACDStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import MACDStrategy


def _valid_macd() -> MACDStrategy:
    return MACDStrategy(fast_period=12, slow_period=26, signal_period=9)


def test_validate_fast_period_must_be_positive() -> None:
    s = _valid_macd()
    s.fast_period = 0
    with pytest.raises(ValueError, match="fast_period must be positive"):
        s.validate_parameters()


def test_validate_slow_period_must_be_positive() -> None:
    s = _valid_macd()
    s.slow_period = 0
    with pytest.raises(ValueError, match="slow_period must be positive"):
        s.validate_parameters()


def test_validate_signal_period_must_be_positive() -> None:
    s = _valid_macd()
    s.signal_period = 0
    with pytest.raises(ValueError, match="signal_period must be positive"):
        s.validate_parameters()


def test_validate_fast_period_must_be_less_than_slow_period() -> None:
    s = _valid_macd()
    s.fast_period = 30
    s.slow_period = 26
    with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
        s.validate_parameters()
