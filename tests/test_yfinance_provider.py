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
    g.data["AAPL"] = MarketData(symbol="AAPL", data=_hist_df(), source="yfinance", fetched_at=datetime.now())
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


def test_get_yf_import_error():
    p = YFinanceProvider(cache_dir="")
    with patch("builtins.__import__", side_effect=ImportError("no")), pytest.raises(ImportError):
        p._get_yf()
    # reset
    p._yf = None
