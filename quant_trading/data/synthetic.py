"""Synthetic data generation for testing and offline examples.

This module generates deterministic, seeded OHLCV price data for any set of
symbols. It is primarily used for unit tests and offline demos where live
market data is unavailable, but it also powers the
:class:`~quant_trading.data.providers.DataProvider` implementation
:class:`SyntheticDataProvider`.

Examples:
    Generate a small synthetic dataset and inspect it::

        from quant_trading.data.synthetic import create_synthetic_data

        data = create_synthetic_data(["AAPL"], days=10, seed=42)
        assert "AAPL" in data
        assert list(data["AAPL"].columns) == ["open", "high", "low", "close", "volume"]
        assert len(data["AAPL"]) == 10

    Wrap generated data in a provider and fetch it back::

        from quant_trading.data.synthetic import create_synthetic_provider

        provider = create_synthetic_provider(["AAPL"], days=5)
        result = provider.fetch(["AAPL"])
        assert result.is_success
        assert "AAPL" in result.data
"""

from datetime import datetime

import numpy as np
import pandas as pd

from quant_trading.data.providers import DataProvider, FetchResult, MarketData

DEFAULT_SEED = 42


def create_synthetic_data(
    symbols: list[str],
    days: int = 100,
    seed: int = DEFAULT_SEED,
    end_date: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Create deterministic synthetic price data (seeded random walk).

    Each symbol is generated independently as a geometric random walk with
    a small positive drift. The open/high/low columns are jittered around the
    close, and volume is drawn from a uniform range. Because the numpy global
    RNG is seeded, calling this function twice with the same arguments
    produces identical output.

    Args:
        symbols: List of symbol names to generate.
        days: Number of days of data to generate per symbol.
        seed: Random seed for reproducibility. Defaults to 42.
        end_date: End date for the data range. Defaults to ``datetime.now()``.

    Returns:
        Dictionary mapping each symbol to a :class:`pandas.DataFrame` indexed
        by business day with ``open``, ``high``, ``low``, ``close``, and
        ``volume`` columns.

    Examples:
        >>> from quant_trading.data.synthetic import create_synthetic_data
        >>> data = create_synthetic_data(["AAPL"], days=5, seed=42)
        >>> "AAPL" in data
        True
        >>> len(data["AAPL"])
        5
        >>> list(data["AAPL"].columns)
        ['open', 'high', 'low', 'close', 'volume']
        >>> data2 = create_synthetic_data(["AAPL"], days=5, seed=42)
        >>> float(data["AAPL"]["close"].iloc[0]) == float(data2["AAPL"]["close"].iloc[0])
        True
    """
    np.random.seed(seed)
    end = end_date or datetime.now()
    dates = pd.date_range(end=end, periods=days, freq="D")
    data = {}

    for symbol in symbols:
        returns = np.random.normal(0.0005, 0.02, days)
        prices = 100 * np.exp(np.cumsum(returns))

        df = pd.DataFrame(
            {
                "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
                "high": prices * (1 + np.random.uniform(0, 0.01, days)),
                "low": prices * (1 - np.random.uniform(0, 0.01, days)),
                "close": prices,
                "volume": np.random.randint(1000000, 10000000, days),
            },
            index=dates,
        )

        data[symbol] = df

    return data


class SyntheticDataProvider(DataProvider):
    """Data provider serving pre-generated synthetic data.

    Wraps a symbol-keyed mapping of :class:`pandas.DataFrame` objects (as
    produced by :func:`create_synthetic_data`) behind the
    :class:`~quant_trading.data.providers.DataProvider` interface. Symbols
    not present in the mapping are reported as missing rather than erroring.

    Attributes:
        _data: Symbol-keyed OHLCV DataFrames.
        _name: Provider identifier.

    Examples:
        >>> from quant_trading.data.synthetic import create_synthetic_provider
        >>> provider = create_synthetic_provider(["AAPL"], days=5)
        >>> provider.name
        'synthetic'
        >>> result = provider.fetch(["AAPL"])
        >>> result.is_success
        True
        >>> result = provider.fetch(["MISSING"])
        >>> result.has_missing
        True
    """

    def __init__(self, data: dict[str, pd.DataFrame], name: str = "synthetic"):
        """Initialize the provider with pre-generated data.

        Args:
            data: Symbol-keyed OHLCV DataFrames to serve.
            name: Provider identifier. Defaults to ``"synthetic"``.
        """
        self._data = data
        self._name = name

    @property
    def name(self) -> str:
        """Return the provider name.

        Returns:
            The provider identifier set at construction time.
        """
        return self._name

    def fetch(
        self,
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        """Fetch synthetic data for the requested symbols.

        Each requested symbol is looked up in the internal data map. When the
        symbol is present, its DataFrame is filtered to the requested
        ``[start, end]`` window and wrapped in a :class:`MarketData` object.
        Unknown symbols are appended to the result's ``missing`` list.

        Args:
            symbols: Tickers to fetch.
            start: Optional inclusive start of the requested window.
            end: Optional inclusive end of the requested window.
            interval: Bar interval (ignored; synthetic data is daily).

        Returns:
            A :class:`FetchResult` with successful data and missing symbols.
        """
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
        """Fetch the latest synthetic data for the requested symbols.

        Equivalent to calling :meth:`fetch` with no date window.

        Args:
            symbols: Tickers to fetch.

        Returns:
            A :class:`FetchResult` with successful data and missing symbols.
        """
        return self.fetch(symbols)


def create_synthetic_provider(
    symbols: list[str],
    days: int = 100,
    seed: int = DEFAULT_SEED,
    end_date: datetime | None = None,
) -> SyntheticDataProvider:
    """Create a :class:`SyntheticDataProvider` with freshly generated data.

    Convenience wrapper around :func:`create_synthetic_data` that returns a
    ready-to-use provider.

    Args:
        symbols: Tickers to generate data for.
        days: Number of days of data to generate per symbol.
        seed: Random seed for reproducibility. Defaults to 42.
        end_date: End date for the data range. Defaults to ``datetime.now()``.

    Returns:
        A :class:`SyntheticDataProvider` serving the generated data.

    Examples:
        >>> from quant_trading.data.synthetic import create_synthetic_provider
        >>> provider = create_synthetic_provider(["AAPL", "MSFT"], days=5)
        >>> provider.name
        'synthetic'
        >>> result = provider.fetch(["AAPL", "MSFT"])
        >>> result.is_success
        True
    """
    data = create_synthetic_data(symbols, days=days, seed=seed, end_date=end_date)
    return SyntheticDataProvider(data)
