"""Monte Carlo simulation for backtest strategy analysis.

Examples:
    Run a bootstrap Monte Carlo simulation on a backtest result::

        from quant_trading.monte_carlo import run_monte_carlo

        mc = run_monte_carlo(result, n_simulations=1000, method="bootstrap", random_state=42)
        profit_prob = mc.probability_of_profit()
        lower, upper = mc.get_confidence_interval("total_return_pct")

    Run a parametric simulation and inspect the summary::

        mc = run_monte_carlo(result, n_simulations=500, method="parametric", random_state=7)
        summary = mc.summary()
        mean_sharpe = summary["sharpe_ratio_mean"]
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics


@dataclass
class MonteCarloResult:
    """Result of a Monte Carlo simulation.

    Attributes:
        simulations: List of metric dataclasses produced by each simulation.
        original_metrics: Metrics computed from the original backtest result.
        n_simulations: Number of simulations that were run.
        confidence_level: Confidence level used for intervals (0-1).
        start_time: When the simulation run started.
        end_time: When the simulation run finished.

    Examples:
        mc = run_monte_carlo(result, random_state=42)
        profit_prob = mc.probability_of_profit()
        assert 0.0 <= profit_prob <= 1.0
        lower, upper = mc.get_confidence_interval("max_drawdown_pct")
    """

    simulations: list[BacktestMetrics]
    original_metrics: BacktestMetrics
    n_simulations: int
    confidence_level: float
    start_time: datetime
    end_time: datetime

    def _ensure_simulations(self) -> None:
        """Raise if no simulation results are available for statistics."""
        if not self.simulations:
            raise ValueError("No simulations available")

    @property
    def duration_seconds(self) -> float:
        """Elapsed wall-clock seconds between ``start_time`` and ``end_time``.

        Returns:
            Duration in seconds as a float.

        Examples:
            >>> from quant_trading.monte_carlo.simulator import MonteCarloResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from datetime import datetime
            >>> metrics = BacktestMetrics()
            >>> mc = MonteCarloResult(
            ...     simulations=[],
            ...     original_metrics=metrics,
            ...     n_simulations=0,
            ...     confidence_level=0.95,
            ...     start_time=datetime(2024, 1, 1),
            ...     end_time=datetime(2024, 1, 2),
            ... )
            >>> mc.duration_seconds
            86400.0
        """
        return (self.end_time - self.start_time).total_seconds()

    def get_percentile(self, metric: str, percentile: float) -> float:
        """Get percentile value for a metric across simulations."""
        self._ensure_simulations()
        values = [getattr(s, metric) for s in self.simulations]
        return float(np.percentile(values, percentile))

    def get_confidence_interval(self, metric: str) -> tuple[float, float]:
        """Get confidence interval for a metric."""
        self._ensure_simulations()
        alpha = (1 - self.confidence_level) / 2
        lower = self.get_percentile(metric, alpha * 100)
        upper = self.get_percentile(metric, (1 - alpha) * 100)
        return (lower, upper)

    def probability_of_profit(self) -> float:
        """Probability that total return is positive."""
        self._ensure_simulations()
        returns = [s.total_return_pct for s in self.simulations]
        return sum(1 for r in returns if r > 0) / len(returns)

    def probability_of_beat_benchmark(self, benchmark_return_pct: float) -> float:
        """Probability that total return exceeds benchmark."""
        self._ensure_simulations()
        returns = [s.total_return_pct for s in self.simulations]
        return sum(1 for r in returns if r > benchmark_return_pct) / len(returns)

    def expected_shortfall(self, metric: str, confidence: float = 0.95) -> float:
        """Expected shortfall (CVaR) for a metric at given confidence level."""
        self._ensure_simulations()
        values = [getattr(s, metric) for s in self.simulations]
        var = np.percentile(values, (1 - confidence) * 100)
        tail_values = [v for v in values if v <= var]
        return float(np.mean(tail_values)) if tail_values else var

    def to_dataframe(self) -> pd.DataFrame:
        """Convert simulation results to DataFrame for analysis."""
        if not self.simulations:
            return pd.DataFrame()  # type: ignore[no-any-return]
        data = [s.to_dict() for s in self.simulations]
        return pd.DataFrame(data)  # type: ignore[no-any-return]

    def summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        if not self.simulations:
            return {}

        metrics_names = [
            "total_return_pct",
            "annual_return_pct",
            "volatility",
            "max_drawdown_pct",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "win_rate",
            "profit_factor",
            "num_trades",
            "var_95",
        ]

        summary = {
            "n_simulations": self.n_simulations,
            "confidence_level": self.confidence_level,
            "probability_of_profit": self.probability_of_profit(),
        }

        for metric in metrics_names:
            values = [getattr(s, metric) for s in self.simulations]
            summary[f"{metric}_mean"] = float(np.mean(values))
            summary[f"{metric}_std"] = float(np.std(values))
            summary[f"{metric}_median"] = float(np.median(values))
            ci = self.get_confidence_interval(metric)
            summary[f"{metric}_ci_lower"] = ci[0]
            summary[f"{metric}_ci_upper"] = ci[1]

        return summary


class MonteCarloSimulator:
    """Monte Carlo simulator for backtest strategy analysis.

    Uses bootstrap resampling of returns to simulate alternative equity curves
    and estimate the distribution of performance metrics.
    """

    def __init__(
        self,
        n_simulations: int = 1000,
        confidence_level: float = 0.95,
        random_state: int | None = None,
    ):
        """Initialize Monte Carlo simulator.

        Args:
            n_simulations: Number of simulations to run.
            confidence_level: Confidence level for intervals (default 0.95).
            random_state: Random seed for reproducibility.
        """
        self.n_simulations = n_simulations
        self.confidence_level = confidence_level
        self.random_state = random_state
        self._rng = np.random.default_rng(random_state)

    def run(
        self,
        result: BacktestResult,
        method: str = "bootstrap",
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation on backtest result.

        Args:
            result: BacktestResult to analyze.
            method: Simulation method ("bootstrap" or "parametric").

        Returns:
            MonteCarloResult with simulation statistics.

        Examples:
            sim = MonteCarloSimulator(n_simulations=200, random_state=0)
            mc = sim.run(result, method="bootstrap")
            n_sims = mc.summary()["n_simulations"]
        """
        start_time = datetime.now()

        returns = self._extract_returns(result)
        if len(returns) < 2:
            raise ValueError("Insufficient data for Monte Carlo simulation")

        original_metrics = result.metrics

        if method == "bootstrap":
            simulations = self._run_bootstrap(returns, result.initial_capital, original_metrics)
        elif method == "parametric":
            simulations = self._run_parametric(returns, result.initial_capital, original_metrics)
        else:
            raise ValueError(f"Unknown method: {method}")

        end_time = datetime.now()

        return MonteCarloResult(
            simulations=simulations,
            original_metrics=original_metrics,
            n_simulations=self.n_simulations,
            confidence_level=self.confidence_level,
            start_time=start_time,
            end_time=end_time,
        )

    def _extract_returns(self, result: BacktestResult) -> np.ndarray:
        """Extract daily returns from equity curve."""
        equity = result.equity_curve
        returns = equity.pct_change().dropna().values
        return np.asarray(returns)

    def _run_bootstrap(
        self,
        returns: np.ndarray,
        initial_capital: float,
        original_metrics: BacktestMetrics,
    ) -> list[BacktestMetrics]:
        """Run bootstrap resampling simulation."""
        n_days = len(returns)
        simulations = []

        for _ in range(self.n_simulations):
            # Resample returns with replacement
            sim_returns = self._rng.choice(returns, size=n_days, replace=True)

            # Build equity curve
            equity = np.concatenate(
                [[initial_capital], initial_capital * np.cumprod(1 + sim_returns)]
            )
            equity_series = pd.Series(equity)

            # Calculate metrics
            from quant_trading.backtest.metrics import calculate_backtest_metrics

            metrics = calculate_backtest_metrics(equity_series, risk_free_rate=0.02)
            simulations.append(metrics)

        return simulations

    def _run_parametric(
        self,
        returns: np.ndarray,
        initial_capital: float,
        original_metrics: BacktestMetrics,
    ) -> list[BacktestMetrics]:
        """Run parametric simulation assuming normal distribution."""
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        n_days = len(returns)

        simulations = []

        for _ in range(self.n_simulations):
            # Sample from normal distribution
            sim_returns = self._rng.normal(mean_return, std_return, n_days)

            # Build equity curve
            equity = np.concatenate(
                [[initial_capital], initial_capital * np.cumprod(1 + sim_returns)]
            )
            equity_series = pd.Series(equity)

            # Calculate metrics
            from quant_trading.backtest.metrics import calculate_backtest_metrics

            metrics = calculate_backtest_metrics(equity_series, risk_free_rate=0.02)
            simulations.append(metrics)

        return simulations


def run_monte_carlo(
    result: BacktestResult,
    n_simulations: int = 1000,
    confidence_level: float = 0.95,
    method: str = "bootstrap",
    random_state: int | None = None,
) -> MonteCarloResult:
    """Convenience function to run Monte Carlo simulation.

    Args:
        result: BacktestResult to analyze.
        n_simulations: Number of simulations to run.
        confidence_level: Confidence level for intervals.
        method: Simulation method ("bootstrap" or "parametric").
        random_state: Random seed for reproducibility.

    Returns:
        MonteCarloResult with simulation statistics.

    Examples:
        mc = run_monte_carlo(result, n_simulations=500, random_state=42)
        profit_prob = mc.probability_of_profit()
        assert 0.0 <= profit_prob <= 1.0
    """
    simulator = MonteCarloSimulator(
        n_simulations=n_simulations,
        confidence_level=confidence_level,
        random_state=random_state,
    )
    return simulator.run(result, method=method)
