"""Offline unit tests for YFinanceProvider (yfinance calls mocked)."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quant_trading.data.yfinance_provider import YFinanceProvider


def _hist_df():
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    return pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0],
            "High": [1.5, 2.5, 3.5],
            "Low": [0.5, 1.5, 2.5],
            "Close": [1.2, 2.2, 3.2],
            "Volume": [100, 200, 300],
        },
        index=idx,
    )


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.info = {"currency": "USD", "exchange": "NMS"}

    def history(self, start=None, end=None, interval="1d"):
        FakeTicker.last_history_kwargs = {"start": start, "end": end, "interval": interval}
        FakeTicker.history_call_count = getattr(FakeTicker, "history_call_count", 0) + 1
        if self.symbol == "EMPTY":
            return pd.DataFrame()
        if self.symbol == "BAD":
            raise ValueError("boom")
        return _hist_df()


def _fake_yf():
    m = MagicMock()
    m.Ticker.side_effect = lambda s: FakeTicker(s)
    m.download.return_value = None
    return m


def test_name_and_init(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path), cache_ttl_hours=2.0)
    assert p.name == "yfinance"
    assert os.path.isdir(str(tmp_path))


def test_cache_key_order_independent():
    p = YFinanceProvider(cache_dir="")
    a = p._cache_key(["MSFT", "AAPL"], None, None, "1d")
    b = p._cache_key(["AAPL", "MSFT"], None, None, "1d")
    assert a == b
    assert "AAPL,MSFT" in a


def test_fetch_success_and_missing_and_error(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch(["AAPL", "EMPTY", "BAD"])
    assert "AAPL" in res.data
    assert "EMPTY" in res.missing
    assert "BAD" in res.errors
    df = res.data["AAPL"].data
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_fetch_cache_roundtrip(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    p.fetch(["AAPL"])
    # second fetch should load from cache (no yf call needed)
    p2 = YFinanceProvider(cache_dir=str(tmp_path))
    p2._yf = MagicMock()  # should not be called
    r2 = p2.fetch(["AAPL"])
    assert "AAPL" in r2.data
    p2._yf.Ticker.assert_not_called()


def test_fetch_latest(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch_latest(["AAPL"])
    assert "AAPL" in res.data


def test_parse_download_multi_and_single():
    p = YFinanceProvider(cache_dir="")
    # empty
    r = p._parse_download(None, ["AAPL"])
    assert "AAPL" in r.missing
    # single (non-multiindex)
    hist = _hist_df()
    hist.columns = [c.lower() for c in hist.columns]
    r2 = p._parse_download(hist, ["AAPL"])
    assert "AAPL" in r2.data


def test_group_cache_key():
    p = YFinanceProvider(cache_dir="")
    k = p._group_cache_key(["AAPL"], None, None, "1d")
    assert k.startswith("yfinance_group_")


def test_slice_group_result():
    p = YFinanceProvider(cache_dir="")
    from quant_trading.data.providers import FetchResult, MarketData

    g = FetchResult()
    g.data["AAPL"] = MarketData(
        symbol="AAPL", data=_hist_df(), source="yfinance", fetched_at=datetime.now()
    )
    g.errors["BAD"] = ValueError("x")
    sliced = p._slice_group_result(g, ["AAPL", "BAD", "MISS"])
    assert "AAPL" in sliced.data
    assert "BAD" in sliced.errors
    assert "MISS" in sliced.missing


def test_is_cache_valid(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    path = os.path.join(str(tmp_path), "x.pkl")
    assert not p._is_cache_valid(path)
    with open(path, "wb") as f:
        import pickle

        pickle.dump("x", f)
    assert p._is_cache_valid(path)


def test_load_cache_invalid(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    path = os.path.join(str(tmp_path), "bad.pkl")
    with open(path, "wb") as f:
        f.write(b"not pickle")
    assert p._load_cache(path) is None


def test_parse_download_multiindex_columns():
    p = YFinanceProvider(cache_dir="")
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    # MultiIndex (Ticker, Field)
    cols = pd.MultiIndex.from_product([["AAPL"], ["Open", "High", "Low", "Close", "Volume"]])
    df = pd.DataFrame([[1, 2, 0.5, 1.5, 100], [2, 3, 1.5, 2.5, 200]], index=idx, columns=cols)
    r = p._parse_download(df, ["AAPL"])
    assert "AAPL" in r.data
    assert list(r.data["AAPL"].data.columns) == ["open", "high", "low", "close", "volume"]


def test_parse_download_multiindex_missing_symbol():
    p = YFinanceProvider(cache_dir="")
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = pd.MultiIndex.from_product([["AAPL"], ["Open", "High", "Low", "Close", "Volume"]])
    df = pd.DataFrame([[1, 2, 0.5, 1.5, 100], [2, 3, 1.5, 2.5, 200]], index=idx, columns=cols)
    r = p._parse_download(df, ["AAPL", "TSLA"])
    assert "AAPL" in r.data
    assert "TSLA" in r.missing


def test_parse_download_multiindex_empty_after_dropna():
    p = YFinanceProvider(cache_dir="")
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = pd.MultiIndex.from_product([["AAPL"], ["Open", "High", "Low", "Close", "Volume"]])
    df = pd.DataFrame([[float("nan")] * 5, [float("nan")] * 5], index=idx, columns=cols)
    r = p._parse_download(df, ["AAPL"])
    assert "AAPL" in r.missing
    assert "AAPL" not in r.data


def test_parse_download_single_empty():
    p = YFinanceProvider(cache_dir="")
    hist = _hist_df()
    hist = hist * float("nan")
    r = p._parse_download(hist, ["AAPL"])
    assert "AAPL" in r.missing


def test_fetch_many_via_provider(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    yf = _fake_yf()
    p._yf = yf

    # Use download path
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    frames = {}
    for sym in ["AAPL", "MSFT"]:
        df = pd.DataFrame(
            {
                "Open": [1.0, 2.0, 3.0],
                "High": [1.5, 2.5, 3.5],
                "Low": [0.5, 1.5, 2.5],
                "Close": [1.2, 2.2, 3.2],
                "Volume": [100, 200, 300],
            },
            index=idx,
        )
        frames[sym] = df
    # Build multiindex
    pieces = [frames[s] for s in ["AAPL", "MSFT"]]
    multi = pd.concat(pieces, axis=1, keys=["AAPL", "MSFT"], names=["Ticker", "Price"])
    yf.download.return_value = multi

    from datetime import datetime

    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    reqs = [
        {"symbols": ["AAPL"], "start": start, "end": end, "interval": "1d"},
        {"symbols": ["MSFT"], "start": start, "end": end, "interval": "1d"},
    ]
    res = p.fetch_many(reqs)
    # Each request gets its own result
    assert len(res) == 2
    # Should have made download call
    assert yf.download.called


def test_fetch_many_group_exception_records_errors(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    yf = _fake_yf()
    yf.download.side_effect = ValueError("boom")
    p._yf = yf

    reqs = [{"symbols": ["AAPL", "BAD"], "start": None, "end": None, "interval": "1d"}]
    res = p.fetch_many(reqs)
    # Get the single result
    result = next(iter(res.values()))
    assert "AAPL" in result.errors
    assert "BAD" in result.errors
    assert isinstance(result.errors["AAPL"], ValueError)


def test_get_yf_import_error():
    p = YFinanceProvider(cache_dir="")
    with patch("builtins.__import__", side_effect=ImportError("no")), pytest.raises(ImportError):
        p._get_yf()
    # reset
    p._yf = None


def test_fetch_with_dates_and_interval(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    res = p.fetch(["AAPL"], start=start, end=end, interval="1h")
    assert "AAPL" in res.data
    # Verify history called with correct params
    assert FakeTicker.history_call_count >= 1
    call_kwargs = FakeTicker.last_history_kwargs
    assert call_kwargs.get("start") == start
    assert call_kwargs.get("end") == end
    assert call_kwargs.get("interval") == "1h"


def test_fetch_normalizes_columns(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch(["AAPL"])
    df = res.data["AAPL"].data
    # All lowercase with underscores
    for col in df.columns:
        assert col == col.lower()
        assert " " not in col


def test_fetch_missing_data_records_in_missing(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch(["EMPTY"])
    assert "EMPTY" in res.missing
    assert "EMPTY" not in res.data
    assert "EMPTY" not in res.errors


def test_fetch_exception_records_in_errors(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch(["BAD"])
    assert "BAD" in res.errors
    assert isinstance(res.errors["BAD"], Exception)
    assert "BAD" not in res.data
    assert "BAD" not in res.missing


def test_fetch_multiple_symbols_mixed(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch(["AAPL", "MSFT", "EMPTY", "BAD"])
    assert "AAPL" in res.data
    assert "MSFT" in res.data
    assert "EMPTY" in res.missing
    assert "BAD" in res.errors


def test_cache_expiration(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path), cache_ttl_hours=0.001)  # very short TTL
    p._yf = _fake_yf()
    p.fetch(["AAPL"])
    # Force cache to be old
    import time

    key = p._cache_key(["AAPL"], None, None, "1d")
    path = p._cache_path(key)
    old_time = time.time() - 3600  # 1 hour ago
    os.utime(path, (old_time, old_time))
    # Should not use cache
    p2 = YFinanceProvider(cache_dir=str(tmp_path), cache_ttl_hours=0.001)
    p2._yf = _fake_yf()
    r2 = p2.fetch(["AAPL"])
    assert "AAPL" in r2.data
    # Ticker should be called again since cache expired
    assert p2._yf.Ticker.called


def test_fetch_without_cache_dir():
    p = YFinanceProvider(cache_dir="")
    p._yf = _fake_yf()
    res = p.fetch(["AAPL"])
    assert "AAPL" in res.data


def test_fetch_metadata(tmp_path):
    p = YFinanceProvider(cache_dir=str(tmp_path))
    p._yf = _fake_yf()
    res = p.fetch(["AAPL"])
    md = res.data["AAPL"].metadata
    assert md["currency"] == "USD"
    assert md["exchange"] == "NMS"


def test_parse_download_multiindex_single_field_series():
    p = YFinanceProvider(cache_dir="")
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = pd.MultiIndex.from_tuples([("AAPL", "Close")])
    df = pd.DataFrame([[1.5], [2.5]], index=idx, columns=cols)
    r = p._parse_download(df, ["AAPL"])
    assert "AAPL" in r.data
    assert list(r.data["AAPL"].data.columns) == ["close"]
