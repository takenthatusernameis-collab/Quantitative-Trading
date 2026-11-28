"""Tests for the Monte Carlo simulator."""

import json
from datetime import datetime
from typing import cast

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
    return pd.Series(equity)  # type: ignore[no-any-return]


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


def _make_populated_result() -> MonteCarloResult:
    """Build a MonteCarloResult with three known total-return simulations."""
    sims = [BacktestMetrics(total_return_pct=r) for r in (-5.0, 2.0, 10.0)]
    return MonteCarloResult(
        simulations=sims,
        original_metrics=BacktestMetrics(),
        n_simulations=len(sims),
        confidence_level=0.95,
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 2),
    )


def test_monte_carlo_result_runs_n_simulations() -> None:
    result = _make_result()
    mc = MonteCarloSimulator(n_simulations=50, random_state=42)
    sim = mc.run(result, method="bootstrap")

    assert isinstance(sim, MonteCarloResult)
    assert sim.n_simulations == 50
    assert len(sim.simulations) == 50
    for metric in sim.simulations:
        assert isinstance(metric, BacktestMetrics)
    assert sim.original_metrics is result.metrics


def test_run_monte_carlo_convenience_function() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=25, random_state=7)

    assert sim.n_simulations == 25
    assert sim.confidence_level == 0.95
    assert sim.duration_seconds >= 0.0


def test_monte_carlo_periods_per_year_annualizes_simulated_metrics() -> None:
    """The simulated metrics must be annualized with the requested period count."""
    result = _make_result()
    daily = run_monte_carlo(result, n_simulations=10, random_state=7, periods_per_year=252)
    monthly = run_monte_carlo(result, n_simulations=10, random_state=7, periods_per_year=12)

    assert daily.simulations[0].volatility != pytest.approx(monthly.simulations[0].volatility)
    assert daily.simulations[0].sharpe_ratio != pytest.approx(monthly.simulations[0].sharpe_ratio)


def test_monte_carlo_simulator_stores_periods_per_year() -> None:
    result = _make_result()
    simulator = MonteCarloSimulator(n_simulations=5, random_state=7, periods_per_year=52)
    assert simulator.periods_per_year == 52
    sim = simulator.run(result, method="parametric")
    assert len(sim.simulations) == 5


def test_monte_carlo_reproducible_with_seed() -> None:
    result = _make_result()
    a = run_monte_carlo(result, n_simulations=30, random_state=123)
    b = run_monte_carlo(result, n_simulations=30, random_state=123)

    assert a.n_simulations == b.n_simulations
    for ma, mb in zip(a.simulations, b.simulations):
        assert ma.total_return_pct == pytest.approx(mb.total_return_pct)


def test_monte_carlo_confidence_interval_bounds() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=1)

    lower, upper = sim.get_confidence_interval("total_return_pct")
    assert lower <= upper


def test_monte_carlo_probability_of_profit_in_range() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=5)

    p = sim.probability_of_profit()
    assert 0.0 <= p <= 1.0


def test_monte_carlo_probability_of_beat_benchmark() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=5)

    p = sim.probability_of_beat_benchmark(5.0)
    assert 0.0 <= p <= 1.0


def test_monte_carlo_expected_shortfall_is_float() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=100, random_state=5)

    es = sim.expected_shortfall("total_return_pct", confidence=0.95)
    assert isinstance(es, float)


def test_monte_carlo_get_percentile_returns_float() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=50, random_state=9)

    val = sim.get_percentile("sharpe_ratio", 50)
    assert isinstance(val, float)


def test_monte_carlo_to_dataframe_has_rows() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, random_state=3)

    df = sim.to_dataframe()
    assert len(df) == 20
    assert "sharpe_ratio" in df.columns


def test_monte_carlo_summary_contains_keys() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, random_state=3)

    summary = sim.summary()
    assert summary["n_simulations"] == 20
    assert "probability_of_profit" in summary
    assert "total_return_pct_mean" in summary
    assert "sharpe_ratio_ci_lower" in summary


def test_monte_carlo_unknown_method_raises() -> None:
    result = _make_result()
    sim = MonteCarloSimulator(n_simulations=10, random_state=1)

    with pytest.raises(ValueError):
        sim.run(result, method="bogus")


def test_monte_carlo_insufficient_data_raises() -> None:
    equity = pd.Series([100_000.0])
    result = _make_result(equity=equity)

    sim = MonteCarloSimulator(n_simulations=5, random_state=1)
    with pytest.raises(ValueError):
        sim.run(result)


def test_monte_carlo_parametric_method_runs() -> None:
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, method="parametric", random_state=11)

    assert len(sim.simulations) == 20


def test_monte_carlo_result_to_dataframe_empty() -> None:
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


def test_monte_carlo_result_summary_empty() -> None:
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


def test_monte_carlo_result_probability_of_profit_empty_raises() -> None:
    """probability_of_profit raises on an empty result instead of dividing by zero."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.probability_of_profit()


def test_monte_carlo_result_probability_of_beat_benchmark_empty_raises() -> None:
    """probability_of_beat_benchmark raises on an empty result."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.probability_of_beat_benchmark(0.0)


def test_monte_carlo_result_get_percentile_empty_raises() -> None:
    """get_percentile raises on an empty result instead of an opaque numpy error."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.get_percentile("total_return_pct", 50)


def test_monte_carlo_result_get_confidence_interval_empty_raises() -> None:
    """get_confidence_interval raises on an empty result."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.get_confidence_interval("total_return_pct")


def test_monte_carlo_result_expected_shortfall_empty_raises() -> None:
    """expected_shortfall raises on an empty result instead of an opaque numpy error."""
    res = _make_empty_result()
    with pytest.raises(ValueError, match="No simulations available"):
        res.expected_shortfall("total_return_pct", confidence=0.95)


@pytest.mark.parametrize("percentile", [-1.0, 101.0, float("nan"), float("inf"), "x", None, True])
def test_monte_carlo_get_percentile_rejects_invalid_percentile(percentile: object) -> None:
    """get_percentile rejects an out-of-range or non-numeric percentile clearly."""
    res = _make_populated_result()
    with pytest.raises(ValueError, match="invalid percentile"):
        res.get_percentile("total_return_pct", cast(float, percentile))


@pytest.mark.parametrize("percentile", [0.0, 50.0, 100.0])
def test_monte_carlo_get_percentile_accepts_boundary_percentiles(percentile: float) -> None:
    """get_percentile accepts the closed [0, 100] boundary percentiles."""
    res = _make_populated_result()
    value = res.get_percentile("total_return_pct", percentile)
    assert isinstance(value, float)


@pytest.mark.parametrize(
    "confidence", [0.0, 1.0, 1.5, -0.5, float("nan"), float("inf"), "x", None, True]
)
def test_monte_carlo_expected_shortfall_rejects_invalid_confidence(confidence: object) -> None:
    """expected_shortfall rejects a non-(0,1) or non-numeric confidence clearly."""
    res = _make_populated_result()
    with pytest.raises(ValueError, match="invalid confidence"):
        res.expected_shortfall("total_return_pct", cast(float, confidence))


def test_monte_carlo_expected_shortfall_accepts_valid_confidence() -> None:
    """expected_shortfall returns a finite float for a valid confidence level."""
    res = _make_populated_result()
    value = res.expected_shortfall("total_return_pct", confidence=0.95)
    assert isinstance(value, float)


def test_monte_carlo_parametric_constant_returns() -> None:
    """Parametric method handles a degenerate (zero-variance) return distribution."""
    # A flat equity curve yields all-zero returns (std == 0).
    equity = pd.Series([100_000.0] * 60)
    result = _make_result(equity=equity)

    sim = run_monte_carlo(result, n_simulations=20, method="parametric", random_state=11)

    assert len(sim.simulations) == 20
    # Constant equity has no change, so every simulated return is 0%.
    assert all(m.total_return_pct == 0.0 for m in sim.simulations)


def test_monte_carlo_parametric_negative_returns() -> None:
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


def test_monte_carlo_summary_is_json_serializable() -> None:
    """summary() output must be JSON-serializable for result serialization."""
    import json

    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=20, random_state=3)

    summary = sim.summary()
    json.dumps(summary)  # should not raise


def test_monte_carlo_probability_of_beat_benchmark_extremes() -> None:
    """probability_of_beat_benchmark returns 0.0 and 1.0 at extremes."""
    result = _make_result()
    sim = run_monte_carlo(result, n_simulations=50, random_state=5)
    returns = [m.total_return_pct for m in sim.simulations]
    high_benchmark = max(returns) + 1.0
    low_benchmark = min(returns) - 1.0

    assert sim.probability_of_beat_benchmark(high_benchmark) == 0.0
    assert sim.probability_of_beat_benchmark(low_benchmark) == 1.0


def test_monte_carlo_simulator_stores_risk_free_rate() -> None:
    """The simulator stores the configured risk-free rate."""
    simulator = MonteCarloSimulator(n_simulations=5, random_state=7, risk_free_rate=0.05)
    assert simulator.risk_free_rate == 0.05


def test_monte_carlo_default_risk_free_rate_is_002() -> None:
    simulator = MonteCarloSimulator(n_simulations=5, random_state=7)
    assert simulator.risk_free_rate == 0.02


@pytest.mark.parametrize("n_simulations", [0, -1, -5])
def test_monte_carlo_rejects_invalid_n_simulations(n_simulations: int) -> None:
    with pytest.raises(ValueError, match="invalid n_simulations"):
        MonteCarloSimulator(n_simulations=n_simulations, random_state=7)


@pytest.mark.parametrize("confidence_level", [0.0, -0.5, 1.0, 1.5])
def test_monte_carlo_rejects_invalid_confidence_level(confidence_level: float) -> None:
    with pytest.raises(ValueError, match="invalid confidence_level"):
        MonteCarloSimulator(n_simulations=10, confidence_level=confidence_level, random_state=7)


@pytest.mark.parametrize("periods_per_year", [0, -1, -252])
def test_monte_carlo_rejects_invalid_periods_per_year(periods_per_year: int) -> None:
    with pytest.raises(ValueError, match="invalid periods_per_year"):
        MonteCarloSimulator(n_simulations=10, periods_per_year=periods_per_year, random_state=7)


@pytest.mark.parametrize("risk_free_rate", [float("nan"), float("inf"), float("-inf")])
def test_monte_carlo_rejects_invalid_risk_free_rate(risk_free_rate: float) -> None:
    """A non-finite risk-free rate is rejected at construction time.

    Without this guard the rate flows into ``calculate_sharpe_ratio`` /
    ``calculate_sortino_ratio`` and turns every simulated Sharpe/Sortino into
    NaN, matching the construction-time check ``BacktestConfig`` already applies.
    """
    with pytest.raises(ValueError, match="invalid risk_free_rate"):
        MonteCarloSimulator(n_simulations=10, risk_free_rate=risk_free_rate, random_state=7)


@pytest.mark.parametrize(
    "field,value",
    [
        ("n_simulations", True),
        ("n_simulations", False),
        ("n_simulations", "abc"),
        ("confidence_level", True),
        ("confidence_level", "abc"),
        ("periods_per_year", True),
        ("periods_per_year", "abc"),
        ("risk_free_rate", True),
        ("risk_free_rate", "abc"),
        ("n_jobs", True),
        ("n_jobs", "abc"),
    ],
)
def test_monte_carlo_rejects_bool_and_non_numeric(field: str, value: object) -> None:
    """Booleans and non-numeric values are rejected for every numeric field.

    ``bool`` is a subclass of ``int`` so ``isinstance(True, (int, float))`` is
    ``True``; without an explicit ``isinstance(x, bool)`` guard every such
    value was silently accepted at construction time (the same defect class
    already fixed for ``BaseOptimizer`` and the config/data validation
    chains). The failed construction must not mutate the simulator.
    """
    with pytest.raises(ValueError, match=f"invalid {field}"):
        if field == "n_simulations":
            MonteCarloSimulator(n_simulations=cast(int, value), random_state=7)
        elif field == "n_jobs":
            MonteCarloSimulator(n_simulations=10, n_jobs=cast(int, value), random_state=7)
        elif field == "confidence_level":
            MonteCarloSimulator(
                n_simulations=10, confidence_level=cast(float, value), random_state=7
            )
        elif field == "periods_per_year":
            MonteCarloSimulator(n_simulations=10, periods_per_year=cast(int, value), random_state=7)
        else:  # risk_free_rate
            MonteCarloSimulator(n_simulations=10, risk_free_rate=cast(float, value), random_state=7)


def test_monte_carlo_rejects_non_finite_n_simulations() -> None:
    """A non-finite ``n_simulations`` is rejected at construction time."""
    with pytest.raises(ValueError, match="invalid n_simulations"):
        MonteCarloSimulator(n_simulations=cast(int, float("nan")), random_state=7)


def test_monte_carlo_rejects_non_finite_risk_free_rate() -> None:
    """A non-finite ``risk_free_rate`` is rejected at construction time."""
    with pytest.raises(ValueError, match="invalid risk_free_rate"):
        MonteCarloSimulator(
            n_simulations=10, risk_free_rate=cast(float, float("nan")), random_state=7
        )


def test_monte_carlo_rejects_non_finite_n_jobs() -> None:
    """A non-finite ``n_jobs`` is rejected at construction time."""
    with pytest.raises(ValueError, match="invalid n_jobs"):
        MonteCarloSimulator(n_simulations=10, n_jobs=cast(int, float("nan")), random_state=7)


@pytest.mark.parametrize(
    "random_state",
    [True, False, "abc", 7.0, float("nan"), float("inf"), float("-inf"), -1, -5],
)
def test_monte_carlo_rejects_invalid_random_state(random_state: object) -> None:
    """``random_state`` must be a non-negative finite number or ``None``.

    Booleans, non-numeric values, non-finite numbers, and negative seeds are
    rejected with a clear ``ValueError`` at construction time instead of being
    silently accepted (bool) or raising an opaque error from numpy.
    """
    with pytest.raises(ValueError, match="invalid random_state"):
        MonteCarloSimulator(n_simulations=10, random_state=cast(int, random_state))


@pytest.mark.parametrize("random_state", [None, 0, 1, 42, 100])
def test_monte_carlo_accepts_valid_random_state(random_state: int | None) -> None:
    """``random_state`` of ``None`` or a non-negative int is accepted."""
    simulator = MonteCarloSimulator(n_simulations=10, random_state=random_state)
    assert simulator.random_state == random_state


def test_monte_carlo_accepts_finite_risk_free_rate() -> None:
    simulator = MonteCarloSimulator(n_simulations=10, risk_free_rate=0.05, random_state=7)
    assert simulator.risk_free_rate == 0.05


def test_monte_carlo_accepts_minimal_valid_values() -> None:
    simulator = MonteCarloSimulator(
        n_simulations=1,
        confidence_level=0.5,
        periods_per_year=1,
        random_state=7,
    )
    assert simulator.n_simulations == 1
    assert simulator.confidence_level == 0.5
    assert simulator.periods_per_year == 1


@pytest.mark.parametrize("n_jobs", [float("nan"), float("inf")])
def test_monte_carlo_rejects_invalid_n_jobs(n_jobs: float) -> None:
    """Non-finite n_jobs values are rejected at construction time."""
    with pytest.raises(ValueError, match="invalid n_jobs"):
        MonteCarloSimulator(n_simulations=10, n_jobs=cast(int, n_jobs), random_state=7)


@pytest.mark.parametrize("n_jobs", [0, -1, -2, -5])
def test_monte_carlo_clamps_non_positive_n_jobs_to_one(n_jobs: int) -> None:
    """Non-positive n_jobs values (except -1 for auto) are clamped to 1."""
    simulator = MonteCarloSimulator(n_simulations=10, n_jobs=n_jobs, random_state=7)
    assert simulator.n_jobs >= 1


def test_monte_carlo_run_monte_carlo_rejects_invalid_n_simulations() -> None:
    result = _make_result()
    with pytest.raises(ValueError, match="invalid n_simulations"):
        run_monte_carlo(result, n_simulations=0, random_state=7)


def test_monte_carlo_run_monte_carlo_rejects_invalid_risk_free_rate() -> None:
    result = _make_result()
    with pytest.raises(ValueError, match="invalid risk_free_rate"):
        run_monte_carlo(result, n_simulations=10, random_state=7, risk_free_rate=float("nan"))


def test_monte_carlo_risk_free_rate_reaches_simulated_metrics() -> None:
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


def test_monte_carlo_risk_free_rate_parametric_method() -> None:
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


class TestMonteCarloResultSerialization:
    """Tests for MonteCarloResult.to_dict/from_dict."""

    def test_to_dict_round_trips(self) -> None:
        result = _make_result()
        sim = run_monte_carlo(result, n_simulations=12, random_state=42)
        data = sim.to_dict()
        reconstructed = MonteCarloResult.from_dict(data)

        assert reconstructed.n_simulations == sim.n_simulations
        assert reconstructed.confidence_level == sim.confidence_level
        assert len(reconstructed.simulations) == len(sim.simulations)
        assert reconstructed.start_time == sim.start_time
        assert reconstructed.end_time == sim.end_time
        assert reconstructed.original_metrics.total_return_pct == pytest.approx(
            sim.original_metrics.total_return_pct
        )
        for orig, recon in zip(sim.simulations, reconstructed.simulations):
            assert recon.total_return_pct == pytest.approx(orig.total_return_pct)
            assert recon.sharpe_ratio == pytest.approx(orig.sharpe_ratio)
            assert recon.num_trades == orig.num_trades

    def test_to_dict_is_json_serializable(self) -> None:
        result = _make_result()
        sim = run_monte_carlo(result, n_simulations=5, random_state=1)
        data = sim.to_dict()
        encoded = json.dumps(data)
        decoded = json.loads(encoded)
        reconstructed = MonteCarloResult.from_dict(decoded)
        assert reconstructed.n_simulations == 5
        assert len(reconstructed.simulations) == 5

    def test_from_dict_defaults_missing_keys(self) -> None:
        mc = MonteCarloResult.from_dict({})
        assert mc.n_simulations == 0
        assert mc.confidence_level == 0.95
        assert mc.simulations == []
        assert mc.start_time == datetime(1970, 1, 1)
        assert mc.end_time == datetime(1970, 1, 1)

    def test_from_dict_ignores_extra_keys(self) -> None:
        m = BacktestMetrics(total_return=1.0)
        mc = MonteCarloResult(
            simulations=[m],
            original_metrics=m,
            n_simulations=1,
            confidence_level=0.95,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 1),
        )
        data = mc.to_dict()
        data["unknown"] = "value"
        reconstructed = MonteCarloResult.from_dict(data)
        assert reconstructed.n_simulations == 1
        assert len(reconstructed.simulations) == 1

    def test_from_dict_empty_simulations(self) -> None:
        m = BacktestMetrics()
        mc = MonteCarloResult([], m, 0, 0.95, datetime(2024, 1, 1), datetime(2024, 1, 1))
        reconstructed = MonteCarloResult.from_dict(mc.to_dict())
        assert reconstructed.simulations == []
        assert reconstructed.n_simulations == 0


class TestMonteCarloResultFromDictValidation:
    """Tests for MonteCarloResult.from_dict input validation."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("n_simulations", True),
            ("n_simulations", False),
            ("n_simulations", "abc"),
            ("n_simulations", float("nan")),
            ("confidence_level", True),
            ("confidence_level", False),
            ("confidence_level", "abc"),
            ("confidence_level", float("nan")),
            ("confidence_level", 0.0),
            ("confidence_level", 1.0),
            ("confidence_level", 1.5),
            ("confidence_level", -0.5),
        ],
    )
    def test_from_dict_rejects_invalid_inputs(self, field: str, value: object) -> None:
        """Invalid inputs for numeric fields raise ValueError."""
        with pytest.raises(ValueError, match=f"invalid {field}"):
            MonteCarloResult.from_dict({field: value})

    @pytest.mark.parametrize(
        "field,value",
        [
            ("n_simulations", 0),
            ("n_simulations", 10),
            ("confidence_level", 0.5),
            ("confidence_level", 0.95),
            ("confidence_level", 0.99),
        ],
    )
    def test_from_dict_accepts_valid_inputs(self, field: str, value: object) -> None:
        """Valid inputs for numeric fields are accepted."""
        mc = MonteCarloResult.from_dict({field: value})
        if field == "n_simulations":
            assert mc.n_simulations == value
        else:
            assert mc.confidence_level == value


class TestMonteCarloParallelExecution:
    """Tests for parallel Monte Carlo execution."""

    def test_monte_carlo_parallel_bootstrap_runs(self) -> None:
        """Parallel bootstrap execution runs and produces correct number of simulations."""
        result = _make_result()
        sim = MonteCarloSimulator(n_simulations=20, random_state=7, n_jobs=2)
        mc = sim.run(result, method="bootstrap")

        assert mc.n_simulations == 20
        assert len(mc.simulations) == 20
        for metric in mc.simulations:
            assert isinstance(metric, BacktestMetrics)

    def test_monte_carlo_parallel_parametric_runs(self) -> None:
        """Parallel parametric execution runs and produces correct number of simulations."""
        result = _make_result()
        sim = MonteCarloSimulator(n_simulations=20, random_state=7, n_jobs=2)
        mc = sim.run(result, method="parametric")

        assert mc.n_simulations == 20
        assert len(mc.simulations) == 20
        for metric in mc.simulations:
            assert isinstance(metric, BacktestMetrics)

    def test_monte_carlo_parallel_reproducible_with_seed(self) -> None:
        """Parallel execution is reproducible with the same seed."""
        result = _make_result()
        a = MonteCarloSimulator(n_simulations=30, random_state=123, n_jobs=2).run(
            result, method="bootstrap"
        )
        b = MonteCarloSimulator(n_simulations=30, random_state=123, n_jobs=2).run(
            result, method="bootstrap"
        )

        assert a.n_simulations == b.n_simulations
        for ma, mb in zip(a.simulations, b.simulations):
            assert ma.total_return_pct == pytest.approx(mb.total_return_pct)

    def test_monte_carlo_parametric_parallel_reproducible_with_seed(self) -> None:
        """Parallel parametric execution is reproducible with the same seed."""
        result = _make_result()
        a = MonteCarloSimulator(n_simulations=30, random_state=123, n_jobs=2).run(
            result, method="parametric"
        )
        b = MonteCarloSimulator(n_simulations=30, random_state=123, n_jobs=2).run(
            result, method="parametric"
        )

        assert a.n_simulations == b.n_simulations
        for ma, mb in zip(a.simulations, b.simulations):
            assert ma.total_return_pct == pytest.approx(mb.total_return_pct)

    def test_run_monte_carlo_convenience_function_with_n_jobs(self) -> None:
        """run_monte_carlo convenience function accepts n_jobs parameter."""
        result = _make_result()
        mc = run_monte_carlo(result, n_simulations=20, random_state=7, n_jobs=2)

        assert mc.n_simulations == 20
        assert len(mc.simulations) == 20

    def test_monte_carlo_parallel_n_jobs_minus_one(self) -> None:
        """n_jobs=-1 uses all available CPUs."""
        import os

        result = _make_result()
        sim = MonteCarloSimulator(n_simulations=10, random_state=7, n_jobs=-1)
        expected_jobs = os.cpu_count() or 1
        assert sim.n_jobs == expected_jobs
        mc = sim.run(result, method="bootstrap")
        assert mc.n_simulations == 10

    def test_monte_carlo_parallel_invalid_n_jobs_clamped(self) -> None:
        """Non-positive n_jobs values are clamped to minimum of 1."""
        sim = MonteCarloSimulator(n_simulations=10, random_state=7, n_jobs=0)
        assert sim.n_jobs == 1
        sim = MonteCarloSimulator(n_simulations=10, random_state=7, n_jobs=-5)
        assert sim.n_jobs == 1

    @pytest.mark.parametrize("method", ["bootstrap", "parametric"])
    def test_monte_carlo_parallel_more_workers_than_simulations(self, method: str) -> None:
        """Workers beyond the simulation count are skipped without error.

        When ``n_jobs`` exceeds ``n_simulations`` some workers are assigned
        zero simulations. They must be skipped (the ``n_sim > 0`` guard in the
        parallel runners) so that exactly ``n_simulations`` results are produced.
        """
        result = _make_result()
        sim = MonteCarloSimulator(n_simulations=2, random_state=7, n_jobs=4)
        assert sim.n_jobs == 4

        mc = sim.run(result, method=method)

        assert mc.n_simulations == 2
        assert len(mc.simulations) == 2
        for metric in mc.simulations:
            assert isinstance(metric, BacktestMetrics)

    def test_monte_carlo_parallel_statistical_properties(self) -> None:
        """Parallel execution produces statistically similar results to sequential."""
        import numpy as np

        result = _make_result()

        seq = MonteCarloSimulator(n_simulations=200, random_state=42, n_jobs=1).run(
            result, method="bootstrap"
        )
        par = MonteCarloSimulator(n_simulations=200, random_state=42, n_jobs=2).run(
            result, method="bootstrap"
        )

        seq_returns = [m.total_return_pct for m in seq.simulations]
        par_returns = [m.total_return_pct for m in par.simulations]

        # Means should be close (within 20% relative difference)
        seq_mean = np.mean(seq_returns)
        par_mean = np.mean(par_returns)
        assert abs(seq_mean - par_mean) / max(abs(seq_mean), 1e-10) < 0.2

        # Standard deviations should be close
        seq_std = np.std(seq_returns)
        par_std = np.std(par_returns)
        assert abs(seq_std - par_std) / max(abs(seq_std), 1e-10) < 0.2
