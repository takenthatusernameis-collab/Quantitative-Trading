"""Deterministic tests for synthetic data generation.

Covers :func:`quant_trading.data.synthetic.create_synthetic_data` and
:class:`quant_trading.data.synthetic.SyntheticDataProvider`.
"""

from datetime import datetime

import pandas as pd

from quant_trading.data.synthetic import (
    DEFAULT_SEED,
    SyntheticDataProvider,
    create_synthetic_data,
    create_synthetic_provider,
)


def test_create_synthetic_data_structure():
    """Returned frames have OHLCV columns, a DatetimeIndex, and the requested length."""
    data = create_synthetic_data(["AAPL"], days=10, seed=DEFAULT_SEED)

    assert set(data.keys()) == {"AAPL"}
    df = data["AAPL"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 10
    assert df.index.freqstr == "D"


def test_create_synthetic_data_is_reproducible():
    """Same arguments produce byte-identical output."""
    end = datetime(2026, 6, 1)
    first = create_synthetic_data(["AAPL", "MSFT"], days=25, seed=7, end_date=end)
    second = create_synthetic_data(["AAPL", "MSFT"], days=25, seed=7, end_date=end)

    for symbol in first:
        pd.testing.assert_frame_equal(first[symbol], second[symbol])


def test_create_synthetic_data_seed_changes_output():
    """Different seeds produce different close series."""
    first = create_synthetic_data(["AAPL"], days=50, seed=1)["AAPL"]["close"]
    second = create_synthetic_data(["AAPL"], days=50, seed=2)["AAPL"]["close"]

    assert not first.equals(second)


def test_create_synthetic_data_ohlc_invariants():
    """Low <= close <= high on every row; volume positive."""
    data = create_synthetic_data(["AAPL", "MSFT"], days=30, seed=3)

    for df in data.values():
        assert (df["low"] <= df["close"]).all()
        assert (df["close"] <= df["high"]).all()
        assert (df["volume"] > 0).all()
        assert (df["volume"] <= 10_000_000).all()


def test_create_synthetic_data_end_date_window():
    """end_date bounds the generated range; last index <= end_date."""
    end = datetime(2026, 1, 15)
    data = create_synthetic_data(["AAPL"], days=40, seed=42, end_date=end)

    df = data["AAPL"]
    assert df.index.max() <= pd.Timestamp(end)
    assert len(df) == 40


def test_create_synthetic_provider_fetch_window():
    """Provider.fetch filters by start/end window."""
    data = create_synthetic_data(["AAPL"], days=30, seed=11, end_date=datetime(2026, 2, 1))
    provider = SyntheticDataProvider(data)

    start = datetime(2026, 1, 10)
    end = datetime(2026, 1, 20)
    result = provider.fetch(["AAPL"], start=start, end=end)

    assert "AAPL" in result.data
    assert not result.missing
    df = result.data["AAPL"].data
    assert df.index.min() >= pd.Timestamp(start)
    assert df.index.max() <= pd.Timestamp(end)


def test_create_synthetic_provider_missing_symbol():
    """Unknown symbols are reported missing and data stays empty."""
    provider = SyntheticDataProvider(create_synthetic_data(["AAPL"], days=10, seed=1))
    result = provider.fetch(["UNKNOWN", "AAPL"])

    assert "UNKNOWN" in result.missing
    assert "AAPL" in result.data
    assert not result.is_success


def test_create_synthetic_provider_convenience_wrapper():
    """create_synthetic_provider builds a usable provider with the default name."""
    provider = create_synthetic_provider(["AAPL", "MSFT"], days=20, seed=99)

    assert provider.name == "synthetic"
    result = provider.fetch(["AAPL", "MSFT"])
    assert "AAPL" in result.data
    assert "MSFT" in result.data
    assert not result.missing
    assert not result.errors


def test_synthetic_provider_fetch_latest():
    """fetch_latest uses fetch without a window."""
    provider = create_synthetic_provider(["AAPL"], days=10)
    result = provider.fetch_latest(["AAPL"])
    assert result.is_success
    assert "AAPL" in result.data


def test_default_seed_constant():
    """DEFAULT_SEED is the documented default of 42."""
    assert DEFAULT_SEED == 42
