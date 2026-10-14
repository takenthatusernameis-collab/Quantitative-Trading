"""Yahoo Finance and Alpha Vantage data provider implementations."""

import os
import pickle
from datetime import datetime, timedelta
from typing import Any, ClassVar, cast

import pandas as pd
import requests

from quant_trading.utils.logging import get_logger

from .providers import DataProvider, FetchResult, MarketData

logger = get_logger(__name__)


class YFinanceProvider(DataProvider):
    """Yahoo Finance data provider using yfinance library."""

    def __init__(
        self,
        cache_dir: str = "./data/cache",
        cache_ttl_hours: float = 24.0,
    ):
        self._cache_dir = cache_dir
        self._cache_ttl = timedelta(hours=cache_ttl_hours)
        self._yf = None
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return "yfinance"

    def _get_yf(self):
        """Lazy import yfinance."""
        if self._yf is None:
            try:
                import yfinance as yf  # type: ignore[import-untyped]

                self._yf = yf
            except ImportError:
                raise ImportError("yfinance is not installed. Install with: pip install yfinance")
        return self._yf

    def _cache_key(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> str:
        """Generate a deterministic cache key."""
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{self.name}_{symbols_str}_{start_str}_{end_str}_{interval}.pkl"

    def _cache_path(self, key: str) -> str:
        """Get full cache file path."""
        return os.path.join(self._cache_dir, key)

    def _is_cache_valid(self, path: str) -> bool:
        """Check if cache file exists and is not expired."""
        if not os.path.exists(path):
            return False
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        return datetime.now() - mtime < self._cache_ttl

    def _load_cache(self, path: str) -> FetchResult | None:
        """Load FetchResult from cache file."""
        try:
            with open(path, "rb") as f:
                result = pickle.load(f)
                if isinstance(result, FetchResult):
                    return result
                logger.warning("Cache file %s contains invalid data type", path)
                return None
        except (pickle.PickleError, EOFError, OSError) as e:
            logger.warning("Failed to load cache from %s: %s", path, e)
            return None

    def _save_cache(self, path: str, result: FetchResult) -> None:
        """Save FetchResult to cache file."""
        try:
            with open(path, "wb") as f:
                pickle.dump(result, f)
        except (pickle.PickleError, OSError) as e:
            logger.warning("Failed to save cache to %s: %s", path, e)

    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        """Fetch market data from Yahoo Finance.

        Returns a FetchResult with data, errors, and missing symbols.
        Missing symbols (no data returned) are tracked separately from errors.
        Uses disk caching if cache_dir is configured.
        """
        # Try cache first
        if self._cache_dir:
            key = self._cache_key(symbols, start, end, interval)
            path = self._cache_path(key)
            if self._is_cache_valid(path):
                cached = self._load_cache(path)
                if cached is not None:
                    logger.debug("Cache hit for %s", key)
                    return cached

        yf = self._get_yf()
        fetch_result = FetchResult()

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start, end=end, interval=interval)

                if hist.empty:
                    logger.warning("No data found for %s", symbol)
                    fetch_result.missing.append(symbol)
                    continue

                # Standardize column names
                hist.columns = [col.lower().replace(" ", "_") for col in hist.columns]

                metadata = {
                    "info": ticker.info,
                    "currency": ticker.info.get("currency", "USD"),
                    "exchange": ticker.info.get("exchange", "UNKNOWN"),
                }

                fetch_result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=hist,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (
                ValueError,
                RuntimeError,
                KeyError,
                ImportError,
                OSError,
                ConnectionError,
                TimeoutError,
            ) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                fetch_result.errors[symbol] = e

        # Save to cache
        if self._cache_dir:
            key = self._cache_key(symbols, start, end, interval)
            path = self._cache_path(key)
            self._save_cache(path, fetch_result)
            logger.debug("Cached result for %s", key)

        return fetch_result

    def fetch_many(
        self,
        requests: list[dict[str, Any]],
    ) -> dict[str, FetchResult]:
        """Fetch multiple requests using batched multi-ticker downloads.

        Requests sharing the same (start, end, interval) are grouped and
        served by a single ``yfinance.download`` call (``group_by="ticker"``),
        issuing one HTTP request for the group's symbols instead of N
        per-symbol requests. Each request's result is keyed by
        ``_request_key`` and the group result is cached on disk separately
        from per-symbol ``fetch`` calls.
        """
        yf = self._get_yf()
        results: dict[str, FetchResult] = {}

        groups: dict[tuple[datetime | None, datetime | None, str], dict[str, list]] = {}
        order: list[tuple[datetime | None, datetime | None, str]] = []
        for req in requests:
            symbols = req.get("symbols", [])
            start = req.get("start")
            end = req.get("end")
            interval = req.get("interval", "1d")
            range_key = (start, end, interval)
            bucket = groups.get(range_key)
            if bucket is None:
                bucket = {"symbols": [], "reqs": []}
                groups[range_key] = bucket
                order.append(range_key)
            bucket["symbols"].extend(symbols)
            bucket["reqs"].append((symbols, start, end, interval))

        for range_key in order:
            start, end, interval = range_key
            symbols = sorted(set(groups[range_key]["symbols"]))
            group_result = self._fetch_group(yf, symbols, start, end, interval)
            for req_symbols, r_start, r_end, r_interval in groups[range_key]["reqs"]:
                key = self._request_key(req_symbols, r_start, r_end, r_interval)
                results[key] = self._slice_group_result(group_result, req_symbols)

        return results

    def _fetch_group(
        self,
        yf: Any,
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        interval: str,
    ) -> FetchResult:
        """Fetch all symbols for one date range with a single download call."""
        if self._cache_dir:
            key = self._group_cache_key(symbols, start, end, interval)
            path = self._cache_path(key)
            if self._is_cache_valid(path):
                cached = self._load_cache(path)
                if cached is not None:
                    logger.debug("Cache hit for %s", key)
                    return cached

        result = FetchResult()
        if symbols:
            df = yf.download(
                tickers=symbols,
                start=start,
                end=end,
                interval=interval,
                group_by="ticker",
                progress=False,
            )
            result = self._parse_download(df, symbols)

        if self._cache_dir and (result.data or result.errors):
            key = self._group_cache_key(symbols, start, end, interval)
            self._save_cache(self._cache_path(key), result)
            logger.debug("Cached group result for %s", key)

        return result

    def _parse_download(
        self,
        df: pd.DataFrame | None,
        symbols: list[str],
    ) -> FetchResult:
        """Convert a yfinance.download (group_by='ticker') result to a FetchResult."""
        result = FetchResult()
        if df is None or df.empty:
            result.missing.extend(symbols)
            return result

        columns = df.columns
        if isinstance(columns, pd.MultiIndex):
            tickers = columns.get_level_values(0)
            for symbol in symbols:
                if symbol not in tickers:
                    result.missing.append(symbol)
                    continue
                hist = df[symbol].copy()
                hist.columns = [str(col).lower().replace(" ", "_") for col in hist.columns]
                hist = hist.dropna(how="all")
                if hist.empty:
                    result.missing.append(symbol)
                    continue
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=hist,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata={},
                )
        else:
            hist = df.copy()
            hist.columns = [str(col).lower().replace(" ", "_") for col in hist.columns]
            hist = hist.dropna(how="all")
            if not hist.empty:
                symbol = symbols[0]
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=hist,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata={},
                )
            else:
                result.missing.extend(symbols)
        return result

    def _group_cache_key(
        self,
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        interval: str,
    ) -> str:
        """Cache filename for a batched group download (distinct from per-symbol)."""
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{self.name}_group_{symbols_str}_{start_str}_{end_str}_{interval}.pkl"

    def _slice_group_result(
        self,
        group_result: FetchResult,
        symbols: list[str],
    ) -> FetchResult:
        """Pick only the requested symbols out of a group FetchResult."""
        sliced = FetchResult()
        for symbol in symbols:
            if symbol in group_result.data:
                sliced.data[symbol] = group_result.data[symbol]
            elif symbol in group_result.errors:
                sliced.errors[symbol] = group_result.errors[symbol]
            else:
                sliced.missing.append(symbol)
        return sliced

    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        """Fetch latest market data (last 1 day)."""
        end = datetime.now()
        start = end - timedelta(days=2)
        return self.fetch(symbols, start=start, end=end, interval="1m")


class AlphaVantageProvider(DataProvider):
    """Alpha Vantage data provider using REST API.

    Supports:
    - TIME_SERIES_DAILY_ADJUSTED for daily historical data
    - TIME_SERIES_WEEKLY for weekly historical data
    - TIME_SERIES_WEEKLY_ADJUSTED for weekly adjusted historical data
    - TIME_SERIES_MONTHLY for monthly historical data
    - TIME_SERIES_MONTHLY_ADJUSTED for monthly adjusted historical data
    - TIME_SERIES_INTRADAY for intraday historical data (1min, 5min, 15min, 30min, 60min)
    - GLOBAL_QUOTE for real-time single symbol quotes
    - BATCH_STOCK_PRICES for real-time batch quotes
    - SYMBOL_SEARCH for symbol lookup by name or ticker

    Alpha Vantage provides a free demo key ("demo") for testing.
    """

    BASE_URL = "https://www.alphavantage.co/query"

    INTRADAY_INTERVALS: ClassVar[dict[str, str]] = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "60min",
        "60m": "60min",
    }

    WEEKLY_INTERVALS: ClassVar[set[str]] = {"1w", "weekly", "week"}
    MONTHLY_INTERVALS: ClassVar[set[str]] = {"1mo", "monthly", "month"}
    QUOTE_INTERVALS: ClassVar[set[str]] = {"quote", "realtime", "rt"}
    MARKET_STATUS_INTERVALS: ClassVar[set[str]] = {"market_status", "marketstatus"}
    FX_DAILY_INTERVALS: ClassVar[set[str]] = {"fx_daily", "fx", "forex_daily"}
    FX_INTRADAY_INTERVALS: ClassVar[set[str]] = {
        "fx_intraday",
        "fx_1m",
        "fx_5m",
        "fx_15m",
        "fx_30m",
        "fx_60m",
    }
    CRYPTO_INTERVALS: ClassVar[set[str]] = {
        "crypto_daily",
        "crypto_weekly",
        "crypto_monthly",
        "crypto_intraday",
    }
    DIGITAL_CURRENCY_INTERVALS: ClassVar[set[str]] = {
        "digital_daily",
        "digital_weekly",
        "digital_monthly",
        "digital_intraday",
    }
    CURRENCY_EXCHANGE_RATE_INTERVALS: ClassVar[set[str]] = {
        "fx_rate",
        "currency_exchange_rate",
        "forex_rate",
    }
    SYMBOL_SEARCH_INTERVALS: ClassVar[set[str]] = {
        "symbol_search",
        "search_symbols",
        "symbol_lookup",
    }
    TECHNICAL_INDICATORS: ClassVar[set[str]] = {
        "sma",
        "ema",
        "rsi",
        "macd",
        "stoch",
        "bbands",
        "adx",
        "cci",
        "roc",
        "willr",
        "mom",
        "trix",
        "obv",
        "ad",
        "adxr",
        "aroondown",
        "aroonup",
        "atr",
        "mfi",
        "ultosc",
        "vwap",
        "plus_di",
        "minus_di",
        "plus_dm",
        "minus_dm",
        "stochf",
        "stochrsi",
        "dx",
        "slowk",
        "slowd",
        "fastk",
        "fastd",
    }
    SECTOR_INTERVALS: ClassVar[set[str]] = {"sector", "sector_performance", "sectors"}
    COMMODITIES_INTERVALS: ClassVar[set[str]] = {
        "wti",
        "brent",
        "natural_gas",
        "copper",
        "aluminum",
        "corn",
        "wheat",
        "cotton",
        "sugar",
        "coffee",
        "all_commodities",
    }
    GOLD_INTERVALS: ClassVar[set[str]] = {"gold", "silver"}
    COMMODITY_FUNCTION_MAP: ClassVar[dict[str, str]] = {
        "wti": "WTI",
        "brent": "BRENT",
        "natural_gas": "NATURAL_GAS",
        "copper": "COPPER",
        "aluminum": "ALUMINUM",
        "corn": "CORN",
        "wheat": "WHEAT",
        "cotton": "COTTON",
        "sugar": "SUGAR",
        "coffee": "COFFEE",
        "all_commodities": "ALL_COMMODITIES",
    }
    ECONOMIC_INDICATORS: ClassVar[set[str]] = {
        "gdp",
        "real_gdp",
        "gdp_per_capita",
        "cpi",
        "inflation",
        "retail_sales",
        "durables",
        "unemployment",
        "nonfarm_payroll",
        "interest_rate",
        "fed_funds_rate",
        "treasury_yield",
        "consumer_sentiment",
    }
    ECONOMIC_FUNCTION_MAP: ClassVar[dict[str, str]] = {
        "gdp": "REAL_GDP",
        "real_gdp": "REAL_GDP",
        "gdp_per_capita": "REAL_GDP_PER_CAPITA",
        "cpi": "CPI",
        "inflation": "INFLATION",
        "retail_sales": "RETAIL_SALES",
        "durables": "DURABLES",
        "unemployment": "UNEMPLOYMENT",
        "nonfarm_payroll": "NONFARM_PAYROLL",
        "interest_rate": "FEDERAL_FUNDS_RATE",
        "fed_funds_rate": "FEDERAL_FUNDS_RATE",
        "treasury_yield": "TREASURY_YIELD",
        "consumer_sentiment": "CONSUMER_SENTIMENT",
    }

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str = "./data/cache",
        cache_ttl_hours: float = 24.0,
        timeout: float = 30.0,
        warn_on_demo: bool = True,
    ):
        self._api_key = api_key or "demo"
        self._cache_dir = cache_dir
        self._cache_ttl = timedelta(hours=cache_ttl_hours)
        self._timeout = timeout
        self._warn_on_demo = warn_on_demo
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        if self._warn_on_demo and self._api_key == "demo":
            logger.warning(
                "Using Alpha Vantage demo API key. "
                "This key is rate limited (5 calls/min, 500 calls/day). "
                "For production use, get a free API key from https://www.alphavantage.co/support/#api-key"
            )

    @property
    def name(self) -> str:
        return "alphavantage"

    def _cache_key(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> str:
        """Generate a deterministic cache key."""
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{self.name}_{symbols_str}_{start_str}_{end_str}_{interval}.pkl"

    def _cache_path(self, key: str) -> str:
        """Get full cache file path."""
        return os.path.join(self._cache_dir, key)

    def _is_cache_valid(self, path: str) -> bool:
        """Check if cache file exists and is not expired."""
        if not os.path.exists(path):
            return False
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        return datetime.now() - mtime < self._cache_ttl

    def _load_cache(self, path: str) -> FetchResult | None:
        """Load FetchResult from cache file."""
        try:
            with open(path, "rb") as f:
                result = pickle.load(f)
                if isinstance(result, FetchResult):
                    return result
                logger.warning("Cache file %s contains invalid data type", path)
                return None
        except (pickle.PickleError, EOFError, OSError) as e:
            logger.warning("Failed to load cache from %s: %s", path, e)
            return None

    def _save_cache(self, path: str, result: FetchResult) -> None:
        """Save FetchResult to cache file."""
        try:
            with open(path, "wb") as f:
                pickle.dump(result, f)
        except (pickle.PickleError, OSError) as e:
            logger.warning("Failed to save cache to %s: %s", path, e)

    @staticmethod
    def _request_key(
        symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> str:
        """Build a stable string key for a fetch request."""
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{symbols_str}|{start_str}|{end_str}|{interval}"

    def _build_daily_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for TIME_SERIES_DAILY_ADJUSTED endpoint."""
        return {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "apikey": self._api_key,
            "outputsize": "full",
            "datatype": "json",
        }

    def _build_batch_params(self, symbols: list[str]) -> dict[str, str]:
        """Build parameters for BATCH_STOCK_PRICES endpoint."""
        return {
            "function": "BATCH_STOCK_PRICES",
            "symbols": ",".join(symbols),
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_intraday_params(self, symbol: str, interval: str) -> dict[str, str]:
        """Build parameters for TIME_SERIES_INTRADAY endpoint."""
        av_interval = self.INTRADAY_INTERVALS.get(interval, interval)
        return {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": av_interval,
            "apikey": self._api_key,
            "outputsize": "full",
            "datatype": "json",
        }

    def _build_weekly_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for TIME_SERIES_WEEKLY endpoint."""
        return {
            "function": "TIME_SERIES_WEEKLY",
            "symbol": symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_weekly_adjusted_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for TIME_SERIES_WEEKLY_ADJUSTED endpoint."""
        return {
            "function": "TIME_SERIES_WEEKLY_ADJUSTED",
            "symbol": symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_monthly_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for TIME_SERIES_MONTHLY endpoint."""
        return {
            "function": "TIME_SERIES_MONTHLY",
            "symbol": symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_monthly_adjusted_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for TIME_SERIES_MONTHLY_ADJUSTED endpoint."""
        return {
            "function": "TIME_SERIES_MONTHLY_ADJUSTED",
            "symbol": symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_global_quote_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for GLOBAL_QUOTE endpoint."""
        return {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_symbol_search_params(self, query: str) -> dict[str, str]:
        """Build parameters for SYMBOL_SEARCH endpoint."""
        return {
            "function": "SYMBOL_SEARCH",
            "keywords": query,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_market_status_params(self) -> dict[str, str]:
        """Build parameters for MARKET_STATUS endpoint."""
        return {
            "function": "MARKET_STATUS",
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_sector_params(self) -> dict[str, str]:
        """Build parameters for SECTOR_PERFORMANCE endpoint."""
        return {
            "function": "SECTOR",
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_gold_spot_params(self, symbol: str) -> dict[str, str]:
        """Build parameters for GOLD_SILVER_SPOT endpoint."""
        return {
            "function": "GOLD_SILVER_SPOT",
            "symbol": symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_gold_history_params(self, symbol: str, interval: str = "daily") -> dict[str, str]:
        """Build parameters for GOLD_SILVER_HISTORY endpoint."""
        return {
            "function": "GOLD_SILVER_HISTORY",
            "symbol": symbol,
            "interval": interval,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_commodity_params(self, function: str, interval: str = "monthly") -> dict[str, str]:
        """Build parameters for a commodity endpoint (WTI, BRENT, COPPER, etc.).

        The commodity functions accept an ``interval`` argument whose valid
        values depend on the commodity (daily/weekly/monthly for energy,
        monthly/quarterly/annual for metals and agriculture).
        """
        params: dict[str, str] = {
            "function": function,
            "apikey": self._api_key,
            "datatype": "json",
        }
        if interval:
            params["interval"] = interval
        return params

    def _build_economic_indicator_params(self, function: str, **kwargs) -> dict[str, str]:
        """Build parameters for an economic indicator endpoint.

        Most economic indicators accept only ``apikey``/``datatype``; a few
        (REAL_GDP, CPI, FEDERAL_FUNDS_RATE, TREASURY_YIELD) accept an
        ``interval`` and, for TREASURY_YIELD, a ``maturity``. Extra keyword
        arguments are forwarded verbatim.
        """
        params: dict[str, str] = {
            "function": function,
            "apikey": self._api_key,
            "datatype": "json",
        }
        for key, value in kwargs.items():
            if value is not None:
                params[key] = str(value)
        return params

    def _build_fx_daily_params(self, from_symbol: str, to_symbol: str) -> dict[str, str]:
        """Build parameters for FX_DAILY endpoint."""
        return {
            "function": "FX_DAILY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_fx_intraday_params(
        self, from_symbol: str, to_symbol: str, interval: str
    ) -> dict[str, str]:
        """Build parameters for FX_INTRADAY endpoint."""
        av_interval = self.INTRADAY_INTERVALS.get(interval.replace("fx_", ""), interval)
        return {
            "function": "FX_INTRADAY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "interval": av_interval,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_currency_exchange_rate_params(
        self, from_currency: str, to_currency: str
    ) -> dict[str, str]:
        """Build parameters for CURRENCY_EXCHANGE_RATE endpoint."""
        return {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_crypto_daily_params(self, symbol: str, market: str = "USD") -> dict[str, str]:
        """Build parameters for CRYPTO_DAILY endpoint (DIGITAL_CURRENCY_DAILY)."""
        return {
            "function": "DIGITAL_CURRENCY_DAILY",
            "symbol": symbol,
            "market": market,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_crypto_weekly_params(self, symbol: str, market: str = "USD") -> dict[str, str]:
        """Build parameters for CRYPTO_WEEKLY endpoint (DIGITAL_CURRENCY_WEEKLY)."""
        return {
            "function": "DIGITAL_CURRENCY_WEEKLY",
            "symbol": symbol,
            "market": market,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_crypto_monthly_params(self, symbol: str, market: str = "USD") -> dict[str, str]:
        """Build parameters for CRYPTO_MONTHLY endpoint (DIGITAL_CURRENCY_MONTHLY)."""
        return {
            "function": "DIGITAL_CURRENCY_MONTHLY",
            "symbol": symbol,
            "market": market,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_crypto_intraday_params(
        self, symbol: str, market: str = "USD", interval: str = "5min"
    ) -> dict[str, str]:
        """Build parameters for CRYPTO_INTRADAY endpoint (DIGITAL_CURRENCY_INTRADAY)."""
        return {
            "function": "DIGITAL_CURRENCY_INTRADAY",
            "symbol": symbol,
            "market": market,
            "interval": interval,
            "apikey": self._api_key,
            "datatype": "json",
        }

    def _build_technical_indicator_params(
        self,
        symbol: str,
        indicator: str = "SMA",
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
        **kwargs,
    ) -> dict[str, str]:
        """Build parameters for a technical indicator."""
        params = {
            "function": indicator.upper(),
            "symbol": symbol,
            "interval": interval,
            "time_period": str(time_period),
            "series_type": series_type,
            "apikey": self._api_key,
            "datatype": "json",
        }
        for k, v in kwargs.items():
            params[k] = str(v)
        return params

    def _parse_intraday_response(
        self, symbol: str, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse TIME_SERIES_INTRADAY response into DataFrame."""
        # Find the time series key (e.g., "Time Series (5min)")
        time_series_key = None
        for key in data:
            if key.startswith("Time Series"):
                time_series_key = key
                break

        if not time_series_key:
            return None

        time_series = data.get(time_series_key)
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(values.get("5. volume", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_daily_response(
        self, symbol: str, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse TIME_SERIES_DAILY_ADJUSTED response into DataFrame."""
        time_series = data.get("Time Series (Daily)")
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "adjusted_close": float(values.get("5. adjusted close", 0)),
                    "volume": int(values.get("6. volume", 0)),
                    "dividend_amount": float(values.get("7. dividend amount", 0)),
                    "split_coefficient": float(values.get("8. split coefficient", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        # mypy: column assignment returns Any, but we know it's DataFrame
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_batch_response(
        self, symbols: list[str], data: dict[str, Any]
    ) -> dict[str, pd.DataFrame]:
        """Parse BATCH_STOCK_PRICES response into per-symbol DataFrames."""
        result = {}
        stock_prices = data.get("Stock Prices", [])
        for item in stock_prices:
            symbol = item.get("1. symbol")
            if symbol in symbols:
                df = pd.DataFrame(
                    [
                        {
                            "date": datetime.now().date(),
                            "open": float(item.get("2. open", 0)),
                            "high": float(item.get("3. high", 0)),
                            "low": float(item.get("4. low", 0)),
                            "price": float(item.get("5. price", 0)),
                            "volume": int(item.get("6. volume", 0)),
                        }
                    ]
                )
                df = df.set_index("date")
                df.columns = [col.lower().replace(" ", "_") for col in df.columns]
                result[symbol] = df
        return result

    def _parse_weekly_response(
        self, symbol: str, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse TIME_SERIES_WEEKLY response into DataFrame."""
        time_series = data.get("Weekly Time Series")
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(values.get("5. volume", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_weekly_adjusted_response(
        self, symbol: str, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse TIME_SERIES_WEEKLY_ADJUSTED response into DataFrame."""
        time_series = data.get("Weekly Adjusted Time Series")
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "adjusted_close": float(values.get("5. adjusted close", 0)),
                    "volume": int(values.get("6. volume", 0)),
                    "dividend_amount": float(values.get("7. dividend amount", 0)),
                    "split_coefficient": float(values.get("8. split coefficient", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_monthly_response(
        self, symbol: str, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse TIME_SERIES_MONTHLY response into DataFrame."""
        time_series = data.get("Monthly Time Series")
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(values.get("5. volume", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_monthly_adjusted_response(
        self, symbol: str, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse TIME_SERIES_MONTHLY_ADJUSTED response into DataFrame."""
        time_series = data.get("Monthly Adjusted Time Series")
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "adjusted_close": float(values.get("5. adjusted close", 0)),
                    "volume": int(values.get("6. volume", 0)),
                    "dividend_amount": float(values.get("7. dividend amount", 0)),
                    "split_coefficient": float(values.get("8. split coefficient", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_global_quote_response(
        self, symbol: str, data: dict[str, Any]
    ) -> pd.DataFrame | None:
        """Parse GLOBAL_QUOTE response into DataFrame."""
        quote = data.get("Global Quote")
        if not quote:
            return None

        # GLOBAL_QUOTE returns a single data point with current price info
        df = pd.DataFrame(
            [
                {
                    "date": datetime.now().date(),
                    "open": float(quote.get("02. open", 0)),
                    "high": float(quote.get("03. high", 0)),
                    "low": float(quote.get("04. low", 0)),
                    "price": float(quote.get("05. price", 0)),
                    "volume": int(quote.get("06. volume", 0)),
                    "latest_trading_day": quote.get("07. latest trading day", ""),
                    "previous_close": float(quote.get("08. previous close", 0)),
                    "change": float(quote.get("09. change", 0)),
                    "change_percent": quote.get("10. change percent", "0%"),
                }
            ]
        )
        df = df.set_index("date")
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]
        return cast(pd.DataFrame, df)

    def _parse_symbol_search_response(self, data: dict[str, Any]) -> list[dict[str, str]]:
        """Parse SYMBOL_SEARCH response into a list of symbol matches.

        Each match is a dict with keys: symbol, name, type, region, market,
        currency, match_score.
        """
        best_matches = data.get("bestMatches", [])
        results: list[dict[str, str]] = []
        for item in best_matches:
            results.append(
                {
                    "symbol": item.get("1. symbol", ""),
                    "name": item.get("2. name", ""),
                    "type": item.get("3. type", ""),
                    "region": item.get("4. region", ""),
                    "market": item.get("5. market", ""),
                    "currency": item.get("6. currency", ""),
                    "match_score": item.get("7. matchScore", ""),
                }
            )
        return results

    def _parse_technical_indicator_response(
        self,
        symbol: str,
        indicator: str,
        data: dict[str, Any],
        start: datetime | None,
        end: datetime | None,
    ) -> pd.DataFrame | None:
        """Parse technical indicator response into DataFrame."""
        # Look for key like "Technical Analysis: SMA"
        ta_key = None
        for key in data:
            if "Technical Analysis" in key:
                ta_key = key
                break
        if not ta_key:
            return None

        ta_data = data.get(ta_key)
        if not ta_data:
            return None

        indicator_key = None
        for key in ta_data:
            if key.upper() == indicator.upper() or key == indicator:
                indicator_key = key
                break
        if not indicator_key:
            return None

        series = ta_data.get(indicator_key)
        if not series:
            return None

        records = []
        date_format = "%Y-%m-%d"
        for date_str, values in series.items():
            try:
                date = datetime.strptime(date_str, date_format)
            except ValueError:
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
            if start and date < start:
                continue
            if end and date > end:
                continue
            # Take first value
            value_key = next(iter(values.keys())) if values else None
            if value_key is not None:
                records.append({"date": date, indicator.lower(): float(values[value_key])})

        if not records:
            return None
        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        return cast(pd.DataFrame, df)

    def _parse_market_status_response(self, data: dict[str, Any]) -> pd.DataFrame | None:
        """Parse MARKET_STATUS response into DataFrame.

        Returns a DataFrame with market status information for various regions/markets.
        """
        markets = data.get("markets", [])
        if not markets:
            return None

        records = []
        for market in markets:
            records.append(
                {
                    "market_type": market.get("market_type", ""),
                    "region": market.get("region", ""),
                    "market": market.get("market", ""),
                    "primary_exchanges": market.get("primary_exchanges", ""),
                    "local_open": market.get("local_open", ""),
                    "local_close": market.get("local_close", ""),
                    "current_status": market.get("current_status", ""),
                    "notes": market.get("notes", ""),
                }
            )

        df = pd.DataFrame(records)
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]
        return cast(pd.DataFrame, df)

    def _parse_fx_daily_response(
        self,
        from_symbol: str,
        to_symbol: str,
        data: dict[str, Any],
        start: datetime | None,
        end: datetime | None,
    ) -> pd.DataFrame | None:
        """Parse FX_DAILY response into DataFrame."""
        time_series = data.get("Time Series FX (Daily)")
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_fx_intraday_response(
        self,
        from_symbol: str,
        to_symbol: str,
        data: dict[str, Any],
        start: datetime | None,
        end: datetime | None,
    ) -> pd.DataFrame | None:
        """Parse FX_INTRADAY response into DataFrame."""
        time_series_key = None
        for key in data:
            if key.startswith("Time Series FX"):
                time_series_key = key
                break

        if not time_series_key:
            return None

        time_series = data.get(time_series_key)
        if not time_series:
            return None

        records = []
        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            records.append(
                {
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                }
            )

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_currency_exchange_rate_response(
        self, from_currency: str, to_currency: str, data: dict[str, Any]
    ) -> pd.DataFrame | None:
        """Parse CURRENCY_EXCHANGE_RATE response into DataFrame."""
        rate = data.get("Realtime Currency Exchange Rate")
        if not rate:
            return None

        df = pd.DataFrame(
            [
                {
                    "date": datetime.now().date(),
                    "from_currency_code": rate.get("1. From_Currency Code", from_currency),
                    "from_currency_name": rate.get("2. From_Currency Name", ""),
                    "to_currency_code": rate.get("3. To_Currency Code", to_currency),
                    "to_currency_name": rate.get("4. To_Currency Name", ""),
                    "exchange_rate": float(rate.get("5. Exchange Rate", 0)),
                    "last_refreshed": rate.get("6. Last Refreshed", ""),
                    "time_zone": rate.get("7. Time Zone", ""),
                    "bid_price": float(rate.get("8. Bid Price", 0)),
                    "ask_price": float(rate.get("9. Ask Price", 0)),
                }
            ]
        )
        df = df.set_index("date")
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]
        return cast(pd.DataFrame, df)

    def _parse_crypto_response(
        self,
        symbol: str,
        market: str,
        data: dict[str, Any],
        start: datetime | None,
        end: datetime | None,
    ) -> pd.DataFrame | None:
        """Parse DIGITAL_CURRENCY_DAILY/WEEKLY/MONTHLY/INTRADAY response into DataFrame."""
        # Find the time series key
        time_series_key = None
        for key in data:
            if "Time Series" in key and "Digital" in key:
                time_series_key = key
                break

        if not time_series_key:
            return None

        time_series = data.get(time_series_key)
        if not time_series:
            return None

        records = []
        date_format = "%Y-%m-%d"
        if "Intraday" in time_series_key:
            date_format = "%Y-%m-%d %H:%M:%S"

        for date_str, values in time_series.items():
            try:
                date = datetime.strptime(date_str, date_format)
            except ValueError:
                continue

            if start and date < start:
                continue
            if end and date > end:
                continue

            # Digital currency responses have both regular and market-specific values
            # Use the market-specific values (e.g., "1a. open (USD)")
            open_key = f"1a. open ({market})"
            high_key = f"2a. high ({market})"
            low_key = f"3a. low ({market})"
            close_key = f"4a. close ({market})"
            volume_key = "5. volume"

            record = {
                "date": date,
                "open": float(values.get(open_key, values.get("1. open", 0))),
                "high": float(values.get(high_key, values.get("2. high", 0))),
                "low": float(values.get(low_key, values.get("3. low", 0))),
                "close": float(values.get(close_key, values.get("4. close", 0))),
                "volume": float(values.get(volume_key, 0)),
            }
            records.append(record)

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        new_cols = [col.lower().replace(" ", "_") for col in df.columns]
        df.columns = new_cols
        return cast(pd.DataFrame, df)

    def _parse_single_series_response(
        self, data: dict[str, Any], start: datetime | None, end: datetime | None
    ) -> pd.DataFrame | None:
        """Parse the commodity/economic indicator response envelope.

        These endpoints return::

            {"name": "...", "interval": "...", "unit": "...",
             "data": [{"date": "YYYY-MM-DD", "value": "123.4"}, ...]}

        Returns a DataFrame indexed by date with a single ``value`` column,
        or None when no series is present.
        """
        series = data.get("data")
        if not series:
            return None

        records = []
        for item in series:
            date_str = item.get("date")
            if not date_str:
                continue
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
            if start and date < start:
                continue
            if end and date > end:
                continue
            value = item.get("value")
            if value is None or value == ".":
                continue
            try:
                records.append({"date": date, "value": float(value)})
            except (TypeError, ValueError):
                continue

        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        return cast(pd.DataFrame, df)

    def _parse_sector_performance_response(self, data: dict[str, Any]) -> pd.DataFrame | None:
        """Parse SECTOR_PERFORMANCE (function=SECTOR) response into DataFrame.

        The response is a mapping of rank keys (e.g. "Rank A: Real-Time
        Performance") to a dict of ``sector -> performance``. The returned
        DataFrame has columns ``sector``, ``period``, ``performance``.
        """
        if not data:
            return None

        rank_keys = [k for k in data if k.startswith("Rank ")]
        if not rank_keys:
            return None

        records = []
        for key in rank_keys:
            # "Rank A: Real-Time Performance" -> "A: Real-Time"
            period = key.replace("Rank ", "").replace(" Performance", "")
            sectors = data.get(key)
            if not isinstance(sectors, dict):
                continue
            for sector, perf in sectors.items():
                try:
                    records.append({"sector": sector, "period": period, "performance": float(perf)})
                except (TypeError, ValueError):
                    continue

        if not records:
            return None

        df = pd.DataFrame(records)
        return cast(pd.DataFrame, df)

    def _fetch_single(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using TIME_SERIES_DAILY_ADJUSTED per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_daily_params(symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_daily_response(symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "TIME_SERIES_DAILY_ADJUSTED", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_batch(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using BATCH_STOCK_PRICES endpoint (real-time quotes only)."""
        result = FetchResult()
        try:
            params = self._build_batch_params(symbols)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                raise ValueError(f"API error: {data['Error Message']}")
            if "Note" in data:
                raise RuntimeError(f"API rate limit: {data['Note']}")

            parsed = self._parse_batch_response(symbols, data)
            for symbol in symbols:
                df = parsed.get(symbol)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue
                metadata = {"function": "BATCH_STOCK_PRICES", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Batch fetch error: %s", e)
            for symbol in symbols:
                if symbol not in result.data:
                    result.errors[symbol] = e
        return result

    def _fetch_intraday(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using TIME_SERIES_INTRADAY endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_intraday_params(symbol, interval)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_intraday_response(symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                av_interval = self.INTRADAY_INTERVALS.get(interval, interval)
                metadata = {"function": "TIME_SERIES_INTRADAY", "interval": av_interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_weekly(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using TIME_SERIES_WEEKLY endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_weekly_params(symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_weekly_response(symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "TIME_SERIES_WEEKLY", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_weekly_adjusted(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using TIME_SERIES_WEEKLY_ADJUSTED endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_weekly_adjusted_params(symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_weekly_adjusted_response(symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "TIME_SERIES_WEEKLY_ADJUSTED", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_monthly(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using TIME_SERIES_MONTHLY endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_monthly_params(symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_monthly_response(symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "TIME_SERIES_MONTHLY", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_monthly_adjusted(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using TIME_SERIES_MONTHLY_ADJUSTED endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_monthly_adjusted_params(symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_monthly_adjusted_response(symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_global_quote(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using GLOBAL_QUOTE endpoint per symbol (real-time single quote)."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_global_quote_params(symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_global_quote_response(symbol, data)
                if df is None or df.empty:
                    logger.warning("No data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "GLOBAL_QUOTE", "interval": interval}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def search_symbols(self, query: str) -> list[dict[str, str]]:
        """Search for symbols matching a query using SYMBOL_SEARCH endpoint.

        Args:
            query: Search query (company name or ticker symbol fragment).

        Returns:
            List of matching symbols, each a dict with keys:
            symbol, name, type, region, market, currency, match_score.
            Sorted by match score (best first). Empty list on error.
        """
        try:
            params = self._build_symbol_search_params(query)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("SYMBOL_SEARCH API error: %s", data["Error Message"])
                return []
            if "Note" in data:
                logger.error("SYMBOL_SEARCH rate limit: %s", data["Note"])
                return []

            matches = self._parse_symbol_search_response(data)
            logger.debug("SYMBOL_SEARCH for %r returned %d matches", query, len(matches))
            return matches
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error searching symbols for %r: %s", query, e)
            return []

    def get_market_status(self) -> pd.DataFrame | None:
        """Get current market status for various regions/markets using MARKET_STATUS endpoint.

        Returns:
            DataFrame with market status information, or None on error.
        """
        try:
            params = self._build_market_status_params()
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("MARKET_STATUS API error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.error("MARKET_STATUS rate limit: %s", data["Note"])
                return None

            df = self._parse_market_status_response(data)
            logger.debug("MARKET_STATUS returned %d markets", len(df) if df is not None else 0)
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching market status: %s", e)
            return None

    def get_currency_exchange_rate(
        self, from_currency: str, to_currency: str
    ) -> pd.DataFrame | None:
        """Get real-time currency exchange rate using CURRENCY_EXCHANGE_RATE endpoint.

        Args:
            from_currency: The currency code to convert from (e.g., 'USD').
            to_currency: The currency code to convert to (e.g., 'JPY').

        Returns:
            DataFrame with exchange rate information, or None on error.
        """
        try:
            params = self._build_currency_exchange_rate_params(from_currency, to_currency)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("CURRENCY_EXCHANGE_RATE API error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.error("CURRENCY_EXCHANGE_RATE rate limit: %s", data["Note"])
                return None

            df = self._parse_currency_exchange_rate_response(from_currency, to_currency, data)
            logger.debug(
                "CURRENCY_EXCHANGE_RATE %s/%s: %s",
                from_currency,
                to_currency,
                "success" if df is not None else "failed",
            )
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching currency exchange rate: %s", e)
            return None

    def get_technical_indicator(
        self,
        symbol: str,
        indicator: str = "SMA",
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
        **kwargs,
    ) -> pd.DataFrame | None:
        try:
            params = self._build_technical_indicator_params(
                symbol,
                indicator=indicator,
                interval=interval,
                time_period=time_period,
                series_type=series_type,
                **kwargs,
            )
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            if "Error Message" in data:
                logger.error("TECHNICAL_INDICATOR API error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.error("TECHNICAL_INDICATOR rate limit: %s", data["Note"])
                return None
            df = self._parse_technical_indicator_response(symbol, indicator, data, None, None)
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching technical indicator: %s", e)
            return None

    def get_sma(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
    ) -> pd.DataFrame | None:
        return self.get_technical_indicator(
            symbol,
            indicator="SMA",
            interval=interval,
            time_period=time_period,
            series_type=series_type,
        )

    def get_ema(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
    ) -> pd.DataFrame | None:
        return self.get_technical_indicator(
            symbol,
            indicator="EMA",
            interval=interval,
            time_period=time_period,
            series_type=series_type,
        )

    def get_rsi(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 14,
        series_type: str = "close",
    ) -> pd.DataFrame | None:
        return self.get_technical_indicator(
            symbol,
            indicator="RSI",
            interval=interval,
            time_period=time_period,
            series_type=series_type,
        )

    def get_macd(
        self, symbol: str, interval: str = "daily", series_type: str = "close"
    ) -> pd.DataFrame | None:
        return self.get_technical_indicator(
            symbol, indicator="MACD", interval=interval, series_type=series_type
        )

    def get_stoch(self, symbol: str, interval: str = "daily") -> pd.DataFrame | None:
        return self.get_technical_indicator(symbol, indicator="STOCH", interval=interval)

    def get_bbands(
        self,
        symbol: str,
        interval: str = "daily",
        time_period: int = 20,
        series_type: str = "close",
    ) -> pd.DataFrame | None:
        return self.get_technical_indicator(
            symbol,
            indicator="BBANDS",
            interval=interval,
            time_period=time_period,
            series_type=series_type,
        )

    def get_sector_performance(self) -> pd.DataFrame | None:
        """Get sector performance rankings using the SECTOR endpoint.

        Returns:
            DataFrame with columns ``sector``, ``period``, ``performance``,
            or None on error.
        """
        try:
            params = self._build_sector_params()
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("SECTOR API error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.error("SECTOR rate limit: %s", data["Note"])
                return None

            df = self._parse_sector_performance_response(data)
            logger.debug("SECTOR returned %d sector/period rows", len(df) if df is not None else 0)
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching sector performance: %s", e)
            return None

    def get_gold_spot(self, symbol: str = "GOLD") -> pd.DataFrame | None:
        """Get live gold/silver spot price using GOLD_SILVER_SPOT endpoint.

        Args:
            symbol: "GOLD" or "XAU" for gold, "SILVER" or "XAG" for silver.

        Returns:
            DataFrame with a single row of spot price data, or None on error.
        """
        try:
            params = self._build_gold_spot_params(symbol)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("GOLD_SILVER_SPOT API error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.error("GOLD_SILVER_SPOT rate limit: %s", data["Note"])
                return None

            df = self._parse_single_series_response(data, None, None)
            logger.debug(
                "GOLD_SILVER_SPOT %s: %s", symbol, "success" if df is not None else "failed"
            )
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching gold/silver spot: %s", e)
            return None

    def get_gold_history(
        self, symbol: str = "GOLD", interval: str = "daily"
    ) -> pd.DataFrame | None:
        """Get historical gold/silver prices using GOLD_SILVER_HISTORY endpoint.

        Args:
            symbol: "GOLD" or "XAU" for gold, "SILVER" or "XAG" for silver.
            interval: "daily", "weekly", or "monthly".

        Returns:
            DataFrame indexed by date with a ``value`` column, or None on error.
        """
        try:
            params = self._build_gold_history_params(symbol, interval=interval)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("GOLD_SILVER_HISTORY API error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.error("GOLD_SILVER_HISTORY rate limit: %s", data["Note"])
                return None

            df = self._parse_single_series_response(data, None, None)
            logger.debug(
                "GOLD_SILVER_HISTORY %s/%s: %s",
                symbol,
                interval,
                "success" if df is not None else "failed",
            )
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching gold/silver history: %s", e)
            return None

    def get_commodity(self, function: str, interval: str = "monthly") -> pd.DataFrame | None:
        """Get commodity price data (WTI, BRENT, COPPER, etc.).

        Args:
            function: Commodity function name (e.g. "WTI", "BRENT", "COPPER",
                "GOLD" via get_gold_history, "ALL_COMMODITIES").
            interval: Frequency of returned time series. Energy commodities
                accept "daily"/"weekly"/"monthly"; metals and agriculture
                accept "monthly"/"quarterly"/"annual".

        Returns:
            DataFrame indexed by date with a ``value`` column, or None on error.
        """
        try:
            params = self._build_commodity_params(function, interval=interval)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("%s API error: %s", function, data["Error Message"])
                return None
            if "Note" in data:
                logger.error("%s rate limit: %s", function, data["Note"])
                return None

            df = self._parse_single_series_response(data, None, None)
            logger.debug("%s/%s: %s", function, interval, "success" if df is not None else "failed")
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching commodity %s: %s", function, e)
            return None

    def get_economic_indicator(
        self, function: str, interval: str | None = None, **kwargs
    ) -> pd.DataFrame | None:
        """Get an economic indicator (REAL_GDP, CPI, UNEMPLOYMENT, etc.).

        Args:
            function: Economic indicator function name (e.g. "REAL_GDP",
                "CPI", "UNEMPLOYMENT", "FEDERAL_FUNDS_RATE", "TREASURY_YIELD").
            interval: Optional interval (e.g. "quarterly"/"annual" for
                REAL_GDP, "monthly"/"semiannual" for CPI,
                "daily"/"weekly"/"monthly" for FEDERAL_FUNDS_RATE).
            **kwargs: Additional params such as ``maturity`` for
                TREASURY_YIELD (e.g. "3month", "10year").

        Returns:
            DataFrame indexed by date with a ``value`` column, or None on error.
        """
        try:
            params = self._build_economic_indicator_params(function, interval=interval, **kwargs)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.error("%s API error: %s", function, data["Error Message"])
                return None
            if "Note" in data:
                logger.error("%s rate limit: %s", function, data["Note"])
                return None

            df = self._parse_single_series_response(data, None, None)
            logger.debug("%s: %s", function, "success" if df is not None else "failed")
            return df
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching economic indicator %s: %s", function, e)
            return None

    def _fetch_sector_performance(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using SECTOR_PERFORMANCE endpoint.

        The endpoint returns a single global result that is replicated for
        every requested symbol (mirroring the behaviour of
        ``_fetch_market_status``).
        """
        result = FetchResult()
        try:
            params = self._build_sector_params()
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                raise ValueError(f"API error: {data['Error Message']}")
            if "Note" in data:
                raise RuntimeError(f"API rate limit: {data['Note']}")

            df = self._parse_sector_performance_response(data)
            if df is None or df.empty:
                logger.warning("No sector performance data found")
                result.missing.extend(symbols)
                return result

            metadata = {"function": "SECTOR", "interval": interval}
            for symbol in symbols:
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching sector performance: %s", e)
            for symbol in symbols:
                result.errors[symbol] = e
        return result

    def _fetch_market_status(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using MARKET_STATUS endpoint."""
        result = FetchResult()
        try:
            params = self._build_market_status_params()
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                raise ValueError(f"API error: {data['Error Message']}")
            if "Note" in data:
                raise RuntimeError(f"API rate limit: {data['Note']}")

            df = self._parse_market_status_response(data)
            if df is None or df.empty:
                logger.warning("No market status data found")
                result.missing.extend(symbols)
                return result

            # Market status doesn't use symbols, but we return the same data for all requested symbols
            metadata = {"function": "MARKET_STATUS", "interval": interval}
            for symbol in symbols:
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching market status: %s", e)
            for symbol in symbols:
                result.errors[symbol] = e
        return result

    def _fetch_commodity(
        self,
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        interval: str,
        function: str = "WTI",
    ) -> FetchResult:
        """Fetch commodity data using the commodity endpoint (e.g. WTI, BRENT).

        Commodity endpoints return a single global series; the same data is
        replicated for every requested symbol.
        """
        result = FetchResult()
        try:
            params = self._build_commodity_params(function, interval=interval or "monthly")
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                raise ValueError(f"API error: {data['Error Message']}")
            if "Note" in data:
                raise RuntimeError(f"API rate limit: {data['Note']}")

            df = self._parse_single_series_response(data, start, end)
            if df is None or df.empty:
                logger.warning("No commodity data found for %s", function)
                result.missing.extend(symbols)
                return result

            metadata = {"function": function, "interval": interval}
            for symbol in symbols:
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching commodity %s: %s", function, e)
            for symbol in symbols:
                result.errors[symbol] = e
        return result

    def _fetch_economic_indicator(
        self,
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        interval: str,
        function: str = "REAL_GDP",
    ) -> FetchResult:
        """Fetch an economic indicator (e.g. REAL_GDP, CPI, UNEMPLOYMENT).

        These endpoints return a single global series; the same data is
        replicated for every requested symbol.
        """
        result = FetchResult()
        try:
            params = self._build_economic_indicator_params(function, interval=interval or None)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                raise ValueError(f"API error: {data['Error Message']}")
            if "Note" in data:
                raise RuntimeError(f"API rate limit: {data['Note']}")

            df = self._parse_single_series_response(data, start, end)
            if df is None or df.empty:
                logger.warning("No economic indicator data found for %s", function)
                result.missing.extend(symbols)
                return result

            metadata = {"function": function, "interval": interval}
            for symbol in symbols:
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error fetching economic indicator %s: %s", function, e)
            for symbol in symbols:
                result.errors[symbol] = e
        return result

    def _fetch_gold(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using GOLD_SILVER_SPOT endpoint per symbol.

        Symbols should be "GOLD"/"XAU" for gold or "SILVER"/"XAG" for
        silver. This endpoint returns the real-time spot price; start/end
        are ignored.
        """
        result = FetchResult()
        for symbol in symbols:
            try:
                upper = symbol.upper()
                if upper in ("GOLD", "XAU"):
                    metal = "GOLD"
                elif upper in ("SILVER", "XAG"):
                    metal = "SILVER"
                else:
                    logger.error(
                        "Invalid gold/silver symbol: %s (expected GOLD/XAU or SILVER/XAG)",
                        symbol,
                    )
                    result.errors[symbol] = ValueError(
                        f"Invalid gold/silver symbol: {symbol} (expected GOLD/XAU or SILVER/XAG)"
                    )
                    continue

                params = self._build_gold_spot_params(metal)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_single_series_response(data, None, None)
                if df is None or df.empty:
                    logger.warning("No gold/silver spot data found for %s", metal)
                    result.missing.append(symbol)
                    continue

                metadata = {"function": "GOLD_SILVER_SPOT", "interval": interval, "symbol": metal}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching gold/silver spot for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_fx_daily(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using FX_DAILY endpoint per symbol pair.

        Symbols should be in format "FROM/TO" (e.g., "USD/EUR", "EUR/USD").
        """
        result = FetchResult()
        for symbol in symbols:
            try:
                # Parse symbol pair
                if "/" not in symbol:
                    logger.error("Invalid FX symbol format: %s (expected FROM/TO)", symbol)
                    result.errors[symbol] = ValueError(
                        f"Invalid FX symbol format: {symbol} (expected FROM/TO)"
                    )
                    continue
                from_symbol, to_symbol = symbol.split("/", 1)

                params = self._build_fx_daily_params(from_symbol, to_symbol)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_fx_daily_response(from_symbol, to_symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No FX data found for %s/%s", from_symbol, to_symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {
                    "function": "FX_DAILY",
                    "interval": interval,
                    "from_symbol": from_symbol,
                    "to_symbol": to_symbol,
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching FX daily for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_fx_intraday(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using FX_INTRADAY endpoint per symbol pair.

        Symbols should be in format "FROM/TO" (e.g., "USD/EUR", "EUR/USD").
        Interval should be like "fx_5m", "fx_15m", etc.
        """
        result = FetchResult()
        for symbol in symbols:
            try:
                # Parse symbol pair
                if "/" not in symbol:
                    logger.error("Invalid FX symbol format: %s (expected FROM/TO)", symbol)
                    result.errors[symbol] = ValueError(
                        f"Invalid FX symbol format: {symbol} (expected FROM/TO)"
                    )
                    continue
                from_symbol, to_symbol = symbol.split("/", 1)

                params = self._build_fx_intraday_params(from_symbol, to_symbol, interval)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_fx_intraday_response(from_symbol, to_symbol, data, start, end)
                if df is None or df.empty:
                    logger.warning("No FX intraday data found for %s/%s", from_symbol, to_symbol)
                    result.missing.append(symbol)
                    continue

                av_interval = self.INTRADAY_INTERVALS.get(interval.replace("fx_", ""), interval)
                metadata = {
                    "function": "FX_INTRADAY",
                    "interval": av_interval,
                    "from_symbol": from_symbol,
                    "to_symbol": to_symbol,
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching FX intraday for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_currency_exchange_rate(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using CURRENCY_EXCHANGE_RATE endpoint per symbol pair.

        Symbols should be in format "FROM/TO" (e.g., "USD/EUR", "EUR/USD").
        This endpoint returns real-time exchange rates; start/end are ignored.
        """
        result = FetchResult()
        for symbol in symbols:
            try:
                # Parse symbol pair
                if "/" not in symbol:
                    logger.error("Invalid FX symbol format: %s (expected FROM/TO)", symbol)
                    result.errors[symbol] = ValueError(
                        f"Invalid FX symbol format: {symbol} (expected FROM/TO)"
                    )
                    continue
                from_currency, to_currency = symbol.split("/", 1)

                params = self._build_currency_exchange_rate_params(from_currency, to_currency)
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_currency_exchange_rate_response(from_currency, to_currency, data)
                if df is None or df.empty:
                    logger.warning(
                        "No currency exchange rate data found for %s/%s", from_currency, to_currency
                    )
                    result.missing.append(symbol)
                    continue

                metadata = {
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "interval": interval,
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching currency exchange rate for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_symbol_search(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using SYMBOL_SEARCH endpoint.

        The symbols list should contain a single query string (e.g., ["Apple"]).
        This endpoint returns symbol matches; start/end are ignored.
        """
        result = FetchResult()
        if not symbols:
            logger.warning("No query provided for symbol search")
            return result

        query = symbols[0]  # Use first symbol as search query
        try:
            params = self._build_symbol_search_params(query)
            resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                raise ValueError(f"API error: {data['Error Message']}")
            if "Note" in data:
                raise RuntimeError(f"API rate limit: {data['Note']}")

            matches = self._parse_symbol_search_response(data)
            if not matches:
                logger.warning("No symbol matches found for query: %s", query)
                result.missing.append(query)
                return result

            # Return matches as a DataFrame with the query as the symbol
            df = pd.DataFrame(matches)
            metadata = {"function": "SYMBOL_SEARCH", "interval": interval, "query": query}
            result.data[query] = MarketData(
                symbol=query,
                data=df,
                source=self.name,
                fetched_at=datetime.now(),
                metadata=metadata,
            )
        except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
            logger.error("Error searching symbols for %r: %s", query, e)
            result.errors[query] = e
        return result

    def _fetch_crypto_daily(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using DIGITAL_CURRENCY_DAILY endpoint per symbol.

        Symbols should be in format "SYMBOL" (e.g., "BTC", "ETH").
        Market is USD by default.
        """
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_crypto_daily_params(symbol, "USD")
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_crypto_response(symbol, "USD", data, start, end)
                if df is None or df.empty:
                    logger.warning("No crypto data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {
                    "function": "DIGITAL_CURRENCY_DAILY",
                    "interval": interval,
                    "symbol": symbol,
                    "market": "USD",
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching crypto daily for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_crypto_weekly(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using DIGITAL_CURRENCY_WEEKLY endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_crypto_weekly_params(symbol, "USD")
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_crypto_response(symbol, "USD", data, start, end)
                if df is None or df.empty:
                    logger.warning("No crypto weekly data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {
                    "function": "DIGITAL_CURRENCY_WEEKLY",
                    "interval": interval,
                    "symbol": symbol,
                    "market": "USD",
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching crypto weekly for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_crypto_monthly(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using DIGITAL_CURRENCY_MONTHLY endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_crypto_monthly_params(symbol, "USD")
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_crypto_response(symbol, "USD", data, start, end)
                if df is None or df.empty:
                    logger.warning("No crypto monthly data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {
                    "function": "DIGITAL_CURRENCY_MONTHLY",
                    "interval": interval,
                    "symbol": symbol,
                    "market": "USD",
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching crypto monthly for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_crypto_intraday(
        self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str
    ) -> FetchResult:
        """Fetch using DIGITAL_CURRENCY_INTRADAY endpoint per symbol."""
        result = FetchResult()
        for symbol in symbols:
            try:
                params = self._build_crypto_intraday_params(symbol, "USD", "5min")
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()

                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")

                df = self._parse_crypto_response(symbol, "USD", data, start, end)
                if df is None or df.empty:
                    logger.warning("No crypto intraday data found for %s", symbol)
                    result.missing.append(symbol)
                    continue

                metadata = {
                    "function": "DIGITAL_CURRENCY_INTRADAY",
                    "interval": interval,
                    "symbol": symbol,
                    "market": "USD",
                }
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching crypto intraday for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def _fetch_technical_indicator(
        self,
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        interval: str,
        indicator: str = "SMA",
    ) -> FetchResult:
        result = FetchResult()
        av_interval = (
            self.INTRADAY_INTERVALS.get(interval, interval)
            if interval in self.INTRADAY_INTERVALS
            else interval
        )
        # map common intervals
        if interval in ("1m", "1h"):
            av_interval = self.INTRADAY_INTERVALS.get(interval, interval)
        elif interval in ("1d", "daily"):
            av_interval = "daily"
        elif interval in ("1w", "weekly"):
            av_interval = "weekly"
        elif interval in ("1mo", "monthly"):
            av_interval = "monthly"
        else:
            av_interval = interval

        for symbol in symbols:
            try:
                params = self._build_technical_indicator_params(
                    symbol, indicator=indicator.upper(), interval=av_interval
                )
                resp = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()
                if "Error Message" in data:
                    raise ValueError(f"API error: {data['Error Message']}")
                if "Note" in data:
                    raise RuntimeError(f"API rate limit: {data['Note']}")
                df = self._parse_technical_indicator_response(symbol, indicator, data, start, end)
                if df is None or df.empty:
                    logger.warning("No technical indicator data found for %s", symbol)
                    result.missing.append(symbol)
                    continue
                metadata = {"function": indicator.upper(), "interval": interval, "symbol": symbol}
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except (ValueError, RuntimeError, KeyError, requests.RequestException) as e:
                logger.error("Error fetching technical indicator for %s: %s", symbol, e)
                result.errors[symbol] = e
        return result

    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
        **kwargs,
    ) -> FetchResult:
        """Fetch market data from Alpha Vantage.

        Supported intervals:
        - Daily: "1d", "daily" -> TIME_SERIES_DAILY_ADJUSTED
        - Weekly: "1w", "weekly", "week" -> TIME_SERIES_WEEKLY
        - Weekly Adjusted: "1wa", "weekly_adjusted" -> TIME_SERIES_WEEKLY_ADJUSTED
        - Monthly: "1mo", "monthly", "month" -> TIME_SERIES_MONTHLY
        - Monthly Adjusted: "1ma", "monthly_adjusted" -> TIME_SERIES_MONTHLY_ADJUSTED
        - Intraday: "1m", "5m", "15m", "30m", "1h", "60m" -> TIME_SERIES_INTRADAY
        - Global Quote: "quote", "realtime", "rt" -> GLOBAL_QUOTE (single symbol real-time)
        - Market Status: "market_status", "marketstatus" -> MARKET_STATUS
        - FX Daily: "fx_daily", "fx", "forex_daily" -> FX_DAILY (symbols as "FROM/TO")
        - FX Intraday: "fx_intraday", "fx_1m", "fx_5m", "fx_15m", "fx_30m", "fx_60m" -> FX_INTRADAY
        - Crypto Daily: "crypto_daily" -> DIGITAL_CURRENCY_DAILY
        - Crypto Weekly: "crypto_weekly" -> DIGITAL_CURRENCY_WEEKLY
        - Crypto Monthly: "crypto_monthly" -> DIGITAL_CURRENCY_MONTHLY
        - Crypto Intraday: "crypto_intraday" -> DIGITAL_CURRENCY_INTRADAY
        - Technical Indicators: "sma", "ema", "rsi", "macd", "bbands", "stoch", etc. -> TIME_SERIES_<INDICATOR> (default daily)
        - Sector Performance: "sector", "sector_performance", "sectors" -> SECTOR
        - Commodities: "wti", "brent", "natural_gas", "copper", "aluminum",
          "corn", "wheat", "cotton", "sugar", "coffee", "all_commodities" ->
          commodity endpoints (default granularity monthly)
        - Economic Indicators: "gdp", "cpi", "unemployment", "fed_funds_rate",
          "treasury_yield", etc. -> economic indicator endpoints
        - Currency Exchange Rate: "fx_rate", "currency_exchange_rate", "forex_rate" -> CURRENCY_EXCHANGE_RATE (symbols as "FROM/TO")
        - Symbol Search: "symbol_search", "search_symbols", "symbol_lookup" -> SYMBOL_SEARCH (single query string in symbols)
        - Precious Metals: "gold", "silver" -> GOLD_SILVER_SPOT (symbols "GOLD"/"XAU" or "SILVER"/"XAG")
        - Batch Quotes: any other interval -> BATCH_STOCK_PRICES

        Uses disk caching if cache_dir is configured.

        For technical indicators (interval in TECHNICAL_INDICATORS), the optional
        keyword argument ``ti_interval`` specifies the time-series resolution
        (e.g., "daily", "5min", "weekly", "monthly"). Defaults to "daily".
        """
        # Try cache first
        if self._cache_dir:
            key = self._cache_key(symbols, start, end, interval)
            path = self._cache_path(key)
            if self._is_cache_valid(path):
                cached = self._load_cache(path)
                if cached is not None:
                    logger.debug("Cache hit for %s", key)
                    return cached

        is_intraday = interval in self.INTRADAY_INTERVALS
        is_weekly = interval in self.WEEKLY_INTERVALS
        is_monthly = interval in self.MONTHLY_INTERVALS
        is_quote = interval in self.QUOTE_INTERVALS
        is_market_status = interval in self.MARKET_STATUS_INTERVALS
        is_fx_daily = interval in self.FX_DAILY_INTERVALS
        is_fx_intraday = interval in self.FX_INTRADAY_INTERVALS
        is_technical = interval in self.TECHNICAL_INDICATORS
        is_sector = interval in self.SECTOR_INTERVALS
        is_commodity = interval in self.COMMODITIES_INTERVALS
        is_economic = interval in self.ECONOMIC_INDICATORS
        is_currency_exchange_rate = interval in self.CURRENCY_EXCHANGE_RATE_INTERVALS
        is_symbol_search = interval in self.SYMBOL_SEARCH_INTERVALS
        is_gold = interval in self.GOLD_INTERVALS

        if interval in ("1d", "daily"):
            fetch_result = self._fetch_single(symbols, start, end, interval)
        elif interval in ("1wa", "weekly_adjusted"):
            fetch_result = self._fetch_weekly_adjusted(symbols, start, end, interval)
        elif is_weekly:
            fetch_result = self._fetch_weekly(symbols, start, end, interval)
        elif interval in ("1ma", "monthly_adjusted"):
            fetch_result = self._fetch_monthly_adjusted(symbols, start, end, interval)
        elif is_monthly:
            fetch_result = self._fetch_monthly(symbols, start, end, interval)
        elif is_intraday:
            fetch_result = self._fetch_intraday(symbols, start, end, interval)
        elif is_quote:
            fetch_result = self._fetch_global_quote(symbols, start, end, interval)
        elif is_market_status:
            fetch_result = self._fetch_market_status(symbols, start, end, interval)
        elif is_sector:
            fetch_result = self._fetch_sector_performance(symbols, start, end, interval)
        elif is_commodity:
            fetch_result = self._fetch_commodity(
                symbols, start, end, interval, function=self.COMMODITY_FUNCTION_MAP[interval]
            )
        elif is_economic:
            fetch_result = self._fetch_economic_indicator(
                symbols, start, end, interval, function=self.ECONOMIC_FUNCTION_MAP[interval]
            )
        elif is_fx_daily:
            fetch_result = self._fetch_fx_daily(symbols, start, end, interval)
        elif is_fx_intraday:
            fetch_result = self._fetch_fx_intraday(symbols, start, end, interval)
        elif is_currency_exchange_rate:
            fetch_result = self._fetch_currency_exchange_rate(symbols, start, end, interval)
        elif is_symbol_search:
            fetch_result = self._fetch_symbol_search(symbols, start, end, interval)
        elif is_gold:
            fetch_result = self._fetch_gold(symbols, start, end, interval)
        elif interval == "crypto_daily" or interval == "digital_daily":
            fetch_result = self._fetch_crypto_daily(symbols, start, end, interval)
        elif interval == "crypto_weekly" or interval == "digital_weekly":
            fetch_result = self._fetch_crypto_weekly(symbols, start, end, interval)
        elif interval == "crypto_monthly" or interval == "digital_monthly":
            fetch_result = self._fetch_crypto_monthly(symbols, start, end, interval)
        elif interval == "crypto_intraday" or interval == "digital_intraday":
            fetch_result = self._fetch_crypto_intraday(symbols, start, end, interval)
        elif is_technical:
            # Technical-indicator intervals pass the indicator name (e.g. "sma",
            # "rsi") as the interval; the underlying time-series resolution
            # can be specified via ti_interval kwarg (default: "daily").
            ti_interval = kwargs.get("ti_interval", "daily")
            fetch_result = self._fetch_technical_indicator(
                symbols, start, end, ti_interval, indicator=interval
            )
        else:
            # BATCH_STOCK_PRICES only returns latest quote, ignore start/end
            fetch_result = self._fetch_batch(symbols, start, end, interval)

        # Save to cache
        if self._cache_dir:
            cache_interval = interval
            if is_technical:
                ti_interval = kwargs.get("ti_interval", "daily")
                cache_interval = f"{interval}:{ti_interval}"
            key = self._cache_key(symbols, start, end, cache_interval)
            path = self._cache_path(key)
            self._save_cache(path, fetch_result)
            logger.debug("Cached result for %s", key)

        return fetch_result

    def fetch_many(
        self,
        requests: list[dict[str, Any]],
    ) -> dict[str, FetchResult]:
        """Fetch multiple requests using batched endpoints where possible.

        Groups requests by interval. For daily/weekly/monthly intervals, fetches each symbol
        individually (Alpha Vantage does not support batch historical).
        For intraday intervals, fetches each symbol individually via TIME_SERIES_INTRADAY.
        For real-time quotes, uses BATCH_STOCK_PRICES per group.
        For global quote, fetches per symbol via GLOBAL_QUOTE endpoint.
        For market status, sector, commodities, economic indicators, FX, crypto,
        currency exchange rate, symbol search, and precious metals endpoints,
        fetches per symbol.
        """
        results: dict[str, FetchResult] = {}

        groups: dict[
            str, list[tuple[list[str], datetime | None, datetime | None, str, dict[str, Any]]]
        ] = {}
        for req in requests:
            symbols = req.get("symbols", [])
            start = req.get("start")
            end = req.get("end")
            interval = req.get("interval", "1d")
            # Extract any extra kwargs (e.g., ti_interval for technical indicators)
            extra_kwargs = {
                k: v for k, v in req.items() if k not in ("symbols", "start", "end", "interval")
            }
            interval_key = interval
            bucket = groups.get(interval_key, [])
            bucket.append((symbols, start, end, interval, extra_kwargs))
            groups[interval_key] = bucket

        for interval, reqs in groups.items():
            all_symbols = sorted({s for symbols, _, _, _, _ in reqs for s in symbols})
            is_intraday = interval in self.INTRADAY_INTERVALS
            is_weekly = interval in self.WEEKLY_INTERVALS
            is_monthly = interval in self.MONTHLY_INTERVALS
            is_quote = interval in self.QUOTE_INTERVALS
            is_market_status = interval in self.MARKET_STATUS_INTERVALS
            is_sector = interval in self.SECTOR_INTERVALS
            is_commodity = interval in self.COMMODITIES_INTERVALS
            is_economic = interval in self.ECONOMIC_INDICATORS
            is_fx_daily = interval in self.FX_DAILY_INTERVALS
            is_fx_intraday = interval in self.FX_INTRADAY_INTERVALS
            is_crypto = interval in self.CRYPTO_INTERVALS
            is_digital = interval in self.DIGITAL_CURRENCY_INTERVALS
            is_technical = interval in self.TECHNICAL_INDICATORS
            is_currency_exchange_rate = interval in self.CURRENCY_EXCHANGE_RATE_INTERVALS
            is_symbol_search = interval in self.SYMBOL_SEARCH_INTERVALS
            is_gold = interval in self.GOLD_INTERVALS

            if interval in ("1d", "daily", "1wa", "weekly_adjusted") or is_weekly or is_monthly:
                # No batch historical endpoint; fall back to per-symbol
                for symbols, start, end, interval, extra_kwargs in reqs:
                    key = self._request_key(symbols, start, end, interval)
                    results[key] = self.fetch(symbols, start, end, interval, **extra_kwargs)
            elif is_intraday:
                # No batch historical intraday endpoint; fall back to per-symbol
                for symbols, start, end, interval, extra_kwargs in reqs:
                    key = self._request_key(symbols, start, end, interval)
                    results[key] = self.fetch(symbols, start, end, interval, **extra_kwargs)
            elif is_quote:
                # GLOBAL_QUOTE is per-symbol; fall back to per-symbol
                for symbols, start, end, interval, extra_kwargs in reqs:
                    key = self._request_key(symbols, start, end, interval)
                    results[key] = self.fetch(symbols, start, end, interval, **extra_kwargs)
            elif (
                is_market_status
                or is_sector
                or is_commodity
                or is_economic
                or is_fx_daily
                or is_fx_intraday
                or is_crypto
                or is_digital
                or is_technical
                or is_currency_exchange_rate
                or is_symbol_search
                or is_gold
            ):
                # These endpoints are per-symbol/pair or single global result;
                # fall back to per-symbol
                for symbols, start, end, interval, extra_kwargs in reqs:
                    key = self._request_key(symbols, start, end, interval)
                    results[key] = self.fetch(symbols, start, end, interval, **extra_kwargs)
            else:
                # Batch real-time quotes
                batch_result = self._fetch_batch(all_symbols, None, None, interval)
                for symbols, start, end, interval, extra_kwargs in reqs:
                    key = self._request_key(symbols, start, end, interval)
                    sliced = FetchResult()
                    for symbol in symbols:
                        if symbol in batch_result.data:
                            sliced.data[symbol] = batch_result.data[symbol]
                        elif symbol in batch_result.errors:
                            sliced.errors[symbol] = batch_result.errors[symbol]
                        else:
                            sliced.missing.append(symbol)
                    results[key] = sliced

        return results

    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        """Fetch latest market data (real-time quotes) using BATCH_STOCK_PRICES."""
        return self._fetch_batch(symbols, None, None, "1m")
