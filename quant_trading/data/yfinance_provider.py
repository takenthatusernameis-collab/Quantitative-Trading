"""Yahoo Finance data provider implementation."""

import os
import pickle
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

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

    def _cache_key(self, symbols: list[str], start: datetime | None, end: datetime | None, interval: str) -> str:
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
            except (ValueError, RuntimeError, KeyError, ImportError, OSError, ConnectionError, TimeoutError) as e:
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
    """Alpha Vantage data provider (placeholder for future implementation)."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "alphavantage"

    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        raise NotImplementedError("Alpha Vantage provider not yet implemented")

    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        raise NotImplementedError("Alpha Vantage provider not yet implemented")