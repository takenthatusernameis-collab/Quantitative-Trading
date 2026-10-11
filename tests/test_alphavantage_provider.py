"""Tests for AlphaVantageProvider."""

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from quant_trading.data.yfinance_provider import AlphaVantageProvider


class FakeResponseError(Exception):
    """Custom exception for fake response errors."""



class FakeResponse:
    """Mock response for requests.get."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeResponseError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


DAILY_RESPONSE = {
    "Meta Data": {
        "1. Information": "Daily Prices (open, high, low, close) and Volumes",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-15",
        "4. Output Size": "Full size",
        "5. Time Zone": "US/Eastern",
    },
    "Time Series (Daily)": {
        "2024-01-15": {
            "1. open": "185.00",
            "2. high": "187.50",
            "3. low": "184.00",
            "4. close": "186.00",
            "5. adjusted close": "185.80",
            "6. volume": "50000000",
            "7. dividend amount": "0.00",
            "8. split coefficient": "1.0",
        },
        "2024-01-12": {
            "1. open": "182.00",
            "2. high": "186.00",
            "3. low": "181.00",
            "4. close": "184.50",
            "5. adjusted close": "184.30",
            "6. volume": "45000000",
            "7. dividend amount": "0.00",
            "8. split coefficient": "1.0",
        },
    },
}

BATCH_RESPONSE = {
    "Meta Data": {
        "1. Information": "Batch Stock Prices",
        "2. Symbols Requested": "AAPL,MSFT",
    },
    "Stock Prices": [
        {
            "1. symbol": "AAPL",
            "2. open": "185.00",
            "3. high": "187.50",
            "4. low": "184.00",
            "5. price": "186.00",
            "6. volume": "50000000",
        },
        {
            "1. symbol": "MSFT",
            "2. open": "380.00",
            "3. high": "385.00",
            "4. low": "378.00",
            "5. price": "382.00",
            "6. volume": "30000000",
        },
    ],
}

ERROR_RESPONSE = {"Error Message": "Invalid API call. Please retry or visit the documentation."}

RATE_LIMIT_RESPONSE = {"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."}


class TestAlphaVantageProvider:
    """Tests for AlphaVantageProvider."""

    @pytest.fixture
    def provider(self, tmp_path):
        """Create provider with temp cache dir."""
        return AlphaVantageProvider(
            api_key="test_key",
            cache_dir=str(tmp_path),
            cache_ttl_hours=1.0,
            timeout=10.0,
        )

    @pytest.fixture
    def provider_no_cache(self):
        """Create provider without cache."""
        return AlphaVantageProvider(
            api_key="test_key",
            cache_dir="",
            timeout=10.0,
        )

    def test_initialization(self, provider):
        """Test provider initialization."""
        assert provider.name == "alphavantage"
        assert provider._api_key == "test_key"

    def test_name_property(self, provider):
        """Test name property."""
        assert provider.name == "alphavantage"

    def test_fetch_daily_single_symbol(self, provider):
        """Test fetching daily data for single symbol."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(DAILY_RESPONSE)

            start = datetime(2024, 1, 10)
            end = datetime(2024, 1, 15)
            result = provider.fetch(["AAPL"], start=start, end=end, interval="1d")

            assert "AAPL" in result.data
            assert not result.errors
            assert not result.missing
            md = result.data["AAPL"]
            assert md.symbol == "AAPL"
            assert isinstance(md.data, pd.DataFrame)
            assert len(md.data) == 2
            assert list(md.data.columns) == [
                "open",
                "high",
                "low",
                "close",
                "adjusted_close",
                "volume",
                "dividend_amount",
                "split_coefficient",
            ]
            mock_get.assert_called_once()

    def test_fetch_daily_multiple_symbols(self, provider):
        """Test fetching daily data for multiple symbols."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(DAILY_RESPONSE)

            start = datetime(2024, 1, 10)
            end = datetime(2024, 1, 15)
            result = provider.fetch(["AAPL", "MSFT"], start=start, end=end, interval="1d")

            assert "AAPL" in result.data
            assert "MSFT" in result.data
            assert not result.errors
            assert not result.missing
            assert mock_get.call_count == 2

    def test_fetch_daily_with_missing_symbol(self, provider):
        """Test fetching daily data with missing symbol."""
        empty_response = {"Meta Data": {}, "Time Series (Daily)": {}}

        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(empty_response)

            result = provider.fetch(["INVALID"], interval="1d")

            assert "INVALID" in result.missing
            assert not result.data
            assert not result.errors

    def test_fetch_daily_api_error(self, provider):
        """Test handling of API error response."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(ERROR_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1d")

            assert "AAPL" in result.errors
            assert not result.data
            assert not result.missing

    def test_fetch_daily_rate_limit(self, provider):
        """Test handling of rate limit response."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(RATE_LIMIT_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1d")

            assert "AAPL" in result.errors
            assert isinstance(result.errors["AAPL"], RuntimeError)

    def test_fetch_batch_intraday(self, provider):
        """Test fetching intraday data using batch endpoint."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(BATCH_RESPONSE)

            result = provider.fetch(["AAPL", "MSFT"], interval="5min")

            assert "AAPL" in result.data
            assert "MSFT" in result.data
            assert not result.errors
            assert not result.missing
            mock_get.assert_called_once()

    def test_fetch_batch_missing_symbol(self, provider):
        """Test batch fetch with missing symbol."""
        partial_response = {
            "Meta Data": {},
            "Stock Prices": [
                {"1. symbol": "AAPL", "2. open": "185", "3. high": "187", "4. low": "184", "5. price": "186", "6. volume": "50000000"}
            ],
        }

        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(partial_response)

            result = provider.fetch(["AAPL", "MSFT"], interval="5min")

            assert "AAPL" in result.data
            assert "MSFT" in result.missing
            assert not result.errors

    def test_fetch_batch_api_error(self, provider):
        """Test batch fetch with API error."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(ERROR_RESPONSE)

            result = provider.fetch(["AAPL", "MSFT"], interval="5min")

            assert "AAPL" in result.errors
            assert "MSFT" in result.errors

    def test_fetch_latest(self, provider):
        """Test fetch_latest method."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(BATCH_RESPONSE)

            result = provider.fetch_latest(["AAPL", "MSFT"])

            assert "AAPL" in result.data
            assert "MSFT" in result.data
            mock_get.assert_called_once()

    def test_fetch_many_daily_fallback(self, provider):
        """Test fetch_many with daily intervals falls back to per-symbol."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(DAILY_RESPONSE)

            requests = [
                {"symbols": ["AAPL"], "start": datetime(2024, 1, 1), "end": datetime(2024, 1, 15), "interval": "1d"},
                {"symbols": ["MSFT"], "start": datetime(2024, 1, 1), "end": datetime(2024, 1, 15), "interval": "1d"},
            ]
            results = provider.fetch_many(requests)

            assert len(results) == 2
            for res in results.values():
                assert res.data
                assert not res.errors
            assert mock_get.call_count == 2

    def test_fetch_many_batch_intraday(self, provider):
        """Test fetch_many with intraday uses batch endpoint."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(BATCH_RESPONSE)

            requests = [
                {"symbols": ["AAPL"], "interval": "5min"},
                {"symbols": ["MSFT"], "interval": "5min"},
            ]
            results = provider.fetch_many(requests)

            assert len(results) == 2
            for res in results.values():
                assert res.data
            assert mock_get.call_count == 1

    def test_fetch_many_mixed_intervals(self, provider):
        """Test fetch_many with mixed intervals."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(DAILY_RESPONSE)

            requests = [
                {"symbols": ["AAPL"], "interval": "1d"},
                {"symbols": ["MSFT"], "interval": "5min"},
            ]
            results = provider.fetch_many(requests)

            assert len(results) == 2

    def test_disk_cache_hit(self, provider, tmp_path):
        """Test disk cache is used on second call."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(DAILY_RESPONSE)

            # First call - should hit API
            result1 = provider.fetch(["AAPL"], interval="1d")
            assert "AAPL" in result1.data
            assert mock_get.call_count == 1

            # Second call - should hit cache
            result2 = provider.fetch(["AAPL"], interval="1d")
            assert "AAPL" in result2.data
            assert mock_get.call_count == 1  # No additional call

    def test_no_cache_when_disabled(self, provider_no_cache):
        """Test no cache operations when cache_dir is empty."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(DAILY_RESPONSE)

            provider_no_cache.fetch(["AAPL"], interval="1d")
            provider_no_cache.fetch(["AAPL"], interval="1d")

            assert mock_get.call_count == 2

    def test_request_key_stable(self, provider):
        """Test _request_key produces stable keys."""
        key1 = provider._request_key(["AAPL", "MSFT"], datetime(2024, 1, 1), datetime(2024, 1, 15), "1d")
        key2 = provider._request_key(["MSFT", "AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 15), "1d")
        assert key1 == key2

    def test_cache_key_includes_interval(self, provider):
        """Test cache key includes interval."""
        key1 = provider._cache_key(["AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 15), "1d")
        key2 = provider._cache_key(["AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 15), "5min")
        assert key1 != key2

    def test_network_error_handling(self, provider):
        """Test handling of network errors."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            import requests
            mock_get.side_effect = requests.ConnectionError("Network unreachable")

            result = provider.fetch(["AAPL"], interval="1d")

            assert "AAPL" in result.errors
            assert isinstance(result.errors["AAPL"], requests.ConnectionError)

    def test_timeout_handling(self, provider):
        """Test handling of request timeout."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            import requests
            mock_get.side_effect = requests.Timeout("Request timed out")

            result = provider.fetch(["AAPL"], interval="1d")

            assert "AAPL" in result.errors
            assert isinstance(result.errors["AAPL"], requests.Timeout)


class TestAlphaVantageProviderIntegration:
    """Integration tests with DataManager."""

    def test_data_manager_delegates_to_alphavantage(self, tmp_path):
        """Test DataManager uses AlphaVantageProvider.fetch_many."""
        from quant_trading.data.providers import DataManager

        provider = AlphaVantageProvider(api_key="test_key", cache_dir=str(tmp_path))
        manager = DataManager([provider])

        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(BATCH_RESPONSE)

            requests = [
                {"symbols": ["AAPL"], "interval": "5min"},
                {"symbols": ["MSFT"], "interval": "5min"},
            ]
            results = manager.fetch_many(requests, provider_name="alphavantage", use_cache=False)

            assert len(results) == 2
            for res in results.values():
                assert res.data
            assert mock_get.call_count == 1

    def test_data_manager_cache_per_request(self, tmp_path):
        """Test DataManager caches per request key."""
        from quant_trading.data.providers import DataManager

        provider = AlphaVantageProvider(api_key="test_key", cache_dir=str(tmp_path))
        manager = DataManager([provider])

        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(BATCH_RESPONSE)

            requests = [{"symbols": ["AAPL"], "interval": "5min"}]
            results1 = manager.fetch_many(requests, provider_name="alphavantage", use_cache=True)
            results2 = manager.fetch_many(requests, provider_name="alphavantage", use_cache=True)

            assert len(results1) == 1
            assert len(results2) == 1
            assert mock_get.call_count == 1  # Second call uses cache