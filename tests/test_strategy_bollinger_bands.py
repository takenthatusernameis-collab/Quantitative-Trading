"""Tests for BollingerBandsStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import BollingerBandsStrategy


def _valid_bb():
    return BollingerBandsStrategy(period=20, std_dev=2.0)


def test_validate_period_must_be_positive():
    s = _valid_bb()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_std_dev_must_be_positive():
    s = _valid_bb()
    s.std_dev = 0
    with pytest.raises(ValueError, match="std_dev must be positive"):
        s.validate_parameters()


def test_validate_std_dev_non_finite_rejected():
    s = _valid_bb()
    s.std_dev = float("nan")
    with pytest.raises(ValueError, match="std_dev must be positive"):
        s.validate_parameters()

    s = _valid_bb()
    s.std_dev = float("inf")
    with pytest.raises(ValueError, match="std_dev must be positive"):
        s.validate_parameters()

    s = _valid_bb()
    s.std_dev = float("-inf")
    with pytest.raises(ValueError, match="std_dev must be positive"):
        s.validate_parameters()


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="std_dev must be positive"):
        BollingerBandsStrategy(period=20, std_dev=float("nan"))

    with pytest.raises(ValueError, match="std_dev must be positive"):
        BollingerBandsStrategy(period=20, std_dev=float("inf"))

    with pytest.raises(ValueError, match="std_dev must be positive"):
        BollingerBandsStrategy(period=20, std_dev=-1.0)

    # Valid construction should succeed
    s = BollingerBandsStrategy(period=20, std_dev=2.0)
    assert s.period == 20
    assert s.std_dev == 2.0


def test_validate_accepts_valid_values():
    s = _valid_bb()
    s.validate_parameters()  # Should not raise

    s = BollingerBandsStrategy(period=20, std_dev=1.5)
    s.validate_parameters()  # Should not raise

    s = BollingerBandsStrategy(period=50, std_dev=3.0)
    s.validate_parameters()  # Should not raise