"""Tests for MovingAverageCrossover (ma) strategy."""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.strategies.examples import MovingAverageCrossover


def _df(prices):
    dates = pd.date_range(end=datetime.now(), periods=len(prices), freq="D")
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


def test_init_defaults():
    s = MovingAverageCrossover()
    assert s.fast_period == 10
    assert s.slow_period == 30
    assert s.name == "MA_Crossover"


def test_validate_params():
    with pytest.raises(ValueError):
        MovingAverageCrossover(fast_period=0)
    with pytest.raises(ValueError):
        MovingAverageCrossover(fast_period=20, slow_period=10)


def test_insufficient_data():
    s = MovingAverageCrossover(fast_period=2, slow_period=4)
    assert s.generate_signals({"AAPL": _df([1.0, 2.0, 3.0])}) == []


def test_signal_shape():
    # Build data that crosses
    prices = [10.0] * 30 + [20.0] * 5
    s = MovingAverageCrossover(fast_period=3, slow_period=5)
    sigs = s.generate_signals({"AAPL": _df(prices)})
    for sig in sigs:
        assert sig.symbol == "AAPL"
        assert sig.action in ("buy", "sell", "hold", "short")
        assert 0.0 <= sig.strength <= 1.0
