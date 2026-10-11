"""Yahoo Finance data provider implementation."""

from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd

from .providers import DataProvider, MarketData


class YFinanceProvider(DataProvider):
    """Yahoo Finance data provider using yfinance library."""

    def __init__(self, cache_dir: str = "./data/cache"):
        self._cache_dir = cache_dir
        self._yf = None

    @property
    def name(self) -> str:
        return "yfinance"

    def _get_yf(self):
        """Lazy import yfinance."""
        if self._yf is None:
            try:
                import yfinance as yf
                self._yf = yf
            except ImportError:
                raise ImportError("yfinance is not installed. Install with: pip install yfinance")
        return self._yf

    def fetch(
        self,
        symbols: List[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: str = "1d",
    ) -> Dict[str, MarketData]:
        """Fetch market data from Yahoo Finance."""
        yf = self._get_yf()
        result = {}

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start, end=end, interval=interval)

                if hist.empty:
                    print(f"Warning: No data found for {symbol}")
                    continue

                # Standardize column names
                hist.columns = [col.lower().replace(' ', '_') for col in hist.columns]

                metadata = {
                    'info': ticker.info,
                    'currency': ticker.info.get('currency', 'USD'),
                    'exchange': ticker.info.get('exchange', 'UNKNOWN'),
                }

                result[symbol] = MarketData(
                    symbol=symbol,
                    data=hist,
                    source=self.name,
                    fetched_at=datetime.now(),
                    metadata=metadata,
                )
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                continue

        return result

    def fetch_latest(self, symbols: List[str]) -> Dict[str, MarketData]:
        """Fetch latest market data (last 1 day)."""
        from datetime import timedelta
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
        symbols: List[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: str = "1d",
    ) -> Dict[str, MarketData]:
        raise NotImplementedError("Alpha Vantage provider not yet implemented")

    def fetch_latest(self, symbols: List[str]) -> Dict[str, MarketData]:
        raise NotImplementedError("Alpha Vantage provider not yet implemented")