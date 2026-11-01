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


def test_generate_signals_incremental_path_emits_oversold_bounce_buy():
    # Declining prices drive RSI to the floor on the full recompute path and
    # establish incremental state. A subsequent up-bar (incremental path) lifts
    # RSI back above the oversold threshold, emitting a buy signal without a
    # full recompute.
    s = _valid_rsi()
    prices = [100.0, 99.0, 98.0, 97.0, 96.0]
    first = s.generate_signals({"AAPL": _df(prices)})
    assert first == []
    assert s._rsi_state["AAPL"]["n"] == 5
    assert s._rsi_state["AAPL"]["curr_rsi"] == 0.0

    sigs = s.generate_signals({"AAPL": _df(prices + [99.0])})
    assert len(sigs) == 1
    signal = sigs[0]
    assert signal.action == "buy"
    assert signal.strength == 1.0
    assert signal.metadata["signal_type"] == "oversold_bounce"
    assert signal.metadata["rsi"] == pytest.approx(75.0)


def test_generate_signals_incremental_path_emits_overbought_rejection_sell():
    # Rising prices pin RSI at the ceiling on the full recompute path and
    # establish incremental state. A subsequent down-bar (incremental path)
    # pulls RSI below the overbought threshold, emitting a sell signal
    # without a full recompute.
    s = _valid_rsi()
    prices = [100.0, 101.0, 102.0, 103.0, 104.0]
    first = s.generate_signals({"AAPL": _df(prices)})
    assert first == []
    assert s._rsi_state["AAPL"]["n"] == 5
    assert s._rsi_state["AAPL"]["curr_rsi"] == 100.0

    sigs = s.generate_signals({"AAPL": _df(prices + [100.0])})
    assert len(sigs) == 1
    signal = sigs[0]
    assert signal.action == "sell"
    assert signal.strength == 1.0
    assert signal.metadata["signal_type"] == "overbought_rejection"
    assert signal.metadata["rsi"] == pytest.approx(20.0)

    # The incremental result must agree with a full recompute.
    fresh = _valid_rsi()
    expected = fresh.generate_signals({"AAPL": _df(prices + [100.0])})
    assert [(sig.action, pytest.approx(sig.strength)) for sig in sigs] == [
        (sig.action, pytest.approx(sig.strength)) for sig in expected
    ]
