"""Offline tests for YFinanceProvider.fetch_many and DataManager delegation.

These tests inject a ``FakeYf`` that mimics the column structure produced by
``yfinance.download(..., group_by="ticker")`` (a MultiIndex of
``(ticker, field)`` columns), so the batching logic can be verified without
any network access.
"""

import importlib.util
import os
import pickle
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest
import requests

from quant_trading.data.providers import DataManager, DataProvider, FetchResult, MarketData
from quant_trading.data.yfinance_provider import AlphaVantageProvider, YFinanceProvider


# Optional dependencies used by some tests. Tests that require them are
# skipped (not failed) when the dependency is unavailable so the suite is
# deterministic in any environment without network or extra packages.
def _module_available(name: str) -> bool:
    """Return True if a top-level module can be imported."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


_HAS_YFINANCE = _module_available("yfinance")

skip_if_no_yfinance = pytest.mark.skipif(
    not _HAS_YFINANCE, reason="yfinance is not installed"
)

pytestmark = skip_if_no_yfinance

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

    def download(
        self,
        tickers=None,
        start=None,
        end=None,
        interval="1d",
        group_by="column",
        progress=True,
        **_kwargs,
    ):
        tickers = list(tickers)
        self.download_calls.append(
            {
                "tickers": tickers,
                "start": start,
                "end": end,
                "interval": interval,
                "group_by": group_by,
            }
        )
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
        {
            "symbols": ["AAPL"],
            "start": datetime(2024, 1, 1),
            "end": datetime(2024, 1, 10),
            "interval": "1d",
        },
        {
            "symbols": ["MSFT"],
            "start": datetime(2024, 2, 1),
            "end": datetime(2024, 2, 10),
            "interval": "1d",
        },
    ]
    results = provider.fetch_many(requests)

    assert len(provider._yf.download_calls) == 2
    assert len(results) == 2
    keys = {
        provider._request_key(["AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 10), "1d"),
        provider._request_key(["MSFT"], datetime(2024, 2, 1), datetime(2024, 2, 10), "1d"),
    }
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


# ---------------------------------------------------------------------------
# Tests covering YFinanceProvider offline helpers and the (monkeypatched)
# fetch / fetch_latest paths. These exercise the pure cache helpers
# (_cache_key, _cache_path, _is_cache_valid, _load_cache, _save_cache),
# _parse_download branching, _slice_group_result partitioning, and the
# per-symbol fetch loop via a lightweight fake ``yfinance.Ticker`` stand-in.
# ---------------------------------------------------------------------------


class FakeTicker:
    """Stand-in for a ``yfinance.Ticker`` instance returned by ``_get_yf``."""

    def __init__(self, hist_df=None, info=None, error=None):
        self._hist = hist_df
        self._err = error
        self.info = info if info is not None else {}
        self.history_calls: list[dict] = []

    def history(self, start=None, end=None, interval="1d"):
        self.history_calls.append({"start": start, "end": end, "interval": interval})
        if self._err is not None:
            raise self._err
        return self._hist if self._hist is not None else pd.DataFrame()


class FakeTickerYf:
    """Stand-in for the ``yfinance`` module exposing ``Ticker``.

    Unlike ``FakeYf`` (which mimics ``yfinance.download``), this fake mirrors
    the ``yf.Ticker(symbol).history(...)`` surface used by ``YFinanceProvider.fetch``.
    """

    def __init__(self, symbol_dfs=None, error_symbols=None, infos=None):
        self._dfs = symbol_dfs or {}
        self._errs = set(error_symbols or [])
        self._infos = infos or {}
        self.ticker_calls: list[str] = []

    def Ticker(self, symbol):
        self.ticker_calls.append(symbol)
        return FakeTicker(
            hist_df=self._dfs.get(symbol),
            info=self._infos.get(symbol, {}),
            error=RuntimeError(f"error fetching {symbol}") if symbol in self._errs else None,
        )


def _make_market_data(symbol: str, start: datetime, end: datetime) -> MarketData:
    return MarketData(
        symbol=symbol,
        data=_make_frame(symbol, start, end),
        source="yfinance",
        fetched_at=datetime.now(),
    )


def test_get_yf_lazy_import_success():
    provider = YFinanceProvider(cache_dir=None)
    yf = provider._get_yf()
    assert yf is not None
    import yfinance

    assert yf is yfinance


# This test asserts the lazy import succeeds, so it is only meaningful when
# yfinance is installed; skip instead of failing when it is absent.
test_get_yf_lazy_import_success = pytest.mark.skipif(
    not _module_available("yfinance"),
    reason="yfinance is not installed",
)(test_get_yf_lazy_import_success)


def test_get_yf_raises_when_yfinance_unavailable(monkeypatch):
    provider = YFinanceProvider(cache_dir=None)
    monkeypatch.setitem(sys.modules, "yfinance", None)
    with pytest.raises(ImportError, match="yfinance is not installed"):
        provider._get_yf()


def test_cache_key_is_deterministic():
    provider = YFinanceProvider(cache_dir=None)
    key = provider._cache_key(["MSFT", "AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 15), "1d")
    assert key == "yfinance_AAPL,MSFT_2024-01-01T00:00:00_2024-01-15T00:00:00_1d.pkl"
    key2 = provider._cache_key(["AAPL"], None, None, "1d")
    assert key2 == "yfinance_AAPL_none_none_1d.pkl"


def test_cache_path_joins_cache_dir(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    assert provider._cache_path("foo.pkl") == os.path.join(str(tmp_path), "foo.pkl")


def test_is_cache_valid_no_file(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    assert provider._is_cache_valid(str(tmp_path / "missing.pkl")) is False


def test_is_cache_valid_fresh(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    p = tmp_path / "fresh.pkl"
    p.write_text("x")
    assert provider._is_cache_valid(str(p)) is True


def test_is_cache_valid_expired_with_zero_ttl(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path), cache_ttl_hours=0.0)
    p = tmp_path / "old.pkl"
    p.write_text("x")
    assert provider._is_cache_valid(str(p)) is False


def test_load_cache_missing_file_returns_none(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    assert provider._load_cache(str(tmp_path / "nope.pkl")) is None


def test_load_cache_invalid_type_returns_none(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    p = tmp_path / "bad.pkl"
    with open(p, "wb") as f:
        pickle.dump("not-a-fetchresult", f)
    assert provider._load_cache(str(p)) is None


def test_load_cache_corrupt_pickle_returns_none(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    p = tmp_path / "corrupt.pkl"
    p.write_bytes(b"not a pickle")
    assert provider._load_cache(str(p)) is None


def test_save_cache_roundtrip(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 15)
    result = FetchResult()
    result.data["AAPL"] = _make_market_data("AAPL", start, end)
    key = provider._cache_key(["AAPL"], start, end, "1d")
    provider._save_cache(provider._cache_path(key), result)
    loaded = provider._load_cache(provider._cache_path(key))
    assert loaded is not None
    assert "AAPL" in loaded.data


def test_save_cache_error_is_swallowed(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    result = FetchResult()
    bad_path = str(tmp_path / "missing_subdir" / "cache.pkl")
    provider._save_cache(bad_path, result)


def test_parse_download_none_df_returns_missing():
    provider = YFinanceProvider(cache_dir=None)
    result = provider._parse_download(None, ["AAPL"])
    assert result.missing == ["AAPL"]
    assert not result.data


def test_parse_download_empty_df_returns_missing():
    provider = YFinanceProvider(cache_dir=None)
    result = provider._parse_download(pd.DataFrame(), ["AAPL", "MSFT"])
    assert set(result.missing) == {"AAPL", "MSFT"}
    assert not result.data


def test_parse_download_multiindex_symbol_all_nan_is_missing():
    provider = YFinanceProvider(cache_dir=None)
    idx = pd.date_range("2024-01-01", periods=3)
    cols = pd.MultiIndex.from_tuples(
        [("AAPL", "Open"), ("AAPL", "Close")], names=["Ticker", "Price"]
    )
    df = pd.DataFrame([[None, None], [None, None], [None, None]], index=idx, columns=cols)
    result = provider._parse_download(df, ["AAPL"])
    assert "AAPL" in result.missing
    assert not result.data


def test_parse_download_non_multiindex_with_data():
    provider = YFinanceProvider(cache_dir=None)
    idx = pd.date_range("2024-01-01", periods=3)
    df = pd.DataFrame({"Open": [1, 2, 3], "Close": [4, 5, 6]}, index=idx)
    result = provider._parse_download(df, ["AAPL"])
    assert "AAPL" in result.data
    assert not result.missing


def test_parse_download_non_multiindex_empty_after_dropna():
    provider = YFinanceProvider(cache_dir=None)
    idx = pd.date_range("2024-01-01", periods=3)
    df = pd.DataFrame({"Open": [None, None, None], "Close": [None, None, None]}, index=idx)
    result = provider._parse_download(df, ["AAPL", "MSFT"])
    assert set(result.missing) == {"AAPL", "MSFT"}


def test_slice_group_result_partitions_data_errors_missing():
    provider = YFinanceProvider(cache_dir=None)
    group = FetchResult()
    group.data["AAPL"] = MarketData(
        symbol="AAPL",
        data=pd.DataFrame({"close": [1.0]}),
        source="yfinance",
        fetched_at=datetime.now(),
    )
    group.errors["MSFT"] = ValueError("boom")
    group.missing = ["TSLA"]
    sliced = provider._slice_group_result(group, ["AAPL", "MSFT", "TSLA"])
    assert "AAPL" in sliced.data
    assert "MSFT" in sliced.errors
    assert "TSLA" in sliced.missing
    assert set(sliced.data) | set(sliced.errors) | set(sliced.missing) == {
        "AAPL",
        "MSFT",
        "TSLA",
    }


def test_fetch_success_no_cache():
    provider = YFinanceProvider(cache_dir=None)
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 15)
    provider._yf = FakeTickerYf(symbol_dfs={"AAPL": _make_frame("AAPL", start, end)})
    result = provider.fetch(["AAPL"], start=start, end=end, interval="1d")
    assert "AAPL" in result.data
    md = result.data["AAPL"]
    assert md.source == "yfinance"
    assert set(md.metadata) == {"info", "currency", "exchange"}
    assert provider._yf.ticker_calls == ["AAPL"]


def test_fetch_missing_symbol_returns_missing():
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = FakeTickerYf(symbol_dfs={})
    result = provider.fetch(["AAPL"])
    assert "AAPL" in result.missing
    assert not result.data


def test_fetch_error_captured():
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = FakeTickerYf(error_symbols={"AAPL"})
    result = provider.fetch(["AAPL"])
    assert "AAPL" in result.errors
    assert isinstance(result.errors["AAPL"], RuntimeError)


def test_fetch_cache_hit_returns_cached(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 15)
    cached = FetchResult()
    cached.data["AAPL"] = _make_market_data("AAPL", start, end)
    key = provider._cache_key(["AAPL"], start, end, "1d")
    provider._save_cache(provider._cache_path(key), cached)
    provider._yf = FakeTickerYf()
    result = provider.fetch(["AAPL"], start=start, end=end, interval="1d")
    assert "AAPL" in result.data
    assert provider._yf.ticker_calls == []


def test_fetch_saves_to_cache_on_success(tmp_path):
    provider = YFinanceProvider(cache_dir=str(tmp_path))
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 15)
    provider._yf = FakeTickerYf(symbol_dfs={"AAPL": _make_frame("AAPL", start, end)})
    result = provider.fetch(["AAPL"], start=start, end=end, interval="1d")
    assert "AAPL" in result.data
    key = provider._cache_key(["AAPL"], start, end, "1d")
    cached = provider._load_cache(provider._cache_path(key))
    assert cached is not None
    assert "AAPL" in cached.data


def test_fetch_latest_delegates_to_fetch(monkeypatch):
    provider = YFinanceProvider(cache_dir=None)
    captured: dict = {}

    def fake_fetch(symbols, start=None, end=None, interval="1d"):
        captured["symbols"] = symbols
        captured["start"] = start
        captured["end"] = end
        captured["interval"] = interval
        return FetchResult()

    monkeypatch.setattr(provider, "fetch", fake_fetch)
    provider.fetch_latest(["AAPL"])
    assert captured["interval"] == "1m"
    assert captured["start"] == captured["end"] - timedelta(days=2)


# ---------------------------------------------------------------------------
# Tests for AlphaVantageProvider offline helpers (cache, _request_key)
# ---------------------------------------------------------------------------


def test_alphavantage_cache_key_is_deterministic(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    key = provider._cache_key(["MSFT", "AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 15), "1d")
    assert key == "alphavantage_AAPL,MSFT_2024-01-01T00:00:00_2024-01-15T00:00:00_1d.pkl"
    key2 = provider._cache_key(["AAPL"], None, None, "1d")
    assert key2 == "alphavantage_AAPL_none_none_1d.pkl"


def test_alphavantage_cache_path_joins_cache_dir(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    assert provider._cache_path("foo.pkl") == os.path.join(str(tmp_path), "foo.pkl")


def test_alphavantage_is_cache_valid_no_file(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    assert provider._is_cache_valid(str(tmp_path / "missing.pkl")) is False


def test_alphavantage_is_cache_valid_fresh(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    p = tmp_path / "fresh.pkl"
    p.write_text("x")
    assert provider._is_cache_valid(str(p)) is True


def test_alphavantage_is_cache_valid_expired_with_zero_ttl(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test", cache_ttl_hours=0.0)
    p = tmp_path / "old.pkl"
    p.write_text("x")
    assert provider._is_cache_valid(str(p)) is False


def test_alphavantage_load_cache_missing_file_returns_none(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    assert provider._load_cache(str(tmp_path / "nope.pkl")) is None


def test_alphavantage_load_cache_invalid_type_returns_none(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    p = tmp_path / "bad.pkl"
    with open(p, "wb") as f:
        pickle.dump("not-a-fetchresult", f)
    assert provider._load_cache(str(p)) is None


def test_alphavantage_load_cache_corrupt_pickle_returns_none(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    p = tmp_path / "corrupt.pkl"
    p.write_bytes(b"not a pickle")
    assert provider._load_cache(str(p)) is None


def test_alphavantage_save_cache_roundtrip(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 15)
    result = FetchResult()
    result.data["AAPL"] = MarketData(
        symbol="AAPL",
        data=_make_frame("AAPL", start, end),
        source="alphavantage",
        fetched_at=datetime.now(),
        metadata={},
    )
    key = provider._cache_key(["AAPL"], start, end, "1d")
    provider._save_cache(provider._cache_path(key), result)
    loaded = provider._load_cache(provider._cache_path(key))
    assert loaded is not None
    assert "AAPL" in loaded.data


def test_alphavantage_save_cache_error_is_swallowed(tmp_path):
    provider = AlphaVantageProvider(cache_dir=str(tmp_path), api_key="test")
    result = FetchResult()
    bad_path = str(tmp_path / "missing_subdir" / "cache.pkl")
    provider._save_cache(bad_path, result)  # Should not raise


def test_alphavantage_request_key_is_deterministic():
    provider = AlphaVantageProvider(api_key="test")
    key = provider._request_key(["MSFT", "AAPL"], datetime(2024, 1, 1), datetime(2024, 1, 15), "1d")
    assert key == "AAPL,MSFT|2024-01-01T00:00:00|2024-01-15T00:00:00|1d"
    key2 = provider._request_key(["AAPL"], None, None, "1d")
    assert key2 == "AAPL|none|none|1d"


# ---------------------------------------------------------------------------
# Tests for AlphaVantageProvider parsing methods (offline, no network)
# ---------------------------------------------------------------------------


def test_parse_intraday_response_no_time_series_key():
    """_parse_intraday_response returns None when no Time Series key found (line 825)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {"Meta Data": {"1. Information": "Intraday (5min)"}}
    result = provider._parse_intraday_response("AAPL", data, None, None)
    assert result is None


def test_parse_intraday_response_empty_time_series():
    """_parse_intraday_response returns None when time series is empty (line 829)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {"Time Series (5min)": {}}
    result = provider._parse_intraday_response("AAPL", data, None, None)
    assert result is None


def test_parse_intraday_response_invalid_date_format():
    """_parse_intraday_response skips records with invalid date format (lines 835-836)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (5min)": {
            "invalid-date": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
            "2024-01-01 09:30:00": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
        }
    }
    result = provider._parse_intraday_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 1  # Only valid date parsed
    assert result.index[0] == datetime(2024, 1, 1, 9, 30, 0)


def test_parse_intraday_response_start_filter():
    """_parse_intraday_response filters by start date (line 839)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (5min)": {
            "2024-01-01 09:30:00": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
            "2024-01-01 10:00:00": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. volume": "1000",
            },
        }
    }
    start = datetime(2024, 1, 1, 10, 0, 0)
    result = provider._parse_intraday_response("AAPL", data, start, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1, 10, 0, 0)


def test_parse_intraday_response_end_filter():
    """_parse_intraday_response filters by end date (line 841)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (5min)": {
            "2024-01-01 09:30:00": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
            "2024-01-01 10:00:00": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. volume": "1000",
            },
        }
    }
    end = datetime(2024, 1, 1, 9, 30, 0)
    result = provider._parse_intraday_response("AAPL", data, None, end)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1, 9, 30, 0)


def test_parse_intraday_response_no_records_after_filter():
    """_parse_intraday_response returns None when all records filtered out (line 855)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (5min)": {
            "2024-01-01 09:30:00": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
        }
    }
    start = datetime(2024, 1, 2)  # After all data
    result = provider._parse_intraday_response("AAPL", data, start, None)
    assert result is None


def test_parse_intraday_response_success():
    """_parse_intraday_response successfully parses valid data."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (5min)": {
            "2024-01-01 09:30:00": {
                "1. open": "100.0",
                "2. high": "101.0",
                "3. low": "99.0",
                "4. close": "100.5",
                "5. volume": "1000",
            },
            "2024-01-01 09:35:00": {
                "1. open": "100.5",
                "2. high": "101.5",
                "3. low": "100.0",
                "4. close": "101.0",
                "5. volume": "1500",
            },
        }
    }
    result = provider._parse_intraday_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 2
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert result["close"].iloc[0] == 100.5
    assert result["volume"].iloc[1] == 1500


def test_parse_daily_response_no_time_series():
    """_parse_daily_response returns None when no Time Series (Daily) key (line 869)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {"Meta Data": {"1. Information": "Daily Prices"}}
    result = provider._parse_daily_response("AAPL", data, None, None)
    assert result is None


def test_parse_daily_response_invalid_date_format():
    """_parse_daily_response skips records with invalid date format (lines 875-876)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (Daily)": {
            "invalid-date": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    result = provider._parse_daily_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1)


def test_parse_daily_response_start_filter():
    """_parse_daily_response filters by start date (line 879)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (Daily)": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
            "2024-01-02": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. adjusted close": "101",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    start = datetime(2024, 1, 2)
    result = provider._parse_daily_response("AAPL", data, start, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 2)


def test_parse_daily_response_end_filter():
    """_parse_daily_response filters by end date (line 881)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (Daily)": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
            "2024-01-02": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. adjusted close": "101",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    end = datetime(2024, 1, 1)
    result = provider._parse_daily_response("AAPL", data, None, end)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1)


def test_parse_daily_response_no_records_after_filter():
    """_parse_daily_response returns None when all records filtered out (line 898)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (Daily)": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    start = datetime(2024, 1, 2)
    result = provider._parse_daily_response("AAPL", data, start, None)
    assert result is None


def test_parse_daily_response_success():
    """_parse_daily_response successfully parses valid data with all fields."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Time Series (Daily)": {
            "2024-01-01": {
                "1. open": "100.0",
                "2. high": "101.0",
                "3. low": "99.0",
                "4. close": "100.5",
                "5. adjusted close": "100.3",
                "6. volume": "1000",
                "7. dividend amount": "0.5",
                "8. split coefficient": "1.0",
            },
            "2024-01-02": {
                "1. open": "100.5",
                "2. high": "101.5",
                "3. low": "100.0",
                "4. close": "101.0",
                "5. adjusted close": "100.8",
                "6. volume": "1500",
                "7. dividend amount": "0",
                "8. split coefficient": "1.0",
            },
        }
    }
    result = provider._parse_daily_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 2
    expected_cols = [
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend_amount",
        "split_coefficient",
    ]
    assert list(result.columns) == expected_cols
    assert result["adjusted_close"].iloc[0] == 100.3
    assert result["dividend_amount"].iloc[0] == 0.5


# ---------------------------------------------------------------------------
# Resilience: YFinanceProvider.fetch_many error propagation
# ---------------------------------------------------------------------------


class _DownloadErrorYf:
    """Stand-in for yfinance whose download() raises."""

    def __init__(self, exc):
        self._exc = exc
        self.download_calls: list[dict] = []

    def download(self, **kwargs):
        self.download_calls.append(kwargs)
        raise self._exc


def test_fetch_many_captures_network_error_per_symbol():
    """A network error during the batched download is captured per symbol."""
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = _DownloadErrorYf(requests.ConnectionError("network boom"))

    results = provider.fetch_many([{"symbols": ["AAPL", "MSFT"], "interval": "1d"}])

    res = next(iter(results.values()))
    assert "AAPL" in res.errors
    assert "MSFT" in res.errors
    assert isinstance(res.errors["AAPL"], requests.ConnectionError)
    assert not res.data
    assert not res.missing


def test_fetch_many_captures_generic_runtime_error_per_symbol():
    """A RuntimeError during download is captured per symbol."""
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = _DownloadErrorYf(RuntimeError("yfinance internal failure"))

    results = provider.fetch_many([{"symbols": ["AAPL"], "interval": "1d"}])

    res = next(iter(results.values()))
    assert "AAPL" in res.errors
    assert isinstance(res.errors["AAPL"], RuntimeError)


def test_fetch_many_captures_value_error_per_symbol():
    """A ValueError during download is captured per symbol."""
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = _DownloadErrorYf(ValueError("bad argument"))

    results = provider.fetch_many([{"symbols": ["AAPL"], "interval": "1d"}])

    res = next(iter(results.values()))
    assert "AAPL" in res.errors
    assert isinstance(res.errors["AAPL"], ValueError)


def test_fetch_many_empty_requests():
    """fetch_many with no requests returns an empty mapping."""
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = _DownloadErrorYf(RuntimeError("should not be called"))
    assert provider.fetch_many([]) == {}


def test_fetch_many_empty_group_result_is_missing():
    """An empty DataFrame from download marks all symbols as missing."""
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = FakeYf({})
    results = provider.fetch_many([{"symbols": ["AAPL", "MSFT"], "interval": "1d"}])
    res = next(iter(results.values()))
    assert "AAPL" in res.missing
    assert "MSFT" in res.missing
    assert not res.data
    assert not res.errors


def test_fetch_many_partial_group_result_partitions():
    """A group result with mixed data/errors/missing is sliced per request."""
    provider = YFinanceProvider(cache_dir=None)
    provider._yf = FakeYf({"AAPL": _make_frame("AAPL", datetime(2024, 1, 1), datetime(2024, 1, 5))})
    results = provider.fetch_many([{"symbols": ["AAPL", "MSFT", "TSLA"], "interval": "1d"}])
    res = next(iter(results.values()))
    assert "AAPL" in res.data
    assert "MSFT" in res.missing
    assert "TSLA" in res.missing


# ---------------------------------------------------------------------------
# Tests for AlphaVantageProvider weekly parsing methods
# ---------------------------------------------------------------------------


def test_parse_weekly_response_no_time_series():
    """_parse_weekly_response returns None when no Weekly Time Series key (line 939)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {"Meta Data": {"1. Information": "Weekly Prices"}}
    result = provider._parse_weekly_response("AAPL", data, None, None)
    assert result is None


def test_parse_weekly_response_invalid_date_format():
    """_parse_weekly_response skips records with invalid date format (lines 945-946)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Time Series": {
            "invalid-date": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
        }
    }
    result = provider._parse_weekly_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1)


def test_parse_weekly_response_start_filter():
    """_parse_weekly_response filters by start date (line 949)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Time Series": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
            "2024-01-08": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. volume": "1000",
            },
        }
    }
    start = datetime(2024, 1, 8)
    result = provider._parse_weekly_response("AAPL", data, start, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 8)


def test_parse_weekly_response_end_filter():
    """_parse_weekly_response filters by end date (line 951)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Time Series": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
            "2024-01-08": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. volume": "1000",
            },
        }
    }
    end = datetime(2024, 1, 1)
    result = provider._parse_weekly_response("AAPL", data, None, end)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1)


def test_parse_weekly_response_no_records_after_filter():
    """_parse_weekly_response returns None when all records filtered out (line 965)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Time Series": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. volume": "1000",
            },
        }
    }
    start = datetime(2024, 1, 8)
    result = provider._parse_weekly_response("AAPL", data, start, None)
    assert result is None


def test_parse_weekly_response_success():
    """_parse_weekly_response successfully parses valid data."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Time Series": {
            "2024-01-01": {
                "1. open": "100.0",
                "2. high": "101.0",
                "3. low": "99.0",
                "4. close": "100.5",
                "5. volume": "1000",
            },
            "2024-01-08": {
                "1. open": "100.5",
                "2. high": "101.5",
                "3. low": "100.0",
                "4. close": "101.0",
                "5. volume": "1500",
            },
        }
    }
    result = provider._parse_weekly_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 2
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert result["close"].iloc[0] == 100.5
    assert result["volume"].iloc[1] == 1500


def test_parse_weekly_adjusted_response_no_time_series():
    """_parse_weekly_adjusted_response returns None when no Weekly Adjusted Time Series key (line 979)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {"Meta Data": {"1. Information": "Weekly Adjusted Prices"}}
    result = provider._parse_weekly_adjusted_response("AAPL", data, None, None)
    assert result is None


def test_parse_weekly_adjusted_response_invalid_date_format():
    """_parse_weekly_adjusted_response skips records with invalid date format (lines 985-986)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Adjusted Time Series": {
            "invalid-date": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    result = provider._parse_weekly_adjusted_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1)


def test_parse_weekly_adjusted_response_start_filter():
    """_parse_weekly_adjusted_response filters by start date (line 989)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Adjusted Time Series": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
            "2024-01-08": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. adjusted close": "101",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    start = datetime(2024, 1, 8)
    result = provider._parse_weekly_adjusted_response("AAPL", data, start, None)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 8)


def test_parse_weekly_adjusted_response_end_filter():
    """_parse_weekly_adjusted_response filters by end date (line 991)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Adjusted Time Series": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
            "2024-01-08": {
                "1. open": "101",
                "2. high": "102",
                "3. low": "100",
                "4. close": "101",
                "5. adjusted close": "101",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    end = datetime(2024, 1, 1)
    result = provider._parse_weekly_adjusted_response("AAPL", data, None, end)
    assert result is not None
    assert len(result) == 1
    assert result.index[0] == datetime(2024, 1, 1)


def test_parse_weekly_adjusted_response_no_records_after_filter():
    """_parse_weekly_adjusted_response returns None when all records filtered out (line 1008)."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Adjusted Time Series": {
            "2024-01-01": {
                "1. open": "100",
                "2. high": "101",
                "3. low": "99",
                "4. close": "100",
                "5. adjusted close": "100",
                "6. volume": "1000",
                "7. dividend amount": "0",
                "8. split coefficient": "1",
            },
        }
    }
    start = datetime(2024, 1, 8)
    result = provider._parse_weekly_adjusted_response("AAPL", data, start, None)
    assert result is None


def test_parse_weekly_adjusted_response_success():
    """_parse_weekly_adjusted_response successfully parses valid data with all fields."""
    provider = AlphaVantageProvider(api_key="test")
    data = {
        "Weekly Adjusted Time Series": {
            "2024-01-01": {
                "1. open": "100.0",
                "2. high": "101.0",
                "3. low": "99.0",
                "4. close": "100.5",
                "5. adjusted close": "100.3",
                "6. volume": "1000",
                "7. dividend amount": "0.5",
                "8. split coefficient": "1.0",
            },
            "2024-01-08": {
                "1. open": "100.5",
                "2. high": "101.5",
                "3. low": "100.0",
                "4. close": "101.0",
                "5. adjusted close": "100.8",
                "6. volume": "1500",
                "7. dividend amount": "0",
                "8. split coefficient": "1.0",
            },
        }
    }
    result = provider._parse_weekly_adjusted_response("AAPL", data, None, None)
    assert result is not None
    assert len(result) == 2
    expected_cols = [
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend_amount",
        "split_coefficient",
    ]
    assert list(result.columns) == expected_cols
    assert result["adjusted_close"].iloc[0] == 100.3
    assert result["dividend_amount"].iloc[0] == 0.5
