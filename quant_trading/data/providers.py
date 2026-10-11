"""Base data provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class DataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> dict[str, MarketData]:
        """Fetch market data for given symbols."""

    @abstractmethod
    def fetch_latest(self, symbols: list[str]) -> dict[str, MarketData]:
        """Fetch latest market data for given symbols."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return provider name."""


class DataManager:
    """Manages data fetching and caching from multiple providers."""

    def __init__(self, providers: list[DataProvider] | None = None):
        self.providers = providers or []
        self._cache: dict[str, dict[str, MarketData]] = {}

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
    ) -> dict[str, MarketData]:
        """Fetch market data using specified or first available provider."""
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