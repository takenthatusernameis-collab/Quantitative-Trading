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

INTRADAY_RESPONSE = {
    "Meta Data": {
        "1. Information": "Intraday (5min) open, high, low, close prices and volume",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-15 19:55:00",
        "4. Interval": "5min",
        "5. Output Size": "Full size",
        "6. Time Zone": "US/Eastern",
    },
    "Time Series (5min)": {
        "2024-01-15 19:55:00": {
            "1. open": "185.00",
            "2. high": "185.50",
            "3. low": "184.80",
            "4. close": "185.20",
            "5. volume": "100000",
        },
        "2024-01-15 19:50:00": {
            "1. open": "184.50",
            "2. high": "185.00",
            "3. low": "184.20",
            "4. close": "184.80",
            "5. volume": "120000",
        },
        "2024-01-15 19:45:00": {
            "1. open": "184.00",
            "2. high": "184.60",
            "3. low": "183.80",
            "4. close": "184.30",
            "5. volume": "110000",
        },
    },
}

INTRADAY_RESPONSE_1MIN = {
    "Meta Data": {
        "1. Information": "Intraday (1min) open, high, low, close prices and volume",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-15 19:59:00",
        "4. Interval": "1min",
        "5. Output Size": "Full size",
        "6. Time Zone": "US/Eastern",
    },
    "Time Series (1min)": {
        "2024-01-15 19:59:00": {
            "1. open": "185.00",
            "2. high": "185.10",
            "3. low": "184.90",
            "4. close": "185.05",
            "5. volume": "5000",
        },
        "2024-01-15 19:58:00": {
            "1. open": "184.95",
            "2. high": "185.05",
            "3. low": "184.85",
            "4. close": "184.98",
            "5. volume": "4800",
        },
    },
}

WEEKLY_RESPONSE = {
    "Meta Data": {
        "1. Information": "Weekly Prices (open, high, low, close) and Volumes",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-12",
        "4. Time Zone": "US/Eastern",
    },
    "Weekly Time Series": {
        "2024-01-12": {
            "1. open": "182.00",
            "2. high": "188.00",
            "3. low": "180.00",
            "4. close": "186.50",
            "5. volume": "250000000",
        },
        "2024-01-05": {
            "1. open": "178.00",
            "2. high": "185.00",
            "3. low": "177.00",
            "4. close": "182.50",
            "5. volume": "230000000",
        },
    },
}

WEEKLY_ADJUSTED_RESPONSE = {
    "Meta Data": {
        "1. Information": "Weekly Adjusted Prices and Volumes",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-12",
        "4. Time Zone": "US/Eastern",
    },
    "Weekly Adjusted Time Series": {
        "2024-01-12": {
            "1. open": "182.00",
            "2. high": "188.00",
            "3. low": "180.00",
            "4. close": "186.50",
            "5. adjusted close": "186.20",
            "6. volume": "250000000",
            "7. dividend amount": "0.25",
            "8. split coefficient": "1.0",
        },
        "2024-01-05": {
            "1. open": "178.00",
            "2. high": "185.00",
            "3. low": "177.00",
            "4. close": "182.50",
            "5. adjusted close": "182.20",
            "6. volume": "230000000",
            "7. dividend amount": "0.00",
            "8. split coefficient": "1.0",
        },
    },
}

MONTHLY_RESPONSE = {
    "Meta Data": {
        "1. Information": "Monthly Prices (open, high, low, close) and Volumes",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-31",
        "4. Time Zone": "US/Eastern",
    },
    "Monthly Time Series": {
        "2024-01-31": {
            "1. open": "175.00",
            "2. high": "195.00",
            "3. low": "172.00",
            "4. close": "186.00",
            "5. volume": "1200000000",
        },
        "2023-12-29": {
            "1. open": "180.00",
            "2. high": "188.00",
            "3. low": "175.00",
            "4. close": "178.00",
            "5. volume": "1100000000",
        },
    },
}

MONTHLY_ADJUSTED_RESPONSE = {
    "Meta Data": {
        "1. Information": "Monthly Adjusted Prices and Volumes",
        "2. Symbol": "AAPL",
        "3. Last Refreshed": "2024-01-31",
        "4. Time Zone": "US/Eastern",
    },
    "Monthly Adjusted Time Series": {
        "2024-01-31": {
            "1. open": "175.00",
            "2. high": "195.00",
            "3. low": "172.00",
            "4. close": "186.00",
            "5. adjusted close": "185.80",
            "6. volume": "1200000000",
            "7. dividend amount": "0.25",
            "8. split coefficient": "1.0",
        },
        "2023-12-29": {
            "1. open": "180.00",
            "2. high": "188.00",
            "3. low": "175.00",
            "4. close": "178.00",
            "5. adjusted close": "177.80",
            "6. volume": "1100000000",
            "7. dividend amount": "0.00",
            "8. split coefficient": "1.0",
        },
    },
}

GLOBAL_QUOTE_RESPONSE = {
    "Global Quote": {
        "01. symbol": "AAPL",
        "02. open": "185.00",
        "03. high": "187.50",
        "04. low": "184.00",
        "05. price": "186.00",
        "06. volume": "50000000",
        "07. latest trading day": "2024-01-15",
        "08. previous close": "184.50",
        "09. change": "1.50",
        "10. change percent": "0.81%",
    }
}

SYMBOL_SEARCH_RESPONSE = {
    "bestMatches": [
        {
            "1. symbol": "AAPL",
            "2. name": "Apple Inc.",
            "3. type": "Equity",
            "4. region": "United States",
            "5. market": "NASDAQ",
            "6. currency": "USD",
            "7. matchScore": "1.0000",
        },
        {
            "1. symbol": "AAPL",
            "2. name": "Apple Inc. - Class A",
            "3. type": "Equity",
            "4. region": "United States",
            "5. market": "NASDAQ",
            "6. currency": "USD",
            "7. matchScore": "0.8500",
        },
    ]
}

SYMBOL_SEARCH_EMPTY_RESPONSE = {"bestMatches": []}


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

    def test_fetch_intraday_5min(self, provider):
        """Test fetching intraday data with 5min interval (TIME_SERIES_INTRADAY)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            start = datetime(2024, 1, 15, 19, 40)
            end = datetime(2024, 1, 15, 20, 0)
            result = provider.fetch(["AAPL"], start=start, end=end, interval="5m")

            assert "AAPL" in result.data
            assert not result.errors
            assert not result.missing
            md = result.data["AAPL"]
            assert md.symbol == "AAPL"
            assert isinstance(md.data, pd.DataFrame)
            assert len(md.data) == 3
            assert list(md.data.columns) == ["open", "high", "low", "close", "volume"]
            # Check metadata indicates intraday endpoint
            assert md.metadata.get("function") == "TIME_SERIES_INTRADAY"
            assert md.metadata.get("interval") == "5min"
            mock_get.assert_called_once()

    def test_fetch_intraday_1min(self, provider):
        """Test fetching intraday data with 1min interval."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE_1MIN)

            result = provider.fetch(["AAPL"], interval="1m")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert len(md.data) == 2
            assert md.metadata.get("interval") == "1min"
            # Check interval mapping
            _args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            assert params.get("interval") == "1min"

    def test_fetch_intraday_15min(self, provider):
        """Test fetching intraday data with 15min interval."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="15m")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("interval") == "15min"
            _args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            assert params.get("interval") == "15min"

    def test_fetch_intraday_30min(self, provider):
        """Test fetching intraday data with 30min interval."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="30m")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("interval") == "30min"
            _args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            assert params.get("interval") == "30min"

    def test_fetch_intraday_1h(self, provider):
        """Test fetching intraday data with 1h interval."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1h")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("interval") == "60min"
            _args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            assert params.get("interval") == "60min"

    def test_fetch_intraday_60m_alias(self, provider):
        """Test fetching intraday data with 60m alias for 1h."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="60m")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("interval") == "60min"
            _args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            assert params.get("interval") == "60min"

    def test_fetch_intraday_date_filtering(self, provider):
        """Test that intraday response is filtered by start/end dates."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            # Request only the last 2 bars
            start = datetime(2024, 1, 15, 19, 50)
            end = datetime(2024, 1, 15, 19, 55)
            result = provider.fetch(["AAPL"], start=start, end=end, interval="5m")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert len(md.data) == 2  # Only 19:50 and 19:55 bars
            # Verify dates are in range
            for idx in md.data.index:
                assert start <= idx <= end

    def test_fetch_intraday_multiple_symbols(self, provider):
        """Test fetching intraday data for multiple symbols."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(INTRADAY_RESPONSE)

            result = provider.fetch(["AAPL", "MSFT"], interval="5m")

            assert "AAPL" in result.data
            assert "MSFT" in result.data
            assert mock_get.call_count == 2  # Per-symbol calls

    def test_fetch_intraday_api_error(self, provider):
        """Test handling of API error for intraday endpoint."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(ERROR_RESPONSE)

            result = provider.fetch(["AAPL"], interval="5m")

            assert "AAPL" in result.errors
            assert not result.data

    def test_fetch_intraday_rate_limit(self, provider):
        """Test handling of rate limit for intraday endpoint."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(RATE_LIMIT_RESPONSE)

            result = provider.fetch(["AAPL"], interval="5m")

            assert "AAPL" in result.errors
            assert isinstance(result.errors["AAPL"], RuntimeError)

    def test_fetch_intraday_empty_response(self, provider):
        """Test handling of empty intraday response."""
        empty_intraday = {
            "Meta Data": {},
            "Time Series (5min)": {},
        }
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(empty_intraday)

            result = provider.fetch(["AAPL"], interval="5m")

            assert "AAPL" in result.missing
            assert not result.data
            assert not result.errors

    def test_intraday_interval_mapping(self, provider):
        """Test INTRADAY_INTERVALS mapping."""
        assert provider.INTRADAY_INTERVALS["1m"] == "1min"
        assert provider.INTRADAY_INTERVALS["5m"] == "5min"
        assert provider.INTRADAY_INTERVALS["15m"] == "15min"
        assert provider.INTRADAY_INTERVALS["30m"] == "30min"
        assert provider.INTRADAY_INTERVALS["1h"] == "60min"
        assert provider.INTRADAY_INTERVALS["60m"] == "60min"

    def test_build_intraday_params(self, provider):
        """Test _build_intraday_params method."""
        params = provider._build_intraday_params("AAPL", "5m")
        assert params["function"] == "TIME_SERIES_INTRADAY"
        assert params["symbol"] == "AAPL"
        assert params["interval"] == "5min"
        assert params["apikey"] == "test_key"
        assert params["outputsize"] == "full"
        assert params["datatype"] == "json"

    def test_parse_intraday_response(self, provider):
        """Test _parse_intraday_response method."""
        start = datetime(2024, 1, 15, 19, 40)
        end = datetime(2024, 1, 15, 20, 0)
        df = provider._parse_intraday_response("AAPL", INTRADAY_RESPONSE, start, end)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "date"
        # Verify sorted index
        assert df.index.is_monotonic_increasing

    def test_parse_intraday_response_different_intervals(self, provider):
        """Test parsing intraday response with different interval key names."""
        response_1min = {
            "Meta Data": {"4. Interval": "1min"},
            "Time Series (1min)": {
                "2024-01-15 19:59:00": {"1. open": "185", "2. high": "186", "3. low": "184", "4. close": "185", "5. volume": "1000"},
            },
        }
        df = provider._parse_intraday_response("AAPL", response_1min, None, None)
        assert df is not None
        assert len(df) == 1
        assert "1. open" not in df.columns  # Should be renamed to 'open'

    # Weekly tests
    def test_fetch_weekly(self, provider):
        """Test fetching weekly data (TIME_SERIES_WEEKLY)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(WEEKLY_RESPONSE)

            start = datetime(2024, 1, 1)
            end = datetime(2024, 1, 15)
            result = provider.fetch(["AAPL"], start=start, end=end, interval="weekly")

            assert "AAPL" in result.data
            assert not result.errors
            assert not result.missing
            md = result.data["AAPL"]
            assert md.symbol == "AAPL"
            assert isinstance(md.data, pd.DataFrame)
            assert len(md.data) == 2
            assert list(md.data.columns) == ["open", "high", "low", "close", "volume"]
            assert md.metadata.get("function") == "TIME_SERIES_WEEKLY"
            mock_get.assert_called_once()

    def test_fetch_weekly_1w_alias(self, provider):
        """Test fetching weekly data with 1w alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(WEEKLY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1w")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "TIME_SERIES_WEEKLY"

    def test_fetch_weekly_week_alias(self, provider):
        """Test fetching weekly data with week alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(WEEKLY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="week")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "TIME_SERIES_WEEKLY"

    def test_fetch_weekly_adjusted(self, provider):
        """Test fetching weekly adjusted data (TIME_SERIES_WEEKLY_ADJUSTED)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(WEEKLY_ADJUSTED_RESPONSE)

            result = provider.fetch(["AAPL"], interval="weekly_adjusted")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert len(md.data) == 2
            assert list(md.data.columns) == [
                "open", "high", "low", "close", "adjusted_close",
                "volume", "dividend_amount", "split_coefficient"
            ]
            assert md.metadata.get("function") == "TIME_SERIES_WEEKLY_ADJUSTED"

    def test_fetch_weekly_1wa_alias(self, provider):
        """Test fetching weekly adjusted data with 1wa alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(WEEKLY_ADJUSTED_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1wa")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "TIME_SERIES_WEEKLY_ADJUSTED"

    def test_build_weekly_params(self, provider):
        """Test _build_weekly_params method."""
        params = provider._build_weekly_params("AAPL")
        assert params["function"] == "TIME_SERIES_WEEKLY"
        assert params["symbol"] == "AAPL"
        assert params["apikey"] == "test_key"
        assert params["datatype"] == "json"

    def test_build_weekly_adjusted_params(self, provider):
        """Test _build_weekly_adjusted_params method."""
        params = provider._build_weekly_adjusted_params("AAPL")
        assert params["function"] == "TIME_SERIES_WEEKLY_ADJUSTED"
        assert params["symbol"] == "AAPL"
        assert params["apikey"] == "test_key"
        assert params["datatype"] == "json"

    def test_parse_weekly_response(self, provider):
        """Test _parse_weekly_response method."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 15)
        df = provider._parse_weekly_response("AAPL", WEEKLY_RESPONSE, start, end)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "date"
        assert df.index.is_monotonic_increasing

    def test_parse_weekly_adjusted_response(self, provider):
        """Test _parse_weekly_adjusted_response method."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 15)
        df = provider._parse_weekly_adjusted_response("AAPL", WEEKLY_ADJUSTED_RESPONSE, start, end)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == [
            "open", "high", "low", "close", "adjusted_close",
            "volume", "dividend_amount", "split_coefficient"
        ]
        assert df.index.name == "date"
        assert df.index.is_monotonic_increasing

    # Monthly tests
    def test_fetch_monthly(self, provider):
        """Test fetching monthly data (TIME_SERIES_MONTHLY)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(MONTHLY_RESPONSE)

            start = datetime(2023, 12, 1)
            end = datetime(2024, 1, 31)
            result = provider.fetch(["AAPL"], start=start, end=end, interval="monthly")

            assert "AAPL" in result.data
            assert not result.errors
            assert not result.missing
            md = result.data["AAPL"]
            assert md.symbol == "AAPL"
            assert isinstance(md.data, pd.DataFrame)
            assert len(md.data) == 2
            assert list(md.data.columns) == ["open", "high", "low", "close", "volume"]
            assert md.metadata.get("function") == "TIME_SERIES_MONTHLY"
            mock_get.assert_called_once()

    def test_fetch_monthly_1mo_alias(self, provider):
        """Test fetching monthly data with 1mo alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(MONTHLY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1mo")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "TIME_SERIES_MONTHLY"

    def test_fetch_monthly_month_alias(self, provider):
        """Test fetching monthly data with month alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(MONTHLY_RESPONSE)

            result = provider.fetch(["AAPL"], interval="month")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "TIME_SERIES_MONTHLY"

    def test_fetch_monthly_adjusted(self, provider):
        """Test fetching monthly adjusted data (TIME_SERIES_MONTHLY_ADJUSTED)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(MONTHLY_ADJUSTED_RESPONSE)

            result = provider.fetch(["AAPL"], interval="monthly_adjusted")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert len(md.data) == 2
            assert list(md.data.columns) == [
                "open", "high", "low", "close", "adjusted_close",
                "volume", "dividend_amount", "split_coefficient"
            ]
            assert md.metadata.get("function") == "TIME_SERIES_MONTHLY_ADJUSTED"

    def test_fetch_monthly_1ma_alias(self, provider):
        """Test fetching monthly adjusted data with 1ma alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(MONTHLY_ADJUSTED_RESPONSE)

            result = provider.fetch(["AAPL"], interval="1ma")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "TIME_SERIES_MONTHLY_ADJUSTED"

    def test_build_monthly_params(self, provider):
        """Test _build_monthly_params method."""
        params = provider._build_monthly_params("AAPL")
        assert params["function"] == "TIME_SERIES_MONTHLY"
        assert params["symbol"] == "AAPL"
        assert params["apikey"] == "test_key"
        assert params["datatype"] == "json"

    def test_build_monthly_adjusted_params(self, provider):
        """Test _build_monthly_adjusted_params method."""
        params = provider._build_monthly_adjusted_params("AAPL")
        assert params["function"] == "TIME_SERIES_MONTHLY_ADJUSTED"
        assert params["symbol"] == "AAPL"
        assert params["apikey"] == "test_key"
        assert params["datatype"] == "json"

    def test_parse_monthly_response(self, provider):
        """Test _parse_monthly_response method."""
        start = datetime(2023, 12, 1)
        end = datetime(2024, 1, 31)
        df = provider._parse_monthly_response("AAPL", MONTHLY_RESPONSE, start, end)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "date"
        assert df.index.is_monotonic_increasing

    def test_parse_monthly_adjusted_response(self, provider):
        """Test _parse_monthly_adjusted_response method."""
        start = datetime(2023, 12, 1)
        end = datetime(2024, 1, 31)
        df = provider._parse_monthly_adjusted_response("AAPL", MONTHLY_ADJUSTED_RESPONSE, start, end)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == [
            "open", "high", "low", "close", "adjusted_close",
            "volume", "dividend_amount", "split_coefficient"
        ]
        assert df.index.name == "date"
        assert df.index.is_monotonic_increasing

    # Global Quote tests
    def test_fetch_global_quote(self, provider):
        """Test fetching global quote (GLOBAL_QUOTE)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(GLOBAL_QUOTE_RESPONSE)

            result = provider.fetch(["AAPL"], interval="quote")

            assert "AAPL" in result.data
            assert not result.errors
            assert not result.missing
            md = result.data["AAPL"]
            assert md.symbol == "AAPL"
            assert isinstance(md.data, pd.DataFrame)
            assert len(md.data) == 1
            assert "price" in md.data.columns
            assert "change" in md.data.columns
            assert "change_percent" in md.data.columns
            assert md.metadata.get("function") == "GLOBAL_QUOTE"
            mock_get.assert_called_once()

    def test_fetch_global_quote_realtime_alias(self, provider):
        """Test fetching global quote with realtime alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(GLOBAL_QUOTE_RESPONSE)

            result = provider.fetch(["AAPL"], interval="realtime")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "GLOBAL_QUOTE"

    def test_fetch_global_quote_rt_alias(self, provider):
        """Test fetching global quote with rt alias."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(GLOBAL_QUOTE_RESPONSE)

            result = provider.fetch(["AAPL"], interval="rt")

            assert "AAPL" in result.data
            md = result.data["AAPL"]
            assert md.metadata.get("function") == "GLOBAL_QUOTE"

    def test_fetch_global_quote_multiple_symbols(self, provider):
        """Test fetching global quote for multiple symbols."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(GLOBAL_QUOTE_RESPONSE)

            result = provider.fetch(["AAPL", "MSFT"], interval="quote")

            assert "AAPL" in result.data
            assert "MSFT" in result.data
            assert mock_get.call_count == 2  # Per-symbol calls

    def test_build_global_quote_params(self, provider):
        """Test _build_global_quote_params method."""
        params = provider._build_global_quote_params("AAPL")
        assert params["function"] == "GLOBAL_QUOTE"
        assert params["symbol"] == "AAPL"
        assert params["apikey"] == "test_key"
        assert params["datatype"] == "json"

    def test_parse_global_quote_response(self, provider):
        """Test _parse_global_quote_response method."""
        df = provider._parse_global_quote_response("AAPL", GLOBAL_QUOTE_RESPONSE)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "price" in df.columns
        assert "change" in df.columns
        assert "change_percent" in df.columns
        assert "latest_trading_day" in df.columns
        assert "previous_close" in df.columns

    def test_global_quote_api_error(self, provider):
        """Test handling of API error for global quote endpoint."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(ERROR_RESPONSE)

            result = provider.fetch(["AAPL"], interval="quote")

            assert "AAPL" in result.errors
            assert not result.data

    def test_global_quote_rate_limit(self, provider):
        """Test handling of rate limit for global quote endpoint."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(RATE_LIMIT_RESPONSE)

            result = provider.fetch(["AAPL"], interval="quote")

            assert "AAPL" in result.errors
            assert isinstance(result.errors["AAPL"], RuntimeError)

    # Demo key warning test
    def test_demo_key_warning(self, tmp_path, caplog):
        """Test warning is logged when using demo key."""
        import logging
        caplog.set_level(logging.WARNING)
        AlphaVantageProvider(
            api_key="demo",
            cache_dir=str(tmp_path),
            warn_on_demo=True,
        )
        assert any("demo API key" in record.message for record in caplog.records)

    def test_no_demo_key_warning_when_disabled(self, tmp_path, caplog):
        """Test no warning when warn_on_demo is False."""
        import logging
        caplog.set_level(logging.WARNING)
        AlphaVantageProvider(
            api_key="demo",
            cache_dir=str(tmp_path),
            warn_on_demo=False,
        )
        assert not any("demo API key" in record.message for record in caplog.records)

    def test_no_demo_key_warning_with_real_key(self, tmp_path, caplog):
        """Test no warning when using a real API key."""
        import logging
        caplog.set_level(logging.WARNING)
        AlphaVantageProvider(
            api_key="real_key_123",
            cache_dir=str(tmp_path),
            warn_on_demo=True,
        )
        assert not any("demo API key" in record.message for record in caplog.records)

    def test_default_api_key_is_demo(self, tmp_path):
        """Test default API key is demo when None provided."""
        provider = AlphaVantageProvider(cache_dir=str(tmp_path), warn_on_demo=False)
        assert provider._api_key == "demo"

    # Symbol Search tests
    def test_search_symbols(self, provider):
        """Test searching symbols (SYMBOL_SEARCH endpoint)."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(SYMBOL_SEARCH_RESPONSE)

            results = provider.search_symbols("Apple")

            assert len(results) == 2
            assert results[0]["symbol"] == "AAPL"
            assert results[0]["name"] == "Apple Inc."
            assert results[0]["type"] == "Equity"
            assert results[0]["region"] == "United States"
            assert results[0]["market"] == "NASDAQ"
            assert results[0]["currency"] == "USD"
            assert results[0]["match_score"] == "1.0000"
            assert results[1]["symbol"] == "AAPL"
            assert results[1]["match_score"] == "0.8500"
            mock_get.assert_called_once()

    def test_search_symbols_empty_response(self, provider):
        """Test searching symbols with empty response."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(SYMBOL_SEARCH_EMPTY_RESPONSE)

            results = provider.search_symbols("NONEXISTENT")

            assert results == []
            mock_get.assert_called_once()

    def test_search_symbols_api_error(self, provider):
        """Test handling of API error for symbol search."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(ERROR_RESPONSE)

            results = provider.search_symbols("Apple")

            assert results == []
            mock_get.assert_called_once()

    def test_search_symbols_rate_limit(self, provider):
        """Test handling of rate limit for symbol search."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            mock_get.return_value = FakeResponse(RATE_LIMIT_RESPONSE)

            results = provider.search_symbols("Apple")

            assert results == []
            mock_get.assert_called_once()

    def test_search_symbols_network_error(self, provider):
        """Test handling of network errors for symbol search."""
        with patch("quant_trading.data.yfinance_provider.requests.get") as mock_get:
            import requests
            mock_get.side_effect = requests.ConnectionError("Network unreachable")

            results = provider.search_symbols("Apple")

            assert results == []
            mock_get.assert_called_once()

    def test_build_symbol_search_params(self, provider):
        """Test _build_symbol_search_params method."""
        params = provider._build_symbol_search_params("Apple")
        assert params["function"] == "SYMBOL_SEARCH"
        assert params["keywords"] == "Apple"
        assert params["apikey"] == "test_key"
        assert params["datatype"] == "json"

    def test_parse_symbol_search_response(self, provider):
        """Test _parse_symbol_search_response method."""
        results = provider._parse_symbol_search_response(SYMBOL_SEARCH_RESPONSE)

        assert len(results) == 2
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["name"] == "Apple Inc."
        assert results[0]["type"] == "Equity"
        assert results[0]["region"] == "United States"
        assert results[0]["market"] == "NASDAQ"
        assert results[0]["currency"] == "USD"
        assert results[0]["match_score"] == "1.0000"
        assert results[1]["symbol"] == "AAPL"
        assert results[1]["match_score"] == "0.8500"

    def test_parse_symbol_search_response_empty(self, provider):
        """Test _parse_symbol_search_response with empty response."""
        results = provider._parse_symbol_search_response(SYMBOL_SEARCH_EMPTY_RESPONSE)
        assert results == []

    def test_parse_symbol_search_response_missing_key(self, provider):
        """Test _parse_symbol_search_response with missing bestMatches key."""
        results = provider._parse_symbol_search_response({})
        assert results == []


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