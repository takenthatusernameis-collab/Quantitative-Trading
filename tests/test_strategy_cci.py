"""Tests for CCIStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import CCIStrategy


def _valid_cci():
    return CCIStrategy(period=20, threshold=100.0)


def test_validate_period_must_be_positive():
    s = _valid_cci()
    s.period = 0
    with pytest.raises(ValueError, match="period must be positive"):
        s.validate_parameters()


def test_validate_threshold_must_be_positive():
    s = _valid_cci()
    s.threshold = 0
    with pytest.raises(ValueError, match="threshold must be positive"):
        s.validate_parameters()


def test_validate_threshold_non_finite_rejected():
    s = _valid_cci()
    s.threshold = float("nan")
    with pytest.raises(ValueError, match="threshold must be positive"):
        s.validate_parameters()

    s = _valid_cci()
    s.threshold = float("inf")
    with pytest.raises(ValueError, match="threshold must be positive"):
        s.validate_parameters()

    s = _valid_cci()
    s.threshold = float("-inf")
    with pytest.raises(ValueError, match="threshold must be positive"):
        s.validate_parameters()


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="threshold must be positive"):
        CCIStrategy(period=20, threshold=float("nan"))

    with pytest.raises(ValueError, match="threshold must be positive"):
        CCIStrategy(period=20, threshold=float("inf"))

    with pytest.raises(ValueError, match="threshold must be positive"):
        CCIStrategy(period=20, threshold=-1.0)

    # Valid construction should succeed
    s = CCIStrategy(period=20, threshold=100.0)
    assert s.period == 20
    assert s.threshold == 100.0


def test_cci_constructs_with_defaults():
    s = CCIStrategy()
    assert s is not None


def test_cci_generates_signals():
    import numpy as np
    import pandas as pd

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

    data = {"AAPL": create_data()}
    s = CCIStrategy()
    signals = s.generate_signals(data)
    assert isinstance(signals, list)
