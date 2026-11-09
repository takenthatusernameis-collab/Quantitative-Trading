"""Base data provider interface.

This module defines the abstract :class:`DataProvider` contract consumed by
the backtest engine and the higher-level :class:`DataManager`. Concrete
providers (e.g. :mod:`quant_trading.data.yfinance_provider` and
:mod:`quant_trading.data.synthetic`) implement the same three methods:
:attr:`fetch`, :attr:`fetch_latest`, and :attr:`fetch_many`.

Examples:
    >>> from quant_trading.data.providers import DataManager, FetchResult
    >>> from quant_trading.data.synthetic import create_synthetic_provider
    >>> manager = DataManager()
    >>> manager.add_provider(create_synthetic_provider({"AAPL": 100.0}))
    >>> result = manager.fetch(["AAPL"])
    >>> result.is_success
    True
    >>> "AAPL" in result.data
    True
    >>> ok = FetchResult()
    >>> ok.is_success
    True
    >>> ok.has_errors
    False
    >>> ok.has_missing
    False
    >>> failed = FetchResult(errors={"AAPL": RuntimeError("boom")})
    >>> failed.has_errors
    True
    >>> failed.is_success
    False

"""

__all__ = [
    "DataManager",
    "DataProvider",
    "FetchResult",
    "MarketData",
    "create_data_manager_from_config",
]

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from quant_trading.config.settings import DataConfig


def _iso(value: datetime | None) -> str | None:
    """Return ISO-8601 string for a datetime, or None for None."""
    if value is None:
        return None
    return value.isoformat()


def _coerce_datetime(value: Any) -> datetime | None:
    """Coerce a value to a datetime, accepting ISO-8601 strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


@dataclass
class MarketData:
    """Container for the market data fetched for a single symbol.

    Attributes:
        symbol: Ticker symbol the data applies to.
        data: OHLCV-style :class:`pandas.DataFrame` indexed by timestamp.
        source: Name of the provider that supplied the data.
        fetched_at: Timestamp when the data was retrieved.
        metadata: Optional free-form extra context keyed by strings.

    Examples:
        >>> import pandas as pd
        >>> from quant_trading.data.providers import MarketData
        >>> md = MarketData(
        ...     symbol="AAPL",
        ...     data=pd.DataFrame({"close": [100.0, 101.0]}),
        ...     source="synthetic",
        ...     fetched_at=pd.Timestamp("2024-01-01"),
        ... )
        >>> md.symbol
        'AAPL'
        >>> md.metadata
        {}
        >>> float(md.data["close"].iloc[1])
        101.0
        >>> restored = MarketData.from_dict(md.to_dict())
        >>> restored.symbol == md.symbol
        True
        >>> float(restored.data["close"].iloc[1])
        101.0

    """

    symbol: str
    data: pd.DataFrame
    source: str
    fetched_at: datetime
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Initialize metadata to an empty dict when not provided."""
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize this market data to a plain dictionary.

        The :class:`~pandas.DataFrame` is encoded with ``orient="split"``
        (index/columns/data) so it survives a JSON round-trip with full index
        fidelity. The index and values are JSON-normalized (timestamps to
        ISO-8601 strings) before encoding.

        Returns:
            Dictionary with ``symbol``, ``data``, ``source``, ``fetched_at``,
            and ``metadata``.

        Examples:
            >>> import pandas as pd
            >>> from quant_trading.data.providers import MarketData
            >>> md = MarketData(
            ...     symbol="AAPL",
            ...     data=pd.DataFrame({"close": [1.0]}),
            ...     source="synthetic",
            ...     fetched_at=pd.Timestamp("2024-01-01"),
            ... )
            >>> md.to_dict()["symbol"]
            'AAPL'

        """
        raw = self.data.to_dict(orient="split")
        raw_index = raw.get("index") or []
        is_dt_index = isinstance(self.data.index, pd.DatetimeIndex) or pd.api.types.is_datetime64_any_dtype(
            self.data.index
        )
        if is_dt_index:
            index = [(v.isoformat() if hasattr(v, "isoformat") else v) for v in raw_index]
        else:
            index = list(raw_index)
        return {
            "symbol": self.symbol,
            "data": {
                "index": index,
                "columns": raw.get("columns"),
                "data": raw.get("data"),
                "datetime_index": bool(is_dt_index),
            },
            "source": self.source,
            "fetched_at": _iso(self.fetched_at),
            "metadata": self.metadata if self.metadata is not None else {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketData":
        """Deserialize a :class:`MarketData` from a dictionary.

        Missing keys fall back to safe defaults (empty frame, current
        timestamp). ISO-8601 timestamps are accepted for ``fetched_at`` and
        for the data-frame index.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`MarketData`.

        Examples:
            >>> from quant_trading.data.providers import MarketData
            >>> restored = MarketData.from_dict({"symbol": "AAPL", "source": "s"})
            >>> restored.symbol
            'AAPL'
            >>> restored.data.empty
            True

        """
        payload = data.get("data") or {}
        columns = payload.get("columns")
        rows = payload.get("data") or []
        index = payload.get("index") or []
        dt_index = payload.get("datetime_index")
        if index and (
            dt_index is True
            or (
                dt_index is None
                and len(index) > 0
                and isinstance(index[0], str)
                and ("-" in index[0] or "T" in index[0] or ":" in index[0])
            )
        ):
            try:
                index = pd.to_datetime(index)
            except (ValueError, TypeError):
                pass
        frame = pd.DataFrame(rows, index=index, columns=columns)
        return cls(
            symbol=str(data.get("symbol", "")),
            data=frame,
            source=str(data.get("source", "")),
            fetched_at=_coerce_datetime(data.get("fetched_at")) or datetime.now(),
            metadata=data.get("metadata") if data.get("metadata") is not None else {},
        )


@dataclass
class FetchResult:
    """Result of a fetch operation with data, errors, and missing symbols.

    A single fetch call may partially succeed: some symbols return data,
    others raise hard errors, and the rest are reported as missing. The
    three properties (:attr:`is_success`, :attr:`has_errors`,
    :attr:`has_missing`) make it easy to branch on the outcome.

    Attributes:
        data: Symbol-keyed :class:`MarketData` for successful fetches.
        errors: Symbol-keyed exceptions for fetches that failed hard.
        missing: List of symbols that returned no data but did not error.

    Examples:
        >>> from quant_trading.data.providers import FetchResult
        >>> ok = FetchResult()
        >>> ok.is_success
        True
        >>> ok.has_errors
        False
        >>> failed = FetchResult(errors={"AAPL": RuntimeError("boom")})
        >>> failed.has_errors
        True
        >>> failed.is_success
        False
        >>> missing = FetchResult(missing=["MSFT"])
        >>> missing.has_missing
        True
        >>> missing.is_success
        False
        >>> restored = FetchResult.from_dict(ok.to_dict())
        >>> restored.is_success
        True

    """

    data: dict[str, MarketData] = field(default_factory=dict)
    errors: dict[str, Exception] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Return True if all requested symbols were fetched successfully.

        True only when both :attr:`errors` and :attr:`missing` are empty.
        """
        return not self.errors and not self.missing

    @property
    def has_errors(self) -> bool:
        """Return True if any hard errors occurred."""
        return bool(self.errors)

    @property
    def has_missing(self) -> bool:
        """Return True if any symbols returned no data."""
        return bool(self.missing)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this fetch result to a plain dictionary.

        Each :class:`MarketData` value is serialized via its ``to_dict``.
        Exceptions in :attr:`errors` cannot be faithfully round-tripped as
        live objects; they are encoded as ``{"type": <name>, "message":
        <str>}`` for inspection. Equality-based round-trips therefore compare
        serialized form (see ``tests/test_serialization_roundtrip.py``).

        Returns:
            Dictionary with ``data``, ``errors``, and ``missing``.

        Examples:
            >>> from quant_trading.data.providers import FetchResult
            >>> FetchResult(missing=["MSFT"]).to_dict()["missing"]
            ['MSFT']

        """
        return {
            "data": {k: v.to_dict() for k, v in self.data.items()},
            "errors": {
                k: {"type": type(v).__name__, "message": str(v)} for k, v in self.errors.items()
            },
            "missing": list(self.missing),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FetchResult":
        """Deserialize a :class:`FetchResult` from a dictionary.

        Missing keys fall back to safe defaults. Error entries are restored as
        :class:`Exception` instances carrying the stored message (the original
        exception type is not reconstructed as a live subclass).

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`FetchResult`.

        Examples:
            >>> from quant_trading.data.providers import FetchResult
            >>> restored = FetchResult.from_dict({"missing": ["MSFT"]})
            >>> restored.has_missing
            True

        """
        raw_data = data.get("data") or {}
        raw_errors = data.get("errors") or {}
        restored_data = {
            k: (MarketData.from_dict(v) if isinstance(v, dict) else v)
            for k, v in raw_data.items()
        }
        restored_errors: dict[str, Exception] = {}
        for k, v in raw_errors.items():
            if isinstance(v, dict):
                msg = str(v.get("message", ""))
                etype = str(v.get("type", "Exception")) or "Exception"
                try:
                    err_cls: type[Exception] = type(etype, (Exception,), {})
                except (TypeError, ValueError):
                    err_cls = Exception
                restored_errors[k] = err_cls(msg)
            elif isinstance(v, BaseException):
                restored_errors[k] = v if isinstance(v, Exception) else Exception(str(v))
            else:
                restored_errors[k] = Exception(str(v))
        missing = list(data.get("missing") or [])
        return cls(data=restored_data, errors=restored_errors, missing=missing)


class DataProvider(ABC):
    """Abstract base class for data providers.

    Concrete providers must implement :meth:`fetch` and
    :meth:`fetch_latest`, and expose their identifier through the
    :attr:`name` property. :meth:`fetch_many` has a default implementation
    that delegates to :meth:`fetch` per request, but providers can override
    it to batch network calls.

    Examples:
        Subclass and implement the abstract methods::

            >>> from quant_trading.data.providers import DataProvider, FetchResult
            >>> class MyProvider(DataProvider):
            ...     @property
            ...     def name(self) -> str:
            ...         return "my"
            ...     def fetch(self, symbols, start=None, end=None, interval="1d"):
            ...         return FetchResult()
            ...     def fetch_latest(self, symbols):
            ...         return FetchResult()
            >>> provider = MyProvider()
            >>> provider.name
            'my'
            >>> result = provider.fetch(["AAPL"])
            >>> result.is_success
            True
            >>> latest = provider.fetch_latest(["AAPL"])
            >>> latest.is_success
            True

    """

    @abstractmethod
    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        """Fetch market data for given symbols.

        Args:
            symbols: Tickers to fetch.
            start: Optional inclusive start of the requested window.
            end: Optional inclusive end of the requested window.
            interval: Bar interval (e.g. ``"1d"``, ``"1h"``).

        Returns:
            A :class:`FetchResult` containing successful data, hard errors,
            and symbols that returned no data.

        """
        ...  # pragma: no cover

    @abstractmethod
    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        """Fetch the latest available market data for given symbols.

        Args:
            symbols: Tickers to fetch.

        Returns:
            A :class:`FetchResult` containing successful data, hard errors,
            and symbols that returned no data.

        """
        ...  # pragma: no cover

    def fetch_many(
        self,
        requests: list[dict[str, Any]],
    ) -> dict[str, FetchResult]:
        """Fetch multiple distinct data ranges in one call.

        Each request is a dict with keys ``symbols``, ``start``, ``end``,
        and ``interval`` (all optional, matching :meth:`fetch` defaults).
        The return value maps a stable request key
        (``"symbols|start|end|interval"``) to the resulting
        :class:`FetchResult`. The default implementation delegates to
        :meth:`fetch` for each request; providers may override this to
        batch network calls more efficiently.

        Args:
            requests: List of request dicts (each may contain ``symbols``,
                ``start``, ``end``, and ``interval``).

        Returns:
            Mapping of stable request key to :class:`FetchResult`.

        Examples:
            >>> from quant_trading.data.synthetic import create_synthetic_provider
            >>> provider = create_synthetic_provider({"AAPL": 100.0})
            >>> results = provider.fetch_many([{"symbols": ["AAPL"]}])
            >>> list(results.keys()) == [provider._request_key(["AAPL"], None, None, "1d")]
            True
            >>> results[provider._request_key(["AAPL"], None, None, "1d")].is_success
            True

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
        """Build a stable string key for a fetch request.

        The key is order-independent with respect to ``symbols`` (they are
        sorted) and deterministic, so it can be used as a cache or result
        dictionary key.

        Args:
            symbols: Tickers for the request.
            start: Optional start of the window.
            end: Optional end of the window.
            interval: Bar interval.

        Returns:
            A string of the form ``"symbols|start|end|interval"`` where
            missing dates are rendered as ``"none"``.

        Examples:
            >>> from quant_trading.data.providers import DataProvider
            >>> DataProvider._request_key(["MSFT", "AAPL"], None, None, "1d")
            'AAPL,MSFT|none|none|1d'

        """
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{symbols_str}|{start_str}|{end_str}|{interval}"

    @property
    @abstractmethod
    def name(self) -> str:
        """Return provider name.

        Returns:
            A short, human-readable identifier for this provider (e.g.
            ``"yfinance"`` or ``"synthetic"``).

        """
        ...  # pragma: no cover


class DataManager:
    """Manages data fetching and caching from multiple providers.

    The DataManager is the primary entry point for fetching market data in
    the backtest engine. It wraps one or more :class:`DataProvider` objects,
    selects a provider by name (or falls back to the first registered one),
    and transparently caches :class:`FetchResult` objects keyed by provider
    name and request parameters.

    Attributes:
        providers: Ordered list of registered :class:`DataProvider` objects.
        _cache: In-memory cache mapping ``"provider_name:request_key"`` to a
            cached :class:`FetchResult`.

    Examples:
        >>> from quant_trading.data.providers import DataManager
        >>> from quant_trading.data.synthetic import create_synthetic_provider
        >>> manager = DataManager()
        >>> manager.add_provider(create_synthetic_provider({"AAPL": 100.0}))
        >>> result = manager.fetch(["AAPL"])
        >>> result.is_success
        True
        >>> "AAPL" in result.data
        True
        >>> manager.get_provider("nonexistent") is None
        True

    """

    def __init__(self, providers: list[DataProvider] | None = None):
        """Initialize the data manager.

        Args:
            providers: Optional list of providers to register immediately.
                Defaults to an empty list.

        """
        self.providers = providers or []
        self._cache: dict[str, FetchResult] = {}

    def add_provider(self, provider: DataProvider) -> None:
        """Add a data provider to the manager.

        Args:
            provider: The :class:`DataProvider` to register.

        Returns:
            None.

        """
        self.providers.append(provider)

    def get_provider(self, name: str) -> DataProvider | None:
        """Get a provider by name.

        Args:
            name: Provider identifier returned by its :attr:`DataProvider.name`.

        Returns:
            The matching provider, or ``None`` when no provider with that
            name is registered.

        """
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
        """Fetch market data using a specified or first available provider.

        When ``provider_name`` is given, the matching provider is selected;
        otherwise the first registered provider is used. Results are cached
        in memory (keyed by provider name and request parameters) when
        ``use_cache`` is True, so repeated calls return the same
        :class:`FetchResult` without re-fetching.

        Args:
            symbols: Tickers to fetch.
            start: Optional inclusive start of the requested window.
            end: Optional inclusive end of the requested window.
            interval: Bar interval (e.g. ``"1d"``, ``"1h"``).
            provider_name: Optional name of the provider to use.
            use_cache: When True, return a cached result when available and
                store new results for later reuse.

        Returns:
            A :class:`FetchResult` for the selected provider.

        Raises:
            ValueError: If no provider matches ``provider_name`` and no
                providers are registered.

        """
        provider = None
        if provider_name:
            provider = self.get_provider(provider_name)
        elif self.providers:
            provider = self.providers[0]

        if not provider:
            raise ValueError("No data provider available")

        req_key = provider._request_key(symbols, start, end, interval)
        cache_key = f"{provider.name}:{req_key}"

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        result = provider.fetch(symbols, start, end, interval)

        if use_cache:
            self._cache[cache_key] = result

        return result

    def clear_cache(self) -> None:
        """Clear the in-memory data cache.

        Returns:
            None.

        """
        self._cache.clear()

    def fetch_many(
        self,
        requests: list[dict[str, Any]],
        provider_name: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, FetchResult]:
        """Fetch multiple distinct data ranges via a single provider.

        Delegates to :meth:`DataProvider.fetch_many` on the selected (or
        first) provider so providers can batch network calls. The in-memory
        cache is checked per request when ``use_cache`` is True; uncached
        requests are forwarded in a single batched call.

        Args:
            requests: List of request dicts (each may contain ``symbols``,
                ``start``, ``end``, and ``interval``).
            provider_name: Optional name of the provider to use.
            use_cache: When True, return cached results when available and
                store new results for later reuse.

        Returns:
            Mapping of stable request key to :class:`FetchResult`.

        Raises:
            ValueError: If no provider matches ``provider_name`` and no
                providers are registered.

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


def create_data_manager_from_config(config: "DataConfig") -> DataManager:
    """Create a :class:`DataManager` configured from a :class:`DataConfig`.

    The provider is selected based on ``config.provider``:

    * ``"synthetic"`` or ``config.offline`` - a lazy synthetic provider that
      generates data on first fetch.
    * ``"yfinance"`` - a :class:`YFinanceProvider` with the configured cache
      directory.
    * ``"alphavantage"`` - an :class:`AlphaVantageProvider` with the
      configured API key and cache directory.

    Args:
        config: :class:`DataConfig` instance with provider settings.

    Returns:
        A :class:`DataManager` with the appropriate provider(s) configured.

    Raises:
        ValueError: If ``config.provider`` is not one of the supported values.

    Examples:
        >>> from quant_trading.config.settings import DataConfig
        >>> from quant_trading.data.providers import create_data_manager_from_config
        >>> manager = create_data_manager_from_config(DataConfig(provider="synthetic"))
        >>> manager.providers[0].name
        'synthetic'

    """
    from quant_trading.config.settings import DataConfig

    providers: list[DataProvider] = []

    if config.offline or config.provider == "synthetic":
        # Offline mode: use synthetic data provider
        from quant_trading.data.synthetic import SyntheticDataProvider

        class LazySyntheticProvider(SyntheticDataProvider):
            """Synthetic provider that lazily generates data on first fetch.

            Data is generated via :func:`quant_trading.data.synthetic.create_synthetic_data`
            on demand, using the synthetic settings from :class:`DataConfig`.
            This avoids generating unused data when symbols are not known
            upfront and mirrors the "offline" behavior expected by the
            configuration layer.

            Attributes:
                _config: Configuration object containing synthetic generation
                    parameters (``synthetic_days``, ``synthetic_seed``).
                _initialized: Whether synthetic data has been generated for the
                    current symbol set.
                _symbols: List of symbols for which data was last generated.

            """

            def __init__(self, config: DataConfig):
                """Initialize the lazy synthetic provider.

                Args:
                    config: :class:`DataConfig` instance with synthetic
                        generation parameters.

                """
                self._config = config
                self._initialized = False
                self._symbols: list[str] | None = None
                super().__init__({}, name="synthetic")

            def _ensure_initialized(self, symbols: list[str]) -> None:
                """Generate synthetic data if not initialized or symbols changed.

                Args:
                    symbols: Tickers that will be fetched. If different from
                        the previously generated set, new data is generated.

                Returns:
                    None.

                """
                if not self._initialized or set(symbols) != set(self._symbols or []):
                    from quant_trading.data.synthetic import create_synthetic_data

                    end_date = datetime.now()
                    data = create_synthetic_data(
                        symbols=symbols,
                        days=self._config.synthetic_days,
                        seed=self._config.synthetic_seed,
                        end_date=end_date,
                    )
                    self._data = data
                    self._symbols = symbols
                    self._initialized = True

            def fetch(
                self,
                symbols: list[str],
                start: datetime | None = None,
                end: datetime | None = None,
                interval: str = "1d",
            ) -> FetchResult:
                """Fetch historical data for the given symbols.

                Args:
                    symbols: List of ticker symbols to fetch.
                    start: Optional start datetime. Defaults to None.
                    end: Optional end datetime. Defaults to None.
                    interval: Data interval (e.g., ``"1d"``). Defaults to
                        ``"1d"``.

                Returns:
                    :class:`FetchResult` containing fetched market data.

                """
                self._ensure_initialized(symbols)
                return super().fetch(symbols, start, end, interval)

            def fetch_latest(self, symbols: list[str]) -> FetchResult:
                """Fetch the most recent data for the given symbols.

                Args:
                    symbols: List of ticker symbols to fetch latest data for.

                Returns:
                    :class:`FetchResult` containing the latest market data.

                """
                self._ensure_initialized(symbols)
                return super().fetch_latest(symbols)

        providers.append(LazySyntheticProvider(config))
    elif config.provider == "yfinance":
        from quant_trading.data.yfinance_provider import YFinanceProvider

        providers.append(YFinanceProvider(cache_dir=config.cache_dir))
    elif config.provider == "alphavantage":
        from quant_trading.data.yfinance_provider import AlphaVantageProvider

        providers.append(
            AlphaVantageProvider(
                api_key=config.alphavantage_api_key,
                cache_dir=config.cache_dir,
            )
        )
    else:
        raise ValueError(f"Unknown data provider: {config.provider}")

    return DataManager(providers)
