"""Tests for RSIStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import RSIStrategy


def _valid_rsi():
    return RSIStrategy(period=14, oversold=30, overbought=70)


def test_validate_period_must_be_positive():
    s = _valid_rsi()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_oversold_must_be_between_0_and_100():
    s = _valid_rsi()
    s.oversold = 0
    with pytest.raises(ValueError, match="oversold must be between 0 and 100"):
        s.validate_parameters()


def test_validate_overbought_must_be_between_0_and_100():
    s = _valid_rsi()
    s.overbought = 100
    with pytest.raises(ValueError, match="overbought must be between 0 and 100"):
        s.validate_parameters()


def test_validate_oversold_must_be_less_than_overbought():
    s = _valid_rsi()
    s.oversold = 70
    s.overbought = 30
    with pytest.raises(ValueError, match="oversold must be less than overbought"):
        s.validate_parameters()
