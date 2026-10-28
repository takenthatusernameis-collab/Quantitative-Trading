"""Tests for StochRSIStrategy."""

import numpy as np
import pandas as pd
import pytest

from quant_trading.strategies.examples import StochRSIStrategy


def create_trending_data(symbol: str, days: int = 100, trend: float = 0.001) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    returns = np.random.normal(trend, 0.02, days)
    prices = 100 * np.exp(np.cumsum(returns))
    df = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
            "high": prices * (1 + np.random.uniform(0, 0.01, days)),
            "low": prices * (1 - np.random.uniform(0, 0.01, days)),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


class TestStochRSIStrategy:
    def test_initialization(self):
        strategy = StochRSIStrategy(rsi_period=10, name="Test_StochRSI")
        assert strategy.name == "Test_StochRSI"
        assert strategy.rsi_period == 10
        assert strategy.parameters["rsi_period"] == 10

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="rsi_period must be positive"):
            StochRSIStrategy(rsi_period=0)
        with pytest.raises(ValueError, match="stoch_period must be positive"):
            StochRSIStrategy(stoch_period=0)
        with pytest.raises(ValueError, match="k_period must be positive"):
            StochRSIStrategy(k_period=0)
        with pytest.raises(ValueError, match="d_period must be positive"):
            StochRSIStrategy(d_period=0)
        with pytest.raises(ValueError, match="oversold must be between"):
            StochRSIStrategy(oversold=0)
        with pytest.raises(ValueError, match="overbought must be between"):
            StochRSIStrategy(overbought=100)
        with pytest.raises(ValueError, match="oversold must be less than overbought"):
            StochRSIStrategy(oversold=50, overbought=40)

    def test_generate_signals_insufficient_data(self):
        strategy = StochRSIStrategy()
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multi_symbol(self):
        strategy = StochRSIStrategy()
        data = {
            "AAPL": create_trending_data("AAPL", days=60),
            "MSFT": create_trending_data("MSFT", days=60),
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol in ("AAPL", "MSFT")
            assert s.action in ("buy", "sell")
            assert 0.0 <= s.strength <= 1.0

    def test_use_midline_flag(self):
        strategy = StochRSIStrategy(use_midline=True)
        data = {"AAPL": create_trending_data("AAPL", days=60)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
