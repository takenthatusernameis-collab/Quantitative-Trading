"""Tests for CCIStrategy."""

import numpy as np
import pandas as pd

from quant_trading.strategies.examples import CCIStrategy


def create_data(days: int = 100, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    prices = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, days)))
    df = pd.DataFrame(
        {
            "open": prices * 1.0,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


def test_cci_constructs_with_defaults():
    s = CCIStrategy()
    assert s is not None


def test_cci_generates_signals():
    data = {"AAPL": create_data()}
    s = CCIStrategy()
    signals = s.generate_signals(data)
    assert isinstance(signals, list)
