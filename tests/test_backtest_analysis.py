"""Tests for the backtest analysis helpers (regime integration)."""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.backtest import (
    BacktestRegimeAnalysis,
    analyze_regimes,
    regime_for_backtest,
)
from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics, calculate_backtest_metrics
from quant_trading.regime import Regime


def _make_result(equity: pd.Series | None = None) -> BacktestResult:
    equity = equity if equity is not None else _make_equity()
    metrics = calculate_backtest_metrics(equity)
    return BacktestResult(
        equity_curve=equity,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 3, 1),
        initial_capital=100_000.0,
        final_value=float(equity.iloc[-1]),
        total_return=float(equity.iloc[-1] - equity.iloc[0]),
        total_return_pct=float((equity.iloc[-1] / equity.iloc[0] - 1) * 100),
    )


def _make_equity(n: int = 80, trend: float = 0.001, vol: float = 0.01, seed: int = 0) -> pd.Series:
    import numpy as np

    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=trend, scale=vol, size=n - 1)
    equity = 100_000.0 * np.cumprod(1 + returns)
    equity = np.concatenate([[100_000.0], equity])
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(equity, index=dates)


def test_analyze_regimes_returns_backtest_regime_analysis():
    result = _make_result()
    analysis = analyze_regimes(result, window=20)

    assert isinstance(analysis, BacktestRegimeAnalysis)
    assert analysis.window == 20
    assert analysis.n_segments >= 1
    assert isinstance(analysis.current_regime, Regime)
    assert analysis.equity_curve is result.equity_curve


def test_analyze_regimes_uses_explicit_thresholds():
    result = _make_result()
    analysis = analyze_regimes(result, window=20, vol_threshold=0.15, return_threshold=0.05)

    assert analysis.vol_threshold == 0.15
    assert analysis.return_threshold == 0.05
    assert analysis.n_segments >= 1


def test_regime_for_backtest_returns_regime_result():
    result = _make_result()
    regime_result = regime_for_backtest(result, window=20)

    assert regime_result.n_segments >= 1
    assert regime_result.current_regime in {
        Regime.BULL_LOW_VOL,
        Regime.BULL_HIGH_VOL,
        Regime.BEAR_LOW_VOL,
        Regime.BEAR_HIGH_VOL,
        Regime.SIDEWAYS_LOW_VOL,
        Regime.SIDEWAYS_HIGH_VOL,
    }


def test_backtest_regime_analysis_to_dict_has_segments():
    result = _make_result()
    analysis = analyze_regimes(result, window=20)

    data = analysis.to_dict()
    assert data["window"] == 20
    assert data["current_regime"] == analysis.current_regime.value
    assert isinstance(data["segments"], list)
    assert len(data["segments"]) == analysis.n_segments


def test_backtest_regime_analysis_to_dataframe_matches_segments():
    result = _make_result()
    analysis = analyze_regimes(result, window=20)

    df = analysis.to_dataframe()
    assert len(df) == analysis.n_segments
    assert "regime" in df.columns


def test_backtest_regime_analysis_summary_contains_window():
    result = _make_result()
    analysis = analyze_regimes(result, window=15)

    summary = analysis.summary()
    assert summary["n_segments"] == analysis.n_segments
    assert summary["window"] == 15
    assert summary["vol_threshold"] == 0.0
    assert summary["return_threshold"] == 0.0


def test_analyze_regimes_deterministic():
    result = _make_result()
    a = analyze_regimes(result, window=20)
    b = analyze_regimes(result, window=20)

    assert a.n_segments == b.n_segments
    assert a.current_regime == b.current_regime
    assert a.result.total_volatility == b.result.total_volatility


def test_analyze_regimes_empty_equity_yields_no_segments():
    equity = pd.Series([100_000.0], index=[datetime(2024, 1, 1)])
    result = _make_result(equity=equity)

    analysis = analyze_regimes(result, window=20)
    assert analysis.n_segments == 0
    assert analysis.current_regime == Regime.UNKNOWN


def test_analyze_regimes_down_series_is_bear():
    equity = _make_equity(n=120, trend=-0.003, vol=0.005, seed=2)
    result = _make_result(equity=equity)

    analysis = analyze_regimes(result, window=30)
    assert analysis.n_segments >= 1
    bear_count = sum(
        1 for s in analysis.segments if s.regime in (Regime.BEAR_LOW_VOL, Regime.BEAR_HIGH_VOL)
    )
    assert bear_count >= 1


def test_analyze_regimes_up_series_is_bull():
    equity = _make_equity(n=120, trend=0.003, vol=0.005, seed=1)
    result = _make_result(equity=equity)

    analysis = analyze_regimes(result, window=30)
    assert analysis.n_segments >= 1
    bull_count = sum(
        1 for s in analysis.segments if s.regime in (Regime.BULL_LOW_VOL, Regime.BULL_HIGH_VOL)
    )
    assert bull_count >= 1


def test_backtest_regime_analysis_defaults():
    """BacktestRegimeAnalysis defaults to window=20 and zero thresholds."""
    result = _make_result()
    analysis = analyze_regimes(result)

    assert analysis.window == 20
    assert analysis.vol_threshold == 0.0
    assert analysis.return_threshold == 0.0


def test_backtest_regime_analysis_explicit_thresholds_persisted():
    """Explicit vol/return thresholds are stored verbatim on the dataclass."""
    result = _make_result()
    analysis = analyze_regimes(result, window=15, vol_threshold=0.25, return_threshold=0.04)

    assert analysis.window == 15
    assert analysis.vol_threshold == 0.25
    assert analysis.return_threshold == 0.04


def test_backtest_regime_analysis_segments_are_regime_segments():
    """Every segment exposed by the analysis is a RegimeSegment instance."""
    from quant_trading.regime import RegimeSegment

    result = _make_result()
    analysis = analyze_regimes(result, window=20)

    assert analysis.n_segments >= 1
    for segment in analysis.segments:
        assert isinstance(segment, RegimeSegment)


def test_backtest_regime_analysis_empty_equity():
    """A single-point equity curve yields no segments and UNKNOWN current regime."""
    equity = pd.Series([100_000.0], index=[datetime(2024, 1, 1)])
    result = _make_result(equity=equity)

    analysis = analyze_regimes(result, window=20)

    assert analysis.n_segments == 0
    assert analysis.segments == []
    assert analysis.current_regime == Regime.UNKNOWN


def test_backtest_regime_analysis_to_dict_full_payload():
    """to_dict exposes window, thresholds, regime stats and segment list."""
    result = _make_result()
    analysis = analyze_regimes(result, window=25, vol_threshold=0.12, return_threshold=0.03)

    data = analysis.to_dict()
    assert data["window"] == 25
    assert data["vol_threshold"] == 0.12
    assert data["return_threshold"] == 0.03
    assert data["current_regime"] == analysis.current_regime.value
    assert isinstance(data["total_volatility"], float)
    assert isinstance(data["total_return_pct"], float)
    assert isinstance(data["segments"], list)
    assert len(data["segments"]) == analysis.n_segments


def test_backtest_regime_analysis_summary_explicit_thresholds():
    """summary() carries the explicitly configured window and thresholds."""
    result = _make_result()
    analysis = analyze_regimes(result, window=15, vol_threshold=0.25, return_threshold=0.04)

    summary = analysis.summary()
    assert summary["window"] == 15
    assert summary["vol_threshold"] == 0.25
    assert summary["return_threshold"] == 0.04
    assert summary["n_segments"] == analysis.n_segments


def test_analyze_regimes_periods_per_year_affects_volatility():
    from quant_trading.backtest.metrics import BacktestMetrics

    metrics = BacktestMetrics()
    eq = pd.Series([100000 * (1 + 0.001 * i) for i in range(60)], index=pd.date_range("2024-01-01", periods=60))
    res = BacktestResult(
        equity_curve=eq,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=eq.index[0],
        end_date=eq.index[-1],
        initial_capital=100000,
        final_value=float(eq.iloc[-1]),
        total_return=float(eq.iloc[-1]) - 100000,
        total_return_pct=float((eq.iloc[-1] / 100000 - 1) * 100),
    )
    a = analyze_regimes(res, window=20, periods_per_year=252)
    b = analyze_regimes(res, window=20, periods_per_year=52)
    assert a.result.total_volatility != b.result.total_volatility


def test_regime_for_backtest_periods_per_year_affects_volatility():
    from quant_trading.backtest.metrics import BacktestMetrics

    metrics = BacktestMetrics()
    eq = pd.Series([100000 * (1 + 0.001 * i) for i in range(60)], index=pd.date_range("2024-01-01", periods=60))
    res = BacktestResult(
        equity_curve=eq,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=eq.index[0],
        end_date=eq.index[-1],
        initial_capital=100000,
        final_value=float(eq.iloc[-1]),
        total_return=float(eq.iloc[-1]) - 100000,
        total_return_pct=float((eq.iloc[-1] / 100000 - 1) * 100),
    )
    a = regime_for_backtest(res, window=20, periods_per_year=252)
    b = regime_for_backtest(res, window=20, periods_per_year=52)
    assert a.total_volatility != b.total_volatility


def test_analyze_regimes_periods_per_year_affects_volatility():
    metrics = BacktestMetrics()
    eq = pd.Series([100000 * (1 + 0.001 * i) for i in range(60)], index=pd.date_range("2024-01-01", periods=60))
    res = BacktestResult(
        equity_curve=eq,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=eq.index[0],
        end_date=eq.index[-1],
        initial_capital=100000,
        final_value=float(eq.iloc[-1]),
        total_return=float(eq.iloc[-1]) - 100000,
        total_return_pct=float((eq.iloc[-1] / 100000 - 1) * 100),
    )
    a = analyze_regimes(res, window=20, periods_per_year=252)
    b = analyze_regimes(res, window=20, periods_per_year=52)
    assert a.result.total_volatility != b.result.total_volatility


def test_regime_for_backtest_periods_per_year_affects_volatility():
    metrics = BacktestMetrics()
    eq = pd.Series([100000 * (1 + 0.001 * i) for i in range(60)], index=pd.date_range("2024-01-01", periods=60))
    res = BacktestResult(
        equity_curve=eq,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=eq.index[0],
        end_date=eq.index[-1],
        initial_capital=100000,
        final_value=float(eq.iloc[-1]),
        total_return=float(eq.iloc[-1]) - 100000,
        total_return_pct=float((eq.iloc[-1] / 100000 - 1) * 100),
    )
    a = regime_for_backtest(res, window=20, periods_per_year=252)
    b = regime_for_backtest(res, window=20, periods_per_year=52)
    assert a.total_volatility != b.total_volatility


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
