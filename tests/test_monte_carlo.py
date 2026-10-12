"""Tests for the Monte Carlo simulator."""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics, calculate_backtest_metrics
from quant_trading.monte_carlo import (
    MonteCarloResult,
    MonteCarloSimulator,
    run_monte_carlo,
)


def _make_equity_curve(n: int = 60, seed: int = 0) -> pd.Series:
    """Build a gently rising equity curve of length n."""
    import numpy as np

    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0008, scale=0.01, size=n - 1)
    equity = 100_000.0 * np.cumprod(1 + returns)
    equity = np.concatenate([[100_000.0], equity])
    return pd.Series(equity)


def _make_result(equity: pd.Series | None = None) -> BacktestResult:
    equity = equity if equity is not None else _make_equity_curve()
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


def test_monte_carlo_result_runs_n_simulations():
    result = _make_result()
    mc = MonteCarloSimulator(n_simulations=50, random_state=42)
    sim = mc.run(result, method="bootstrap")

    assert isinstance(sim, MonteCarloResult)
    assert sim.n_simulations == 50
    assert len(sim.simulations) == 50
    for metric in sim.simulations:
        assert isinstance(metric, BacktestMetrics)
    assert sim.original_metrics is result.metrics


def test_run_monte_carlo_convenience_function():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=25, random_state=7)

    assert sim.n_simulations == 25
    assert sim.confidence_level == 0.95
    assert sim.duration_seconds >= 0.0


def test_monte_carlo_reproducible_with_seed():
    result = _make_result()
    a = run_monte_carlo(result, n_simulations=30, random_state=123)
    b = run_monte_carlo(result, n_simulations=30, random_state=123)

    assert a.n_simulations == b.n_simulations
    for ma, mb in zip(a.simulations, b.simulations):
        assert ma.total_return_pct == pytest.approx(mb.total_return_pct)


def test_monte_carlo_confidence_interval_bounds():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=1)

    lower, upper = sim.get_confidence_interval("total_return_pct")
    assert lower <= upper


def test_monte_carlo_probability_of_profit_in_range():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=5)

    p = sim.probability_of_profit()
    assert 0.0 <= p <= 1.0


def test_monte_carlo_probability_of_beat_benchmark():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=5)

    p = sim.probability_of_beat_benchmark(5.0)
    assert 0.0 <= p <= 1.0


def test_monte_carlo_expected_shortfall_is_float():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=5)

    es = sim.expected_shortfall("total_return_pct", confidence=0.95)
    assert isinstance(es, float)


def test_monte_carlo_get_percentile_returns_float():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=50, random_state=9)

    val = sim.get_percentile("sharpe_ratio", 50)
    assert isinstance(val, float)


def test_monte_carlo_to_dataframe_has_rows():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, random_state=3)

    df = sim.to_dataframe()
    assert len(df) == 20
    assert "sharpe_ratio" in df.columns


def test_monte_carlo_summary_contains_keys():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, random_state=3)

    summary = sim.summary()
    assert summary["n_simulations"] == 20
    assert "probability_of_profit" in summary
    assert "total_return_pct_mean" in summary
    assert "sharpe_ratio_ci_lower" in summary


def test_monte_carlo_unknown_method_raises():
    result = _make_result()
    sim = MonteCarloSimulator(n_simulations=10, random_state=1)

    with pytest.raises(ValueError):
        sim.run(result, method="bogus")


def test_monte_carlo_insufficient_data_raises():
    equity = pd.Series([100_000.0])
    result = _make_result(equity=equity)

    sim = MonteCarloSimulator(n_simulations=5, random_state=1)
    with pytest.raises(ValueError):
        sim.run(result)


def test_monte_carlo_parametric_method_runs():
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, method="parametric", random_state=11)

    assert len(sim.simulations) == 20