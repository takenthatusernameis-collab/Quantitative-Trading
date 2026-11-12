"""Tests for SuperTrendStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import SuperTrendStrategy


def _valid_st():
    return SuperTrendStrategy(period=10, multiplier=3.0)


def test_validate_period_must_be_positive():
    s = _valid_st()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_multiplier_must_be_positive():
    s = _valid_st()
    s.multiplier = 0
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()


def test_validate_multiplier_non_finite_rejected():
    s = _valid_st()
    s.multiplier = float("nan")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()

    s = _valid_st()
    s.multiplier = float("inf")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()

    s = _valid_st()
    s.multiplier = float("-inf")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="multiplier must be positive"):
        SuperTrendStrategy(period=10, multiplier=float("nan"))

    with pytest.raises(ValueError, match="multiplier must be positive"):
        SuperTrendStrategy(period=10, multiplier=float("inf"))

    with pytest.raises(ValueError, match="multiplier must be positive"):
        SuperTrendStrategy(period=10, multiplier=-1.0)

    # Valid construction should succeed
    s = SuperTrendStrategy(period=10, multiplier=3.0)
    assert s.period == 10
    assert s.multiplier == 3.0


def test_validate_accepts_valid_values():
    s = _valid_st()
    s.validate_parameters()  # Should not raise

    s = SuperTrendStrategy(period=14, multiplier=2.5)
    s.validate_parameters()  # Should not raise

    s = SuperTrendStrategy(period=20, multiplier=4.0)
    s.validate_parameters()  # Should not raise