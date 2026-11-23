"""Tests for AverageTrueRangeStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import AverageTrueRangeStrategy


def _valid_atr() -> AverageTrueRangeStrategy:
    return AverageTrueRangeStrategy(period=14, atr_multiplier=2.0)


def test_validate_period_must_be_positive() -> None:
    s = _valid_atr()
    s.period = 0
    with pytest.raises(ValueError, match="invalid period: the value must be positive"):
        s.validate_parameters()


def test_validate_atr_multiplier_must_be_positive() -> None:
    s = _valid_atr()
    s.atr_multiplier = 0
    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        s.validate_parameters()


def test_validate_atr_multiplier_non_finite_rejected() -> None:
    s = _valid_atr()
    s.atr_multiplier = float("nan")
    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        s.validate_parameters()

    s = _valid_atr()
    s.atr_multiplier = float("inf")
    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        s.validate_parameters()

    s = _valid_atr()
    s.atr_multiplier = float("-inf")
    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        s.validate_parameters()


def test_constructor_calls_validate() -> None:
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        AverageTrueRangeStrategy(period=14, atr_multiplier=float("nan"))

    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        AverageTrueRangeStrategy(period=14, atr_multiplier=float("inf"))

    with pytest.raises(ValueError, match="invalid atr_multiplier: the value must be positive"):
        AverageTrueRangeStrategy(period=14, atr_multiplier=-1.0)

    # Valid construction should succeed
    s = AverageTrueRangeStrategy(period=14, atr_multiplier=2.0)
    assert s.period == 14
    assert s.atr_multiplier == 2.0


def test_validate_accepts_valid_values() -> None:
    s = _valid_atr()
    s.validate_parameters()  # Should not raise

    s = AverageTrueRangeStrategy(period=14, atr_multiplier=1.5)
    s.validate_parameters()  # Should not raise

    s = AverageTrueRangeStrategy(period=20, atr_multiplier=3.0)
    s.validate_parameters()  # Should not raise
