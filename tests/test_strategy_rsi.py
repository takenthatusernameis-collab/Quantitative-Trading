"""Tests for RSIStrategy validation branches."""

import pandas as pd
import pytest

from quant_trading.strategies.examples import RSIStrategy


def _df(prices):
    dates = pd.date_range(end=pd.Timestamp.now(), periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000000] * len(prices),
        },
        index=dates,
    )


def _valid_rsi():
    return RSIStrategy(period=2, oversold=30, overbought=70)


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


def test_generate_signals_full_path_skips_when_last_price_is_nan():
    s = _valid_rsi()
    sigs = s.generate_signals({"AAPL": _df([1.0, 2.0, 3.0, 4.0, float("nan")])})
    assert sigs == []


def test_generate_signals_incremental_path_skips_when_last_price_is_nan():
    s = _valid_rsi()
    prices = [1.0, 2.0, 3.0, 4.0]
    first = s.generate_signals({"AAPL": _df(prices)})
    assert isinstance(first, list)
    sigs = s.generate_signals({"AAPL": _df(prices + [float("nan")])})
    assert sigs == []
