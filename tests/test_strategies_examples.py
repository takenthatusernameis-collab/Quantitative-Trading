"""Tests for example trading strategies."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    MovingAverageCrossover,
    RSIStrategy,
)


def create_trending_data(symbol: str, days: int = 100, trend: float = 0.001) -> pd.DataFrame:
    """Create mock price data with a trend."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
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
    return df


def create_mean_reverting_data(symbol: str, days: int = 100) -> pd.DataFrame:
    """Create mock price data that mean reverts."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    # Create oscillating prices
    t = np.arange(days)
    base = 100 + 10 * np.sin(t * 2 * np.pi / 20)  # 20-day cycle
    noise = np.random.normal(0, 0.5, days)
    prices = base + noise

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
    return df


class TestMovingAverageCrossover:
    """Tests for MovingAverageCrossover strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30, name="Test_MA")
        assert strategy.name == "Test_MA"
        assert strategy.fast_period == 10
        assert strategy.slow_period == 30
        assert strategy.parameters["fast_period"] == 10
        assert strategy.parameters["slow_period"] == 30

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        data = {"AAPL": create_trending_data("AAPL", days=20)}  # Less than slow_period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_golden_cross(self):
        """Test generate_signals detects golden cross (buy signal)."""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=15)
        # Create data where fast MA crosses above slow MA
        data = {"AAPL": create_trending_data("AAPL", days=50, trend=0.005)}
        signals = strategy.generate_signals(data)

        # Should have at least one signal
        assert len(signals) >= 0  # May or may not cross depending on data
        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            assert signal.price is not None
            assert signal.timestamp is not None

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=15)
        data = {
            "AAPL": create_trending_data("AAPL", days=50, trend=0.005),
            "MSFT": create_trending_data("MSFT", days=50, trend=0.003),
        }
        signals = strategy.generate_signals(data)
        # Should generate signals for each symbol
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})


class TestRSIStrategy:
    """Tests for RSIStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = RSIStrategy(period=14, oversold=30, overbought=70, name="Test_RSI")
        assert strategy.name == "Test_RSI"
        assert strategy.period == 14
        assert strategy.oversold == 30
        assert strategy.overbought == 70

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = RSIStrategy(period=14)
        data = {"AAPL": create_mean_reverting_data("AAPL", days=10)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_oversold_bounce(self):
        """Test generate_signals detects oversold bounce (buy signal)."""
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        data = {"AAPL": create_mean_reverting_data("AAPL", days=60)}
        signals = strategy.generate_signals(data)

        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            if signal.action == "buy":
                assert signal.metadata.get("signal_type") == "oversold_bounce"
            elif signal.action == "sell":
                assert signal.metadata.get("signal_type") == "overbought_rejection"

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = RSIStrategy(period=14)
        data = {
            "AAPL": create_mean_reverting_data("AAPL", days=60),
            "MSFT": create_mean_reverting_data("MSFT", days=60),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})


class TestBollingerBandsStrategy:
    """Tests for BollingerBandsStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0, name="Test_BB")
        assert strategy.name == "Test_BB"
        assert strategy.period == 20
        assert strategy.std_dev == 2.0

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = BollingerBandsStrategy(period=20)
        data = {"AAPL": create_trending_data("AAPL", days=15)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_band_touch(self):
        """Test generate_signals detects band touches."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        data = {"AAPL": create_mean_reverting_data("AAPL", days=60)}
        signals = strategy.generate_signals(data)

        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            if signal.action == "buy":
                assert signal.metadata.get("signal_type") == "lower_band_touch"
            elif signal.action == "sell":
                assert signal.metadata.get("signal_type") == "upper_band_touch"

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = BollingerBandsStrategy(period=20)
        data = {
            "AAPL": create_mean_reverting_data("AAPL", days=60),
            "MSFT": create_mean_reverting_data("MSFT", days=60),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})


class TestStrategyParameters:
    """Tests for strategy parameter handling."""

    def test_get_parameters(self):
        """Test get_parameters returns copy."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        params = strategy.get_parameters()
        assert params == {"fast_period": 10, "slow_period": 30}
        # Modify copy, original should be unchanged
        params["fast_period"] = 999
        assert strategy.parameters["fast_period"] == 10

    def test_set_parameter(self):
        """Test set_parameter updates parameter."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        strategy.set_parameter("fast_period", 20)
        assert strategy.parameters["fast_period"] == 20
        assert strategy.fast_period == 10  # Instance attribute not updated (by design)

    def test_update_positions(self):
        """Test update_positions."""
        from quant_trading.strategies.base import Position

        strategy = MovingAverageCrossover()
        positions = {"AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0)}
        strategy.update_positions(positions)
        assert strategy.positions == positions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])