"""Tests for the regime detector."""

import numpy as np
import pandas as pd

from quant_trading.regime import (
    Regime,
    RegimeDetector,
    RegimeResult,
    RegimeSegment,
    detect_regimes,
)


def _make_series(n: int = 100, trend: float = 0.0, vol: float = 0.01, seed: int = 0) -> pd.Series:
    """Build a synthetic price series of length n with given trend and vol."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=trend, scale=vol, size=n - 1)
    prices = 100.0 * np.cumprod(1 + returns)
    prices = np.concatenate([[100.0], prices])
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(prices, index=dates)


def test_regime_detector_defaults():
    detector = RegimeDetector()
    assert detector.window == 20
    assert detector.vol_threshold == 0.0
    assert detector.return_threshold == 0.0
    assert detector.periods_per_year == 252


def test_detect_regimes_returns_result():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=42)
    result = detect_regimes(prices, window=20)

    assert isinstance(result, RegimeResult)
    assert result.n_segments >= 1
    assert isinstance(result.current_regime, Regime)
    assert result.total_volatility >= 0.0
    assert isinstance(result.total_return_pct, float)


def test_detect_regimes_up_series_is_bull():
    prices = _make_series(n=150, trend=0.003, vol=0.005, seed=1)
    result = detect_regimes(prices, window=30)

    assert result.n_segments >= 1
    assert result.total_return_pct > 0
    bull_count = sum(
        1 for r in result.regimes if r in (Regime.BULL_LOW_VOL, Regime.BULL_HIGH_VOL)
    )
    assert bull_count >= 1


def test_detect_regimes_down_series_is_bear():
    prices = _make_series(n=150, trend=-0.003, vol=0.005, seed=2)
    result = detect_regimes(prices, window=30)

    assert result.n_segments >= 1
    assert result.total_return_pct < 0
    bear_count = sum(
        1 for r in result.regimes if r in (Regime.BEAR_LOW_VOL, Regime.BEAR_HIGH_VOL)
    )
    assert bear_count >= 1


def test_detect_regimes_sideways_series():
    prices = _make_series(n=150, trend=0.0, vol=0.008, seed=3)
    result = detect_regimes(prices, window=30)

    assert result.n_segments >= 1
    assert abs(result.total_return_pct) < 15.0
    sideways_count = sum(
        1
        for r in result.regimes
        if r in (Regime.SIDEWAYS_LOW_VOL, Regime.SIDEWAYS_HIGH_VOL)
    )
    assert sideways_count >= 1


def test_detect_regimes_label_set():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=4)
    result = detect_regimes(prices, window=20)

    valid = {
        Regime.BULL_LOW_VOL,
        Regime.BULL_HIGH_VOL,
        Regime.BEAR_LOW_VOL,
        Regime.BEAR_HIGH_VOL,
        Regime.SIDEWAYS_LOW_VOL,
        Regime.SIDEWAYS_HIGH_VOL,
    }
    for regime in result.regimes:
        assert regime in valid


def test_detect_regimes_empty_input_returns_empty_result():
    result = detect_regimes(pd.Series([100.0]), window=20)
    assert isinstance(result, RegimeResult)
    assert result.n_segments == 0
    assert result.current_regime == Regime.UNKNOWN


def test_detect_regimes_non_series_input_converted():
    prices = _make_series(n=80, trend=0.001, vol=0.01, seed=5)
    result = detect_regimes(pd.Series(prices.values), window=20)
    assert result.n_segments >= 1


def test_detect_regimes_deterministic_same_seed():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=6)
    a = detect_regimes(prices, window=20)
    b = detect_regimes(prices, window=20)

    assert a.n_segments == b.n_segments
    assert a.current_regime == b.current_regime
    assert a.total_volatility == b.total_volatility


def test_detect_regimes_explicit_thresholds():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=7)
    result = detect_regimes(
        prices, window=20, vol_threshold=0.1, return_threshold=0.05
    )
    assert result.n_segments >= 1


def test_regime_segment_to_dict():
    seg = RegimeSegment(
        regime=Regime.BULL_LOW_VOL,
        start=pd.Timestamp("2024-01-01"),
        end=pd.Timestamp("2024-01-31"),
        start_index=0,
        end_index=20,
        volatility=0.1,
        return_pct=5.0,
    )
    d = seg.to_dict()
    assert d["regime"] == "bull_low_vol"
    assert d["volatility"] == 0.1
    assert d["return_pct"] == 5.0


def test_regime_result_to_dataframe_has_rows():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=8)
    result = detect_regimes(prices, window=20)
    df = result.to_dataframe()
    assert len(df) == result.n_segments
    assert "regime" in df.columns


def test_regime_result_summary_contains_keys():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=9)
    result = detect_regimes(prices, window=20)
    summary = result.summary()
    assert summary["n_segments"] == result.n_segments
    assert "current_regime" in summary
    assert "regime_counts" in summary