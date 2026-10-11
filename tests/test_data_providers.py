"""Tests for data provider interfaces and the DataManager batch fetch API."""

from datetime import datetime, timedelta

import pytest

from quant_trading.data.providers import (
    DataManager,
    DataProvider,
    FetchResult,
    MarketData,
)
from quant_trading.data.synthetic import create_synthetic_data


class CountingProvider(DataProvider):
    """Provider that records how many times fetch is called."""

    def __init__(self, data: dict, name: str = "counting"):
        self._data = data
        self._name = name
        self.fetch_calls = 0

    @property
    def name(self) -> str:
        return self._name

    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        self.fetch_calls += 1
        result = FetchResult()
        for symbol in symbols:
            if symbol in self._data:
                df = self._data[symbol]
                if start is not None:
                    df = df[df.index >= start]
                if end is not None:
                    df = df[df.index <= end]
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                )
            else:
                result.missing.append(symbol)
        return result

    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        return self.fetch(symbols)


def test_fetch_many_default_delegates_to_fetch():
    """DataProvider.fetch_many falls back to per-request fetch calls."""
    data = create_synthetic_data(["AAPL", "MSFT"], days=20)
    provider = CountingProvider(data)

    end = datetime.now()
    start = end - timedelta(days=10)
    requests = [
        {"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"},
        {"symbols": ["MSFT"], "start": start, "end": end, "interval": "1d"},
    ]

    results = provider.fetch_many(requests)

    assert provider.fetch_calls == 2
    assert set(results.keys()) == {
        provider._request_key(["AAPL"], start, end, "1d"),
        provider._request_key(["MSFT"], start, end, "1d"),
    }
    for result in results.values():
        assert isinstance(result, FetchResult)
        assert result.data


def test_fetch_many_request_key_is_stable():
    """Request keys are order-independent and deterministic."""
    provider = CountingProvider({})
    end = datetime.now()
    start = end - timedelta(days=5)

    key1 = provider._request_key(["AAPL", "MSFT"], start, end, "1d")
    key2 = provider._request_key(["MSFT", "AAPL"], start, end, "1d")
    assert key1 == key2
    assert key1 == "AAPL,MSFT|" + start.isoformat() + "|" + end.isoformat() + "|1d"


def test_data_manager_fetch_many_uses_provider_and_cache():
    """DataManager.fetch_many delegates to the provider and caches per request."""
    data = create_synthetic_data(["AAPL", "MSFT"], days=20)
    provider = CountingProvider(data)
    manager = DataManager([provider])

    end = datetime.now()
    start = end - timedelta(days=10)
    requests = [
        {"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"},
        {"symbols": ["MSFT"], "start": start, "end": end, "interval": "1d"},
    ]

    results = manager.fetch_many(requests)
    assert provider.fetch_calls == 2
    assert len(results) == 2

    # Second call should hit the in-memory cache for every request.
    cached_results = manager.fetch_many(requests)
    assert provider.fetch_calls == 2
    assert set(cached_results.keys()) == set(results.keys())
    for key, result in cached_results.items():
        assert result is results[key]


def test_data_manager_fetch_many_respects_provider_name():
    """DataManager.fetch_many can target a named provider."""
    data = create_synthetic_data(["AAPL"], days=10)
    provider = CountingProvider(data, name="primary")
    other = CountingProvider({}, name="secondary")
    manager = DataManager([other, provider])

    end = datetime.now()
    start = end - timedelta(days=5)
    results = manager.fetch_many(
        [{"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"}],
        provider_name="primary",
    )
    assert provider.fetch_calls == 1
    assert other.fetch_calls == 0
    assert results


def test_data_manager_fetch_many_no_provider_raises():
    """DataManager.fetch_many raises when no provider is available."""
    manager = DataManager([])
    with pytest.raises(ValueError):
        manager.fetch_many([{"symbols": ["AAPL"]}])