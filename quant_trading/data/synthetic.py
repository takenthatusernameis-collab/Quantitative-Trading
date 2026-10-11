"""Synthetic data generation for testing and offline examples."""

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

    Args:
        symbols: List of symbol names.
        days: Number of days of data to generate.
        seed: Random seed for reproducibility (default: 42).
        end_date: End date for the data range (default: now).

    Returns:
        Dictionary mapping symbols to DataFrames with OHLCV data.
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
    """Data provider serving pre-generated synthetic data."""

    def __init__(self, data: dict[str, pd.DataFrame], name: str = "synthetic"):
        self._data = data
        self._name = name

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


def create_synthetic_provider(
    symbols: list[str],
    days: int = 100,
    seed: int = DEFAULT_SEED,
    end_date: datetime | None = None,
) -> SyntheticDataProvider:
    """Convenience function to create a SyntheticDataProvider with generated data."""
    data = create_synthetic_data(symbols, days=days, seed=seed, end_date=end_date)
    return SyntheticDataProvider(data)