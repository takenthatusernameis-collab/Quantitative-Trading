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
from quant_trading.backtest.metrics import calculate_backtest_metrics
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
    analysis = analyze_regimes(
        result, window=20, vol_threshold=0.15, return_threshold=0.05
    )

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
        1
        for s in analysis.segments
        if s.regime in (Regime.BEAR_LOW_VOL, Regime.BEAR_HIGH_VOL)
    )
    assert bear_count >= 1


def test_analyze_regimes_up_series_is_bull():
    equity = _make_equity(n=120, trend=0.003, vol=0.005, seed=1)
    result = _make_result(equity=equity)

    analysis = analyze_regimes(result, window=30)
    assert analysis.n_segments >= 1
    bull_count = sum(
        1
        for s in analysis.segments
        if s.regime in (Regime.BULL_LOW_VOL, Regime.BULL_HIGH_VOL)
    )
    assert bull_count >= 1


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])