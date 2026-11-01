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


def test_incremental_update_path_is_reached():
    # The incremental-update branch requires a prior call whose state has
    # ``n == current_len - 1`` for the same symbol on the same instance.
    prices = [10.0, 10.0, 10.0, 10.0, 10.0, 15.0]
    s = MovingAverageCrossover(fast_period=3, slow_period=5)

    first = s.generate_signals({"AAPL": _df(prices[:5])})
    assert first == []
    assert s._ma_state["AAPL"]["n"] == 5

    second = s.generate_signals({"AAPL": _df(prices[:6])})
    assert s._ma_state["AAPL"]["n"] == 6
    assert len(second) == 1
    assert second[0].action == "buy"
    assert 0.0 <= second[0].strength <= 1.0

    # The incremental result must agree with a full recompute.
    fresh = MovingAverageCrossover(fast_period=3, slow_period=5)
    expected = fresh.generate_signals({"AAPL": _df(prices[:6])})
    assert [(sig.action, pytest.approx(sig.strength)) for sig in second] == [
        (sig.action, pytest.approx(sig.strength)) for sig in expected
    ]


def test_incremental_slow_window_still_growing_branch():
    # Force the incremental path's "window still growing" else-branch for the
    # slow moving average by making the prior state look one bar shorter than
    # the slow window, while keeping the sums consistent.
    prices = [1.0, 2.0, 3.0, 4.0, 5.0]
    s = MovingAverageCrossover(fast_period=3, slow_period=5)
    s.generate_signals({"AAPL": _df(prices)})
    assert s._ma_state["AAPL"]["n"] == 5
    s._ma_state["AAPL"]["n"] = 4
    out = s.generate_signals({"AAPL": _df(prices)})
    assert isinstance(out, list)
    assert s._ma_state["AAPL"]["n"] == 5
