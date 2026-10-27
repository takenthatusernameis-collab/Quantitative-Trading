"""Tests for the regime detector."""

import numpy as np
import pandas as pd
import pytest

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
    bull_count = sum(1 for r in result.regimes if r in (Regime.BULL_LOW_VOL, Regime.BULL_HIGH_VOL))
    assert bull_count >= 1


def test_detect_regimes_down_series_is_bear():
    prices = _make_series(n=150, trend=-0.003, vol=0.005, seed=2)
    result = detect_regimes(prices, window=30)

    assert result.n_segments >= 1
    assert result.total_return_pct < 0
    bear_count = sum(1 for r in result.regimes if r in (Regime.BEAR_LOW_VOL, Regime.BEAR_HIGH_VOL))
    assert bear_count >= 1


def test_detect_regimes_sideways_series():
    prices = _make_series(n=150, trend=0.0, vol=0.008, seed=3)
    result = detect_regimes(prices, window=30)

    assert result.n_segments >= 1
    assert abs(result.total_return_pct) < 15.0
    sideways_count = sum(
        1 for r in result.regimes if r in (Regime.SIDEWAYS_LOW_VOL, Regime.SIDEWAYS_HIGH_VOL)
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


def test_detect_regimes_two_bar_series_returns_empty_result():
    """A two-bar series yields a single NaN return, so no signal survives."""
    result = detect_regimes(pd.Series([100.0, 101.0]), window=20)
    assert isinstance(result, RegimeResult)
    assert result.n_segments == 0
    assert result.current_regime == Regime.UNKNOWN


def test_detect_regimes_deterministic_same_seed():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=6)
    a = detect_regimes(prices, window=20)
    b = detect_regimes(prices, window=20)

    assert a.n_segments == b.n_segments
    assert a.current_regime == b.current_regime
    assert a.total_volatility == b.total_volatility


def test_detect_regimes_explicit_thresholds():
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=7)
    result = detect_regimes(prices, window=20, vol_threshold=0.1, return_threshold=0.05)
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


def test_regime_result_to_dict():
    """RegimeResult.to_dict() is callable and returns expected keys (line 59)."""
    prices = _make_series(n=100, trend=0.001, vol=0.01, seed=10)
    result = detect_regimes(prices, window=20)
    d = result.to_dict()
    assert "segments" in d
    assert d["n_segments"] == result.n_segments
    assert d["current_regime"] == result.current_regime.value
    assert len(d["regimes"]) == len(result.regimes)


def test_regime_result_empty_to_dict_and_to_dataframe():
    """Empty RegimeResult.to_dict() (line 59) and to_dataframe() empty branch (line 70)."""
    prices = pd.Series([100.0])
    result = detect_regimes(prices, window=20)
    assert result.n_segments == 0

    d = result.to_dict()
    assert d["n_segments"] == 0
    assert d["segments"] == []
    assert d["regimes"] == []
    assert d["current_regime"] == Regime.UNKNOWN.value

    df = result.to_dataframe()
    assert df.empty


def test_detect_regimes_non_series_input_list():
    """detect() converts a non-Series (list) input to pd.Series (line 107)."""
    prices = [100.0, 101.0, 102.0, 103.0, 100.5, 101.0, 102.5, 103.0, 104.0, 105.0]
    result = detect_regimes(prices, window=3)
    assert result.n_segments >= 1


def test_detect_regimes_periods_per_year_affects_annualization():
    """Non-daily periods_per_year changes annualized volatility/thresholds."""
    prices = _make_series(n=150, trend=0.001, vol=0.01, seed=42)
    result_daily = detect_regimes(prices, window=20, periods_per_year=252)
    result_weekly = detect_regimes(prices, window=20, periods_per_year=52)

    assert result_daily.n_segments >= 1
    assert result_weekly.n_segments >= 1
    # Annualized values should differ when periods_per_year differs
    assert result_daily.total_volatility != result_weekly.total_volatility


def test_detect_regimes_periods_per_year_scales_volatility_by_sqrt():
    """The annualized volatility is scaled by the square root of the period count."""
    prices = _make_series(n=150, trend=0.001, vol=0.01, seed=42)
    result_daily = detect_regimes(prices, window=20, periods_per_year=252)
    result_weekly = detect_regimes(prices, window=20, periods_per_year=52)

    assert result_daily.total_volatility > 0.0
    assert result_daily.total_volatility == pytest.approx(
        result_weekly.total_volatility * (252 / 52) ** 0.5, rel=1e-9
    )


def test_detect_regimes_auto_thresholds_keep_labels_across_periods_per_year():
    """Auto-derived thresholds scale with the statistics, so labels do not move.

    The auto-derived thresholds are the means of the very statistics they are
    compared against and both are scaled by the same annualization factor, so
    the labelling is independent of the period count.
    """
    prices = _make_series(n=150, trend=0.001, vol=0.01, seed=42)
    result_daily = detect_regimes(prices, window=20, periods_per_year=252)
    result_weekly = detect_regimes(prices, window=20, periods_per_year=52)

    assert result_daily.regimes == result_weekly.regimes
    assert result_daily.n_segments == result_weekly.n_segments


def test_detect_regimes_explicit_thresholds_follow_periods_per_year():
    """An explicit annualized threshold is a fixed number, so labels follow it.

    The threshold stays put while the statistics it is compared against are
    rescaled, so a different period count produces a different labelling.
    """
    prices = _make_series(n=150, trend=0.001, vol=0.01, seed=42)
    result_daily = detect_regimes(
        prices, window=20, vol_threshold=0.20, return_threshold=0.05, periods_per_year=252
    )
    result_weekly = detect_regimes(
        prices, window=20, vol_threshold=0.20, return_threshold=0.05, periods_per_year=52
    )

    assert result_daily.n_segments != result_weekly.n_segments


def test_regime_detector_periods_per_year_passed_through():
    """RegimeDetector passes periods_per_year to calculations."""
    prices = _make_series(n=150, trend=0.001, vol=0.01, seed=43)
    det_daily = RegimeDetector(window=20, periods_per_year=252)
    det_weekly = RegimeDetector(window=20, periods_per_year=52)
    res_daily = det_daily.detect(prices)
    res_weekly = det_weekly.detect(prices)

    assert res_daily.total_volatility != res_weekly.total_volatility


def test_merge_segments_all_none_labels():
    """When every label is None, the loop body is skipped and `current` stays None,
    so the trailing `if current is not None` (202->206) is False and no segment
    is appended."""
    from quant_trading.regime.detector import RegimeDetector

    detector = RegimeDetector()
    prices = _make_series(n=20)
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=5).std()

    labels: list = [None] * 10
    segments = detector._merge_segments(labels, prices, returns, rolling_vol)
    assert segments == []


def test_merge_segments_normal():
    """Sanity check that a normal label list produces segments."""
    from quant_trading.regime import Regime
    from quant_trading.regime.detector import RegimeDetector

    detector = RegimeDetector()
    prices = _make_series(n=20)
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=5).std()

    labels = [Regime.BULL_LOW_VOL, Regime.BULL_LOW_VOL, Regime.BEAR_LOW_VOL]
    segments = detector._merge_segments(labels, prices, returns, rolling_vol)
    assert len(segments) == 2


def test_window_larger_than_prices():
    """When window > len(prices), rolling stats are all NaN -> all labels None -> empty result.
    However, total_return_pct should still be computed from the full price series.
    """
    prices = _make_series(n=10, seed=42)  # fixed seed for deterministic return
    result = detect_regimes(prices, window=20)  # window larger than series
    assert isinstance(result, RegimeResult)
    assert result.n_segments == 0
    assert result.current_regime == Regime.UNKNOWN
    assert result.total_volatility == 0.0
    # total_return_pct should be the actual return of the series
    expected_return = float((prices.iloc[-1] / prices.iloc[0] - 1) * 100)
    assert result.total_return_pct == expected_return


def test_all_same_prices():
    """Constant prices should produce sideways low vol regime (zero return, zero vol)."""
    prices = pd.Series([100.0] * 20, index=pd.date_range("2024-01-01", periods=20, freq="D"))
    result = detect_regimes(prices, window=5)
    assert result.n_segments == 1  # one segment for the whole series
    assert result.current_regime == Regime.SIDEWAYS_LOW_VOL
    assert abs(result.total_return_pct) < 1e-9  # essentially zero
    # volatility should be zero (or very close)
    assert result.total_volatility < 1e-9


def test_prices_with_nan():
    """Prices containing NaN values should not crash; NaNs propagate through returns."""
    # Create a series with a NaN in the middle
    prices = _make_series(n=10)
    prices.iloc[5] = np.nan
    # Should not raise
    result = detect_regimes(prices, window=5)
    assert isinstance(result, RegimeResult)
    # We don't make strong assertions about the result because NaN handling is complex,
    # but we ensure it doesn't crash and returns a valid RegimeResult.
    assert result.n_segments >= 0
    assert isinstance(result.current_regime, Regime)


def test_prices_with_inf():
    """Prices containing Inf values should not crash."""
    prices = _make_series(n=10)
    prices.iloc[5] = np.inf
    # Should not raise
    result = detect_regimes(prices, window=5)
    assert isinstance(result, RegimeResult)
    assert result.n_segments >= 0
    assert isinstance(result.current_regime, Regime)


def test_merge_segments_single_element():
    """Single element label list should produce one segment."""
    from quant_trading.regime import Regime
    from quant_trading.regime.detector import RegimeDetector

    detector = RegimeDetector()
    prices = _make_series(n=5)
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=2).std()

    labels = [Regime.BULL_LOW_VOL]
    segments = detector._merge_segments(labels, prices, returns, rolling_vol)
    assert len(segments) == 1
    assert segments[0].regime == Regime.BULL_LOW_VOL
    assert segments[0].start_index == 0
    assert segments[0].end_index == 1


def test_merge_segments_two_same():
    """Two identical labels should produce one segment."""
    from quant_trading.regime import Regime
    from quant_trading.regime.detector import RegimeDetector

    detector = RegimeDetector()
    prices = _make_series(n=5)
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=2).std()

    labels = [Regime.BULL_LOW_VOL, Regime.BULL_LOW_VOL]
    segments = detector._merge_segments(labels, prices, returns, rolling_vol)
    assert len(segments) == 1
    assert segments[0].regime == Regime.BULL_LOW_VOL
    assert segments[0].start_index == 0
    assert segments[0].end_index == 2


def test_merge_segments_two_different():
    """Two different labels should produce two segments."""
    from quant_trading.regime import Regime
    from quant_trading.regime.detector import RegimeDetector

    detector = RegimeDetector()
    prices = _make_series(n=5)
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=2).std()

    labels = [Regime.BULL_LOW_VOL, Regime.BEAR_LOW_VOL]
    segments = detector._merge_segments(labels, prices, returns, rolling_vol)
    assert len(segments) == 2
    assert segments[0].regime == Regime.BULL_LOW_VOL
    assert segments[1].regime == Regime.BEAR_LOW_VOL
    assert segments[0].end_index == segments[1].start_index == 1


def test_merge_segments_alternating():
    """Alternating labels should produce many segments."""
    from quant_trading.regime import Regime
    from quant_trading.regime.detector import RegimeDetector

    detector = RegimeDetector()
    prices = _make_series(n=11)  # 11 prices -> 10 returns, matching the 10 labels
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=2).std()

    labels = [Regime.BULL_LOW_VOL, Regime.BEAR_LOW_VOL] * 5  # 10 elements
    segments = detector._merge_segments(labels, prices, returns, rolling_vol)
    assert len(segments) == 10  # each element is its own segment
    for i, seg in enumerate(segments):
        expected_regime = Regime.BULL_LOW_VOL if i % 2 == 0 else Regime.BEAR_LOW_VOL
        assert seg.regime == expected_regime
        assert seg.start_index == i
        assert seg.end_index == i + 1


def test_segment_boundary_aligns_with_labeled_price_bars():
    """A segment spanning labels [start_idx, end_idx) covers price bars
    [start_idx + 1, end_idx], because label i derives from returns whose index is
    prices.index[1:] (pct_change drops the first bar).

    With explicit thresholds and a strictly increasing series, every label is
    BULL_LOW_VOL, so a single segment must span the whole labeled range and its
    return_pct must equal the price change across exactly those bars.
    """
    from quant_trading.regime.detector import RegimeDetector

    prices = pd.Series(
        [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        index=pd.date_range("2024-01-01", periods=6, freq="D"),
    )
    detector = RegimeDetector(window=2, vol_threshold=10.0, return_threshold=10.0)
    result = detector.detect(prices)

    assert result.n_segments == 1
    seg = result.segments[0]
    # labels[0] is NaN (window warm-up), labels[1..4] are BULL_LOW_VOL.
    assert seg.start_index == 1
    assert seg.end_index == 5
    assert seg.start == prices.index[2]  # label 1 -> price bar 2
    assert seg.end == prices.index[5]  # label 4 -> price bar 5
    assert seg.return_pct == pytest.approx((prices.iloc[5] / prices.iloc[2] - 1) * 100)


def test_segment_boundary_at_series_end():
    """The trailing segment must not index past the last price bar.

    When labels run to the end of the series (end_idx == len(labels) ==
    len(prices) - 1), the segment's end must be the last price bar and its
    return_pct must be computed against the labeled range, not past it.
    """
    from quant_trading.regime.detector import RegimeDetector

    prices = pd.Series(
        [100.0 * (1.01**i) for i in range(10)],
        index=pd.date_range("2024-01-01", periods=10, freq="D"),
    )
    detector = RegimeDetector(window=2, vol_threshold=10.0, return_threshold=10.0)
    result = detector.detect(prices)

    assert result.n_segments == 1
    seg = result.segments[0]
    # labels[0] is NaN (window warm-up); labels[1..8] are SIDEWAYS_LOW_VOL.
    assert seg.start_index == 1
    assert seg.end_index == 9
    assert seg.start == prices.index[2]  # label 1 -> price bar 2
    assert seg.end == prices.index[-1]  # label 8 -> price bar 9 (last)
    assert seg.return_pct == pytest.approx((prices.iloc[-1] / prices.iloc[2] - 1) * 100)


def test_segment_return_pct_matches_labeled_price_range():
    """return_pct must reflect the price change across the segment's labeled
    bars, not an off-by-one window of it."""
    from quant_trading.regime.detector import RegimeDetector

    prices = pd.Series(
        [100.0 + i for i in range(30)],
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )
    detector = RegimeDetector(window=2, vol_threshold=10.0, return_threshold=10.0)
    result = detector.detect(prices)

    assert result.n_segments == 1
    seg = result.segments[0]
    assert seg.start_index == 1
    assert seg.end_index == 29
    assert seg.start == prices.index[2]  # label 1 -> price bar 2
    assert seg.end == prices.index[-1]  # label 28 -> price bar 29 (last)
    assert seg.return_pct == pytest.approx((prices.iloc[-1] / prices.iloc[2] - 1) * 100)


def test_one_bar_segment_reports_own_return():
    """A single-bar segment must report that bar's own close-to-close return,
    not 0.0%, since its start and end price bars coincide."""
    from quant_trading.regime.detector import RegimeDetector

    prices = pd.Series(
        [100.0, 101.0, 102.0, 95.0, 102.0],
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )
    # vol_threshold high -> all LOW_VOL; return_threshold=1.0 isolates a single
    # BEAR bar between two BULL bars, yielding three one-bar segments.
    result = RegimeDetector(window=2, vol_threshold=50.0, return_threshold=1.0).detect(prices)

    assert result.n_segments == 3
    bull, bear, sideways = result.segments
    assert bull.regime == Regime.BULL_LOW_VOL
    assert bear.regime == Regime.BEAR_LOW_VOL
    assert sideways.regime == Regime.SIDEWAYS_LOW_VOL
    # Each one-bar segment reports that bar's own return vs its predecessor.
    assert bull.return_pct == pytest.approx((prices.iloc[2] / prices.iloc[1] - 1) * 100)
    assert bear.return_pct == pytest.approx((prices.iloc[3] / prices.iloc[2] - 1) * 100)
    assert sideways.return_pct == pytest.approx((prices.iloc[4] / prices.iloc[3] - 1) * 100)
    # Sanity: none of the one-bar segments report 0.0.
    assert all(s.return_pct != 0.0 for s in result.segments)


def test_short_series_window_larger_than_prices_returns_empty():
    prices = pd.Series(
        [100.0, 101.0, 102.0],
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )
    result = detect_regimes(prices, window=5)
    assert result.segments == []
    assert result.regimes == []
    assert result.n_segments == 0
    assert result.current_regime == Regime.UNKNOWN


def test_flat_prices_single_sideways_low_vol():
    prices = pd.Series(
        [100.0] * 30,
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )
    result = detect_regimes(prices, window=5)
    assert result.n_segments >= 1
    assert all(r == Regime.SIDEWAYS_LOW_VOL for r in result.regimes)


def test_monotonic_up_single_bull_segment():
    prices = pd.Series(
        [100.0 + i for i in range(30)],
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )
    result = detect_regimes(prices, window=5, vol_threshold=10.0, return_threshold=0.0001)
    assert result.n_segments == 1
    assert result.regimes[0] in (Regime.BULL_LOW_VOL, Regime.BULL_HIGH_VOL)


def test_monotonic_down_single_bear_segment():
    prices = pd.Series(
        [100.0 - i for i in range(30)],
        index=pd.date_range("2024-01-01", periods=30, freq="D"),
    )
    result = detect_regimes(prices, window=5, vol_threshold=10.0, return_threshold=0.0001)
    assert result.n_segments == 1
    assert result.regimes[0] in (Regime.BEAR_LOW_VOL, Regime.BEAR_HIGH_VOL)


def test_explicit_thresholds_override_auto():
    prices = _make_series(n=80, trend=0.001, vol=0.01, seed=7)
    auto = detect_regimes(prices, window=10)
    explicit = detect_regimes(prices, window=10, vol_threshold=100.0, return_threshold=100.0)
    assert auto.n_segments >= 1
    assert explicit.n_segments >= 1
    # explicit high thresholds force sideways labeling
    assert all(r in (Regime.SIDEWAYS_LOW_VOL, Regime.SIDEWAYS_HIGH_VOL) for r in explicit.regimes)


def test_single_bar_segment_at_the_first_price_bar_reports_zero_return():
    """A one-bar segment on the very first price bar has no predecessor bar.

    Its own close-to-close return is measured against the bar before it, so
    the first bar has nothing to be measured against and reports 0.0%.
    """
    detector = RegimeDetector()
    prices = _make_series(n=20)
    # A returns series that is indexed like the prices, so label 0 is the
    # first price bar rather than the second one.
    returns = pd.Series(prices.pct_change().values, index=prices.index)
    rolling_vol = returns.rolling(window=5).std()

    segment = detector._make_segment(Regime.BULL_LOW_VOL, 0, 1, prices, returns, rolling_vol)

    assert segment.regime == Regime.BULL_LOW_VOL
    assert segment.start == prices.index[0]
    assert segment.return_pct == 0.0


def test_segment_without_labeled_bars_reports_zero_return():
    """A segment that spans no labeled bar has no price range to report.

    The start and end price bars would not even exist, so the return is 0.0%
    rather than an error.
    """
    detector = RegimeDetector()
    prices = _make_series(n=20)
    returns = prices.pct_change().dropna()
    rolling_vol = returns.rolling(window=5).std()

    segment = detector._make_segment(Regime.BEAR_LOW_VOL, 3, 3, prices, returns, rolling_vol)

    assert segment.regime == Regime.BEAR_LOW_VOL
    assert segment.return_pct == 0.0
    assert segment.volatility == 0.0
