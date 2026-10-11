"""Base data provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class MarketData:
    """Container for market data."""

    symbol: str
    data: pd.DataFrame
    source: str
    fetched_at: datetime
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class FetchResult:
    """Result of a fetch operation with data, errors, and missing symbols."""

    data: dict[str, MarketData] = field(default_factory=dict)
    errors: dict[str, Exception] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Return True if all requested symbols were fetched successfully."""
        return not self.errors and not self.missing

    @property
    def has_errors(self) -> bool:
        """Return True if any hard errors occurred."""
        return bool(self.errors)

    @property
    def has_missing(self) -> bool:
        """Return True if any symbols returned no data."""
        return bool(self.missing)


class DataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        """Fetch market data for given symbols.

        Returns a FetchResult containing successful data, errors, and missing symbols.
        """

    @abstractmethod
    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        """Fetch latest market data for given symbols.

        Returns a FetchResult containing successful data, errors, and missing symbols.
        """

    def fetch_many(
        self,
        requests: list[dict[str, Any]],
    ) -> dict[str, FetchResult]:
        """Fetch multiple distinct data ranges in one call.

        Each request is a dict with keys ``symbols``, ``start``, ``end``,
        ``interval`` (all optional, matching ``fetch`` defaults). The return
        value maps a stable request key (``"symbols|start|end|interval"``) to
        the resulting ``FetchResult``. Providers may override this to batch
        network calls more efficiently than per-request loops.

        The default implementation delegates to ``fetch`` for each request.
        """
        results: dict[str, FetchResult] = {}
        for req in requests:
            symbols = req.get("symbols", [])
            start = req.get("start")
            end = req.get("end")
            interval = req.get("interval", "1d")
            key = self._request_key(symbols, start, end, interval)
            results[key] = self.fetch(symbols, start, end, interval)
        return results

    @staticmethod
    def _request_key(
        symbols: list[str],
        start: datetime | None,
        end: datetime | None,
        interval: str,
    ) -> str:
        """Build a stable string key for a fetch request."""
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{symbols_str}|{start_str}|{end_str}|{interval}"

    @property
    @abstractmethod
    def name(self) -> str:
        """Return provider name."""


class DataManager:
    """Manages data fetching and caching from multiple providers."""

    def __init__(self, providers: list[DataProvider] | None = None):
        self.providers = providers or []
        self._cache: dict[str, FetchResult] = {}

    def add_provider(self, provider: DataProvider) -> None:
        """Add a data provider."""
        self.providers.append(provider)

    def get_provider(self, name: str) -> DataProvider | None:
        """Get provider by name."""
        for provider in self.providers:
            if provider.name == name:
                return provider
        return None

    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
        provider_name: str | None = None,
        use_cache: bool = True,
    ) -> FetchResult:
        """Fetch market data using specified or first available provider.

        Returns a FetchResult containing successful data, errors, and missing symbols.
        """
        provider = None
        if provider_name:
            provider = self.get_provider(provider_name)
        elif self.providers:
            provider = self.providers[0]

        if not provider:
            raise ValueError("No data provider available")

        cache_key = f"{provider.name}:{','.join(sorted(symbols))}:{start}:{end}:{interval}"

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        result = provider.fetch(symbols, start, end, interval)

        if use_cache:
            self._cache[cache_key] = result

        return result

    def clear_cache(self) -> None:
        """Clear the data cache."""
        self._cache.clear()

    def fetch_many(
        self,
        requests: list[dict[str, Any]],
        provider_name: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, FetchResult]:
        """Fetch multiple distinct data ranges via a single provider.

        Delegates to ``DataProvider.fetch_many`` on the selected (or first)
        provider, so providers can batch network calls. The in-memory cache
        is checked per request when ``use_cache`` is True.
        """
        provider = None
        if provider_name:
            provider = self.get_provider(provider_name)
        elif self.providers:
            provider = self.providers[0]

        if not provider:
            raise ValueError("No data provider available")

        results: dict[str, FetchResult] = {}
        pending: list[tuple[dict[str, Any], str, str]] = []

        for req in requests:
            symbols = req.get("symbols", [])
            start = req.get("start")
            end = req.get("end")
            interval = req.get("interval", "1d")
            key = provider._request_key(symbols, start, end, interval)
            cache_key = f"{provider.name}:{key}"

            if use_cache and cache_key in self._cache:
                results[key] = self._cache[cache_key]
            else:
                pending.append((req, key, cache_key))

        # Delegate the uncached requests to the provider in a single call so it
        # can batch network requests; each result is keyed by ``_request_key``.
        if pending:
            provider_results = provider.fetch_many([req for req, _, _ in pending])
            for req, key, cache_key in pending:
                result = provider_results.get(key, FetchResult())
                if use_cache:
                    self._cache[cache_key] = result
                results[key] = result

        return results
