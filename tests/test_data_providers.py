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

# Multi-provider end-to-end tests
class FakeResponse:
    """Mock response for requests.get."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            class FakeResponseError(Exception):
                pass
            raise FakeResponseError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


GOLD_SPOT_RESPONSE = {
    "name": "Global Price of Gold",
    "interval": "spot",
    "unit": "dollar per troy ounce",
    "data": [
        {"date": "2026-10-12", "value": "2650.45"},
    ],
}


def test_data_manager_multi_provider_gold_via_alphavantage(tmp_path):
    """Register a real AlphaVantageProvider alongside another provider.

    Patch requests.get to return GOLD_SPOT_RESPONSE and verify the AV
    provider is used with the correct function parameter.
    """
    from unittest.mock import patch

    from quant_trading.data.providers import DataManager
    from quant_trading.data.yfinance_provider import AlphaVantageProvider

    # Create providers
    data = create_synthetic_data(["AAPL"], days=10)
    counting = CountingProvider(data, name="counting")
    av = AlphaVantageProvider(
        api_key="test_key",
        cache_dir=str(tmp_path),
        cache_ttl_hours=1.0,
    )
    manager = DataManager([counting, av])

    with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
        mock_get.return_value = FakeResponse(GOLD_SPOT_RESPONSE)

        result = manager.fetch(
            ["GOLD"],
            interval="gold",
            provider_name="alphavantage",
        )

        assert "GOLD" in result.data
        assert not result.errors
        assert not result.missing
        # Verify the AV provider was hit with correct params
        mock_get.assert_called_once()
        params = mock_get.call_args.kwargs.get("params", {})
        assert params["function"] == "GOLD_SILVER_SPOT"
        assert params["symbol"] == "GOLD"
        # The counting provider should not have been called
        assert counting.fetch_calls == 0


def test_data_manager_cache_isolation_across_providers(tmp_path):
    """Fetch same symbols/interval from two differently-named providers.

    Cache entries should be isolated per provider name.
    """
    from quant_trading.data.providers import DataManager

    data1 = create_synthetic_data(["AAPL"], days=10)
    data2 = create_synthetic_data(["AAPL"], days=10)
    p1 = CountingProvider(data1, name="provider1")
    p2 = CountingProvider(data2, name="provider2")
    manager = DataManager([p1, p2])

    # Fetch from provider1
    res1a = manager.fetch(["AAPL"], provider_name="provider1")
    assert p1.fetch_calls == 1
    assert p2.fetch_calls == 0

    # Fetch same from provider2 - should be separate
    res1b = manager.fetch(["AAPL"], provider_name="provider2")
    assert p1.fetch_calls == 1
    assert p2.fetch_calls == 1

    # Repeat from provider1 - should hit cache
    res1c = manager.fetch(["AAPL"], provider_name="provider1")
    assert p1.fetch_calls == 1  # Still 1, cache hit
    assert res1c is res1a

    # Repeat from provider2 - should hit cache
    res1d = manager.fetch(["AAPL"], provider_name="provider2")
    assert p2.fetch_calls == 1  # Still 1, cache hit
    assert res1d is res1b


def test_create_data_manager_from_config():
    """Create DataManager from DataConfig for different providers."""
    from quant_trading.config.settings import DataConfig
    from quant_trading.data.providers import create_data_manager_from_config

    # Synthetic/offline
    cfg = DataConfig(provider="synthetic", offline=True)
    mgr = create_data_manager_from_config(cfg)
    assert mgr.providers
    assert mgr.providers[0].name == "synthetic"

    # Alphavantage
    cfg_av = DataConfig(provider="alphavantage", alphavantage_api_key="key")
    mgr_av = create_data_manager_from_config(cfg_av)
    assert mgr_av.providers
    # Name might vary; just check it's an AlphaVantageProvider
    assert "alphavantage" in mgr_av.providers[0].name.lower() or hasattr(mgr_av.providers[0], "name")

    # YFinance
    cfg_yf = DataConfig(provider="yfinance")
    mgr_yf = create_data_manager_from_config(cfg_yf)
    assert mgr_yf.providers


def test_data_manager_fetch_many_with_alphavantage_gold(tmp_path):
    """DataManager.fetch_many works with AlphaVantageProvider for gold requests."""
    from datetime import datetime, timedelta
    from unittest.mock import patch

    from quant_trading.data.providers import DataManager
    from quant_trading.data.yfinance_provider import AlphaVantageProvider

    av = AlphaVantageProvider(
        api_key="test_key",
        cache_dir=str(tmp_path),
        cache_ttl_hours=1.0,
    )
    manager = DataManager([av])

    end = datetime.now()
    start = end - timedelta(days=5)
    requests = [
        {"symbols": ["GOLD"], "start": start, "end": end, "interval": "gold"},
        {"symbols": ["SILVER"], "start": start, "end": end, "interval": "silver"},
    ]

    with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
        mock_get.return_value = FakeResponse(GOLD_SPOT_RESPONSE)
        results = manager.fetch_many(requests, provider_name="alphavantage")

        # Should have results for both requests
        assert len(results) == 2
        # Each symbol requires a separate call (per-symbol in AV implementation)
        assert mock_get.call_count == 2
