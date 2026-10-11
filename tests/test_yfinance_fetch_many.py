"""Offline tests for YFinanceProvider.fetch_many and DataManager delegation.

These tests inject a ``FakeYf`` that mimics the column structure produced by
``yfinance.download(..., group_by="ticker")`` (a MultiIndex of
``(ticker, field)`` columns), so the batching logic can be verified without
any network access.
"""

from datetime import datetime

import pandas as pd

from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.data.yfinance_provider import YFinanceProvider

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def _make_frame(symbol: str, start: datetime, end: datetime, price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(start=start, end=end, freq="D")
    n = len(idx)
    base = [price + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "Open": base,
            "High": [b + 1 for b in base],
            "Low": [b - 1 for b in base],
            "Close": [b + 0.5 for b in base],
            "Volume": [1000] * n,
        },
        index=idx,
    )


class FakeYf:
    """Minimal stand-in for the ``yfinance`` module's ``download`` function.

    Returns a DataFrame whose columns are a MultiIndex ``(Ticker, Field)``,
    matching ``yfinance.download(..., group_by="ticker")``. Symbols absent
    from ``frames`` are omitted (mimicking yfinance dropping a ticker that
    returned no data).
    """

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self._frames = frames
        self.download_calls: list[dict] = []

    def download(self, tickers=None, start=None, end=None, interval="1d",
                 group_by="column", progress=True, **_kwargs):
        tickers = list(tickers)
        self.download_calls.append({
            "tickers": tickers,
            "start": start,
            "end": end,
            "interval": interval,
            "group_by": group_by,
        })
        available = [t for t in tickers if t in self._frames]
        if not available:
            return pd.DataFrame()
        pieces = [self._frames[t] for t in available]
        data = pd.concat(pieces, axis=1, keys=available, names=["Ticker", "Price"])
        return data


def _provider_with_fake(frames: dict[str, pd.DataFrame]) -> YFinanceProvider:
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = FakeYf(frames)
    return provider


def test_yfinance_fetch_many_single_download_per_group():
    """Requests sharing a date range are served by one batched download."""
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    frames = {s: _make_frame(s, start, end) for s in ("AAPL", "MSFT")}
    provider = _provider_with_fake(frames)

    requests = [
        {"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"},
        {"symbols": ["MSFT"], "start": start, "end": end, "interval": "1d"},
    ]
    results = provider.fetch_many(requests)

    assert len(provider._yf.download_calls) == 1
    call = provider._yf.download_calls[0]
    assert set(call["tickers"]) == {"AAPL", "MSFT"}
    assert call["group_by"] == "ticker"
    assert len(results) == 2
    for result in results.values():
        assert isinstance(result, FetchResult)
        assert result.data
        assert not result.missing
        assert not result.errors


def test_yfinance_fetch_many_different_ranges_separate_downloads():
    """Distinct date ranges each trigger their own download call."""
    frames = {
        "AAPL": _make_frame("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 10)),
        "MSFT": _make_frame("MSFT", datetime(2024, 2, 1), datetime(2024, 2, 10)),
    }
    provider = _provider_with_fake(frames)
    requests = [
        {"symbols": ["AAPL"], "start": datetime(2024, 1, 1), "end": datetime(2024, 1, 10), "interval": "1d"},
        {"symbols": ["MSFT"], "start": datetime(2024, 2, 1), "end": datetime(2024, 2, 10), "interval": "1d"},
    ]
    results = provider.fetch_many(requests)

    assert len(provider._yf.download_calls) == 2
    assert len(results) == 2
    keys = {provider._request_key(["AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 10), "1d"),
            provider._request_key(["MSFT"], datetime(2024, 2, 1), datetime(2024, 2, 10), "1d")}
    assert set(results.keys()) == keys


def test_yfinance_fetch_many_missing_symbol():
    """Symbols absent from the download are reported as missing."""
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    frames = {"AAPL": _make_frame("AAPL", start, end)}
    provider = _provider_with_fake(frames)

    req = {"symbols": ["AAPL", "TSLA"], "start": start, "end": end, "interval": "1d"}
    results = provider.fetch_many([req])
    key = provider._request_key(["AAPL", "TSLA"], start, end, "1d")

    assert len(provider._yf.download_calls) == 1
    result = results[key]
    assert "AAPL" in result.data
    assert "TSLA" in result.missing
    assert "TSLA" not in result.data
    assert "AAPL" not in result.missing


def test_yfinance_fetch_many_disk_cache(tmp_path):
    """A second call with the same range hits the disk cache (no extra download)."""
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    frames = {"AAPL": _make_frame("AAPL", start, end)}
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    provider._yf = FakeYf(frames)

    req = {"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"}
    provider.fetch_many([req])
    assert len(provider._yf.download_calls) == 1

    provider.fetch_many([req])
    assert len(provider._yf.download_calls) == 1
    assert any("group" in p.name for p in tmp_path.glob("*.pkl"))


def test_data_manager_fetch_many_delegates_to_provider_fetch_many():
    """DataManager.fetch_many must call provider.fetch_many (not provider.fetch)."""
    class SpyProvider(DataProvider):
        def __init__(self):
            self.fetch_many_calls = 0
            self._name = "spy"

        @property
        def name(self) -> str:
            return self._name

        def fetch(self, symbols, start=None, end=None, interval="1d"):
            raise AssertionError("provider.fetch must not be called by fetch_many")

        def fetch_latest(self, symbols):
            return self.fetch(symbols)

        def fetch_many(self, requests):
            self.fetch_many_calls += 1
            out = {}
            for req in requests:
                symbols = req.get("symbols", [])
                start = req.get("start")
                end = req.get("end")
                interval = req.get("interval", "1d")
                key = self._request_key(symbols, start, end, interval)
                result = FetchResult()
                for sym in symbols:
                    result.data[sym] = MarketData(
                        symbol=sym, data=pd.DataFrame(), source=self.name, fetched_at=datetime.now()
                    )
                out[key] = result
            return out

    provider = SpyProvider()
    manager = DataManager([provider])
    requests = [{"symbols": ["AAPL"], "start": None, "end": None, "interval": "1d"}]

    results = manager.fetch_many(requests)

    assert provider.fetch_many_calls == 1
    assert set(results.keys()) == {provider._request_key(["AAPL"], None, None, "1d")}


def test_data_manager_fetch_many_caches_provider_fetch_many_result():
    """DataManager in-memory cache prevents a second provider.fetch_many call."""
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    frames = {"AAPL": _make_frame("AAPL", start, end), "MSFT": _make_frame("MSFT", start, end)}
    provider = _provider_with_fake(frames)

    requests = [
        {"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"},
        {"symbols": ["MSFT"], "start": start, "end": end, "interval": "1d"},
    ]
    manager = DataManager([provider])

    first = manager.fetch_many(requests)
    assert len(provider._yf.download_calls) == 1

    second = manager.fetch_many(requests)
    assert len(provider._yf.download_calls) == 1  # in-memory cache hit
    assert set(second.keys()) == set(first.keys())
    for key in first:
        assert second[key] is first[key]
