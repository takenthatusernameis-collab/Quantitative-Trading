"""Tests for BollingerPercentBStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import BollingerPercentBStrategy


def _valid_pb():
    return BollingerPercentBStrategy(period=20, std_dev=2.0, oversold=0.2, overbought=0.8)


def test_validate_period_must_be_positive():
    s = _valid_pb()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_std_dev_must_be_positive():
    s = _valid_pb()
    s.std_dev = 0
    with pytest.raises(ValueError, match="std_dev must be positive"):
        s.validate_parameters()


def test_validate_oversold_must_be_in_range_and_below_overbought():
    s = _valid_pb()
    s.oversold = -0.1
    with pytest.raises(
        ValueError, match="oversold must be in \\[0, 1\\) and below overbought in \\(0, 1\\]"
    ):
        s.validate_parameters()


def test_validate_overbought_must_be_in_range_and_above_oversold():
    s = _valid_pb()
    s.overbought = 1.5
    with pytest.raises(
        ValueError, match="oversold must be in \\[0, 1\\) and below overbought in \\(0, 1\\]"
    ):
        s.validate_parameters()


def test_validate_oversold_must_be_less_than_overbought():
    s = _valid_pb()
    s.oversold = 0.8
    s.overbought = 0.2
    with pytest.raises(
        ValueError, match="oversold must be in \\[0, 1\\) and below overbought in \\(0, 1\\]"
    ):
        s.validate_parameters()
