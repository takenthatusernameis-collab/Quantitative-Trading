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
