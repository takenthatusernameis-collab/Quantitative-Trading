"""Tests for MomentumStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import MomentumStrategy


def _valid_mom():
    return MomentumStrategy(period=10, threshold=0.0)


def test_validate_period_must_be_positive():
    s = _valid_mom()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_threshold_must_be_non_negative():
    s = _valid_mom()
    s.threshold = -1.0
    with pytest.raises(ValueError, match="threshold must be non-negative"):
        s.validate_parameters()


def test_validate_threshold_non_finite_rejected():
    s = _valid_mom()
    s.threshold = float("nan")
    with pytest.raises(ValueError, match="threshold must be non-negative"):
        s.validate_parameters()

    s = _valid_mom()
    s.threshold = float("inf")
    with pytest.raises(ValueError, match="threshold must be non-negative"):
        s.validate_parameters()

    s = _valid_mom()
    s.threshold = float("-inf")
    with pytest.raises(ValueError, match="threshold must be non-negative"):
        s.validate_parameters()


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="threshold must be non-negative"):
        MomentumStrategy(period=10, threshold=float("nan"))

    with pytest.raises(ValueError, match="threshold must be non-negative"):
        MomentumStrategy(period=10, threshold=float("inf"))

    with pytest.raises(ValueError, match="threshold must be non-negative"):
        MomentumStrategy(period=10, threshold=-1.0)

    # Valid construction should succeed
    s = MomentumStrategy(period=10, threshold=0.0)
    assert s.period == 10
    assert s.threshold == 0.0


def test_validate_accepts_valid_values():
    s = _valid_mom()
    s.validate_parameters()  # Should not raise

    s = MomentumStrategy(period=10, threshold=0.5)
    s.validate_parameters()  # Should not raise

    s = MomentumStrategy(period=20, threshold=0.0)
    s.validate_parameters()  # Should not raise
