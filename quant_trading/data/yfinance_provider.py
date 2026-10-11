"""Yahoo Finance data provider implementation."""

from datetime import datetime

from quant_trading.utils.logging import get_logger

from .providers import DataProvider, FetchResult, MarketData

logger = get_logger(__name__)


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
                import yfinance as yf  # type: ignore[import-untyped]

                self._yf = yf
            except ImportError:
                raise ImportError("yfinance is not installed. Install with: pip install yfinance")
        return self._yf

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
        """
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

        return fetch_result

    def fetch_latest(self, symbols: list[str]) -> FetchResult:
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
        symbols: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> FetchResult:
        raise NotImplementedError("Alpha Vantage provider not yet implemented")

    def fetch_latest(self, symbols: list[str]) -> FetchResult:
        raise NotImplementedError("Alpha Vantage provider not yet implemented")
