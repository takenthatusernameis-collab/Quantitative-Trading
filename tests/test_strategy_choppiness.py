"""Tests for ChoppinessIndexStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import ChoppinessIndexStrategy


def _valid_chop():
    return ChoppinessIndexStrategy(period=14, low_threshold=38.2, high_threshold=61.8)


def test_validate_period_must_be_positive():
    s = _valid_chop()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_low_threshold_non_finite_rejected():
    s = _valid_chop()
    s.low_threshold = float("nan")
    with pytest.raises(ValueError, match="low_threshold must be non-negative"):
        s.validate_parameters()

    s = _valid_chop()
    s.low_threshold = float("inf")
    with pytest.raises(ValueError, match="low_threshold must be non-negative"):
        s.validate_parameters()

    s = _valid_chop()
    s.low_threshold = float("-inf")
    with pytest.raises(ValueError, match="low_threshold must be non-negative"):
        s.validate_parameters()


def test_validate_high_threshold_non_finite_rejected():
    s = _valid_chop()
    s.high_threshold = float("nan")
    with pytest.raises(ValueError, match="high_threshold must be at most 100"):
        s.validate_parameters()

    s = _valid_chop()
    s.high_threshold = float("inf")
    with pytest.raises(ValueError, match="high_threshold must be at most 100"):
        s.validate_parameters()

    s = _valid_chop()
    s.high_threshold = float("-inf")
    with pytest.raises(ValueError, match="high_threshold must be at most 100"):
        s.validate_parameters()


def test_validate_low_threshold_negative_rejected():
    s = _valid_chop()
    s.low_threshold = -1
    with pytest.raises(ValueError, match="low_threshold must be non-negative"):
        s.validate_parameters()


def test_validate_high_threshold_above_100_rejected():
    s = _valid_chop()
    s.high_threshold = 101
    with pytest.raises(ValueError, match="high_threshold must be at most 100"):
        s.validate_parameters()


def test_validate_low_threshold_must_be_less_than_high():
    s = _valid_chop()
    s.low_threshold = 70
    s.high_threshold = 61.8
    with pytest.raises(ValueError, match="low_threshold must be less than high_threshold"):
        s.validate_parameters()


def test_validate_accepts_valid_values():
    s = _valid_chop()
    s.validate_parameters()  # Should not raise

    s = ChoppinessIndexStrategy(period=14, low_threshold=0, high_threshold=100)
    s.validate_parameters()  # Should not raise

    s = ChoppinessIndexStrategy(period=14, low_threshold=0, high_threshold=1)
    s.validate_parameters()  # Should not raise


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="low_threshold must be non-negative"):
        ChoppinessIndexStrategy(period=14, low_threshold=float("nan"), high_threshold=61.8)

    with pytest.raises(ValueError, match="high_threshold must be at most 100"):
        ChoppinessIndexStrategy(period=14, low_threshold=38.2, high_threshold=float("nan"))

    with pytest.raises(ValueError, match="low_threshold must be non-negative"):
        ChoppinessIndexStrategy(period=14, low_threshold=-1, high_threshold=61.8)

    with pytest.raises(ValueError, match="high_threshold must be at most 100"):
        ChoppinessIndexStrategy(period=14, low_threshold=38.2, high_threshold=101)

    with pytest.raises(ValueError, match="low_threshold must be less than high_threshold"):
        ChoppinessIndexStrategy(period=14, low_threshold=70, high_threshold=61.8)

    # Valid construction should succeed
    s = ChoppinessIndexStrategy(period=14, low_threshold=38.2, high_threshold=61.8)
    assert s.period == 14
    assert s.low_threshold == 38.2
    assert s.high_threshold == 61.8
