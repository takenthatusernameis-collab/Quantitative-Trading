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


def _make_empty_result() -> MonteCarloResult:
    """Build a degenerate MonteCarloResult with no simulations."""
    return MonteCarloResult(
        simulations=[],
        original_metrics=BacktestMetrics(),
        n_simulations=0,
        confidence_level=0.95,
        start_time=datetime.now(),
        end_time=datetime.now(),
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


def test_monte_carlo_periods_per_year_annualizes_simulated_metrics():
    """The simulated metrics must be annualized with the requested period count."""
    result = _make_result()
    daily = run_monte_carlo(result, n_simulations=10, random_state=7, periods_per_year=252)
    monthly = run_monte_carlo(result, n_simulations=10, random_state=7, periods_per_year=12)

    assert daily.simulations[0].volatility != pytest.approx(monthly.simulations[0].volatility)
    assert daily.simulations[0].sharpe_ratio != pytest.approx(monthly.simulations[0].sharpe_ratio)


def test_monte_carlo_simulator_stores_periods_per_year():
    result = _make_result()
    simulator = MonteCarloSimulator(n_simulations=5, random_state=7, periods_per_year=52)
    assert simulator.periods_per_year == 52
    sim = simulator.run(result, method="parametric")
    assert len(sim.simulations) == 5


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


def test_monte_carlo_result_to_dataframe_empty():
    from datetime import datetime

    from quant_trading.backtest.metrics import BacktestMetrics
    from quant_trading.monte_carlo import MonteCarloResult

    metrics = BacktestMetrics()
    res = MonteCarloResult(
        simulations=[],
        original_metrics=metrics,
        n_simulations=0,
        confidence_level=0.95,
        start_time=datetime.now(),
        end_time=datetime.now(),
    )
    df = res.to_dataframe()
    assert df.empty


def test_monte_carlo_result_summary_empty():
    from datetime import datetime

    from quant_trading.backtest.metrics import BacktestMetrics
    from quant_trading.monte_carlo import MonteCarloResult

    metrics = BacktestMetrics()
    res = MonteCarloResult(
        simulations=[],
        original_metrics=metrics,
        n_simulations=0,
        confidence_level=0.95,
        start_time=datetime.now(),
        end_time=datetime.now(),
    )
    summary = res.summary()
    assert summary == {}


def test_monte_carlo_result_probability_of_profit_empty_raises():
    """probability_of_profit raises on an empty result instead of dividing by zero."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.probability_of_profit()


def test_monte_carlo_result_probability_of_beat_benchmark_empty_raises():
    """probability_of_beat_benchmark raises on an empty result."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.probability_of_beat_benchmark(0.0)


def test_monte_carlo_result_get_percentile_empty_raises():
    """get_percentile raises on an empty result instead of an opaque numpy error."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.get_percentile("total_return_pct", 50)


def test_monte_carlo_result_get_confidence_interval_empty_raises():
    """get_confidence_interval raises on an empty result."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.get_confidence_interval("total_return_pct")


def test_monte_carlo_result_expected_shortfall_empty_raises():
    """expected_shortfall raises on an empty result instead of an opaque numpy error."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.expected_shortfall("total_return_pct", confidence=0.95)


def test_monte_carlo_parametric_constant_returns():
    """Parametric method handles a degenerate (zero-variance) return distribution."""
    # A flat equity curve yields all-zero returns (std == 0).
    equity = pd.Series([100_000.0] * 60)
    result = _make_result(equity=equity)

    sim = run_monte_carlo(result, n_simulations=20, method="parametric", random_state=11)

    assert len(sim.simulations) == 20
    # Constant equity has no change, so every simulated return is 0%.
    assert all(m.total_return_pct == 0.0 for m in sim.simulations)


def test_monte_carlo_parametric_negative_returns():
    """Parametric method handles an extreme all-negative return distribution."""
    import numpy as np

    # Strictly declining equity curve (-1% daily so all returns are negative).
    daily_returns = np.full(59, -0.01)
    equity_vals = 100_000.0 * np.cumprod(1 + daily_returns)
    equity = pd.Series(np.concatenate([[100_000.0], equity_vals]))
    result = _make_result(equity=equity)

    sim = run_monte_carlo(result, n_simulations=20, method="parametric", random_state=7)

    assert len(sim.simulations) == 20
    # All daily returns are -1%, so every simulated return is negative.
    assert all(m.total_return_pct < 0 for m in sim.simulations)
    assert sim.summary()["probability_of_profit"] == 0.0


def test_monte_carlo_summary_is_json_serializable():
    """summary() output must be JSON-serializable for result serialization."""
    import json

    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, random_state=3)

    summary = sim.summary()
    json.dumps(summary)  # should not raise


def test_monte_carlo_probability_of_beat_benchmark_extremes():
    """probability_of_beat_benchmark returns 0.0 and 1.0 at extremes."""
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=50, random_state=5)
    returns = [m.total_return_pct for m in sim.simulations]
    high_benchmark = max(returns) + 1.0
    low_benchmark = min(returns) - 1.0

    assert sim.probability_of_beat_benchmark(high_benchmark) == 0.0
    assert sim.probability_of_beat_benchmark(low_benchmark) == 1.0


def test_monte_carlo_simulator_stores_risk_free_rate():
    """The simulator stores the configured risk-free rate."""
    simulator = MonteCarloSimulator(n_simulations=5, random_state=7, risk_free_rate=0.05)
    assert simulator.risk_free_rate == 0.05


def test_monte_carlo_default_risk_free_rate_is_002():
    simulator = MonteCarloSimulator(n_simulations=5, random_state=7)
    assert simulator.risk_free_rate == 0.02


def test_monte_carlo_risk_free_rate_reaches_simulated_metrics():
    """A non-default risk-free rate must change the simulated Sharpe/Sortino.

    Regression test: the simulator previously hardcoded ``risk_free_rate=0.02``
    in both the bootstrap and parametric methods.
    """
    result = _make_result()

    default = run_monte_carlo(result, n_simulations=30, random_state=7, risk_free_rate=0.02)
    high = run_monte_carlo(result, n_simulations=30, random_state=7, risk_free_rate=0.10)

    assert len(default.simulations) == 30
    assert len(high.simulations) == 30

    # Same seed => same equity curves, so the only difference is the rate.
    for d, h in zip(default.simulations, high.simulations):
        assert d.total_return_pct == pytest.approx(h.total_return_pct)
        assert h.sharpe_ratio != pytest.approx(d.sharpe_ratio)
        assert h.sortino_ratio != pytest.approx(d.sortino_ratio)


def test_monte_carlo_risk_free_rate_parametric_method():
    """The risk-free rate is honoured by the parametric method too."""
    result = _make_result()

    default = run_monte_carlo(
        result, n_simulations=20, method="parametric", random_state=7, risk_free_rate=0.02
    )
    high = run_monte_carlo(
        result, n_simulations=20, method="parametric", random_state=7, risk_free_rate=0.10
    )

    for d, h in zip(default.simulations, high.simulations):
        assert d.total_return_pct == pytest.approx(h.total_return_pct)
        assert h.sharpe_ratio != pytest.approx(d.sharpe_ratio)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
