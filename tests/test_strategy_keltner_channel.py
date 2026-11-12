"""Tests for KeltnerChannelStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import KeltnerChannelStrategy


def _valid_kc():
    return KeltnerChannelStrategy(ema_period=20, atr_period=10, multiplier=2.0)


def test_validate_ema_period_must_be_positive():
    s = _valid_kc()
    s.ema_period = 0
    with pytest.raises(ValueError, match="ema_period must be positive"):
        s.validate_parameters()


def test_validate_atr_period_must_be_positive():
    s = _valid_kc()
    s.atr_period = 0
    with pytest.raises(ValueError, match="atr_period must be positive"):
        s.validate_parameters()


def test_validate_multiplier_must_be_positive():
    s = _valid_kc()
    s.multiplier = 0
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()


def test_validate_multiplier_non_finite_rejected():
    s = _valid_kc()
    s.multiplier = float("nan")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()

    s = _valid_kc()
    s.multiplier = float("inf")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()

    s = _valid_kc()
    s.multiplier = float("-inf")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        s.validate_parameters()


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="multiplier must be positive"):
        KeltnerChannelStrategy(ema_period=20, atr_period=10, multiplier=float("nan"))

    with pytest.raises(ValueError, match="multiplier must be positive"):
        KeltnerChannelStrategy(ema_period=20, atr_period=10, multiplier=float("inf"))

    with pytest.raises(ValueError, match="multiplier must be positive"):
        KeltnerChannelStrategy(ema_period=20, atr_period=10, multiplier=-1.0)

    # Valid construction should succeed
    s = KeltnerChannelStrategy(ema_period=20, atr_period=10, multiplier=2.0)
    assert s.ema_period == 20
    assert s.atr_period == 10
    assert s.multiplier == 2.0


def test_validate_accepts_valid_values():
    s = _valid_kc()
    s.validate_parameters()  # Should not raise

    s = KeltnerChannelStrategy(ema_period=20, atr_period=10, multiplier=1.5)
    s.validate_parameters()  # Should not raise

    s = KeltnerChannelStrategy(ema_period=50, atr_period=20, multiplier=3.0)
    s.validate_parameters()  # Should not raise