"""Regression tests: strategy generate_signals with NaN/inf frames never crashes."""

import math

import pandas as pd
import pytest

from quant_trading.strategies.factory import create_strategy, strategy_keys


def _df(prices: list[float]) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp("2024-01-01"), periods=len(prices), freq="D")
    data: dict[str, list[float | int]] = {
        "open": prices,
        "high": prices,
        "low": prices,
        "close": prices,
        "volume": [1000000] * len(prices),
    }
    return pd.DataFrame(data=data, index=dates)


_NON_FINITE_FRAMES = [
    [1.0, 2.0, 3.0, float("nan"), 5.0],
    [1.0, 2.0, 3.0, float("inf"), 5.0],
    [1.0, 2.0, 3.0, float("-inf"), 5.0],
    [float("nan")] * 5,
    [float("inf")] * 5,
]


@pytest.mark.parametrize("key", strategy_keys())
@pytest.mark.parametrize("prices", _NON_FINITE_FRAMES)
def test_generate_signals_tolerates_non_finite_prices(key, prices):
    strategy = create_strategy(key)
    sigs = strategy.generate_signals({"AAPL": _df(prices)})
    assert isinstance(sigs, list)
    for sig in sigs:
        if getattr(sig, "strength", None) is not None:
            assert math.isfinite(sig.strength)
        if getattr(sig, "price", None) is not None:
            assert math.isfinite(sig.price)
