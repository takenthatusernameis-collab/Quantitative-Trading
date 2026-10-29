"""Monte Carlo simulation for backtest strategy analysis.

>>> from datetime import datetime
>>> import pandas as pd
>>> from quant_trading.backtest.engine import BacktestResult
>>> from quant_trading.backtest.metrics import calculate_backtest_metrics
>>> from quant_trading.monte_carlo import run_monte_carlo
>>> import numpy as np
>>> rng = np.random.default_rng(0)
>>> returns = rng.normal(loc=0.0008, scale=0.01, size=59)
>>> equity = 100000.0 * np.cumprod(1 + returns)
>>> equity = np.concatenate([[100000.0], equity])
>>> equity_series = pd.Series(equity)
>>> metrics = calculate_backtest_metrics(equity_series)
>>> result = BacktestResult(
...     equity_curve=equity_series,
...     trades=pd.DataFrame(),
...     positions={},
...     metrics=metrics,
...     start_date=datetime(2024, 1, 1),
...     end_date=datetime(2024, 3, 1),
...     initial_capital=100000.0,
...     final_value=float(equity_series.iloc[-1]),
...     total_return=float(equity_series.iloc[-1] - equity_series.iloc[0]),
...     total_return_pct=float((equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100),
... )
>>> mc = run_monte_carlo(result, n_simulations=25, method="bootstrap", random_state=42)
>>> profit_prob = mc.probability_of_profit()
>>> 0.0 <= profit_prob <= 1.0
True
>>> lower, upper = mc.get_confidence_interval("total_return_pct")
>>> lower <= upper
True
>>> mc2 = run_monte_carlo(result, n_simulations=25, method="parametric", random_state=7)
>>> summary = mc2.summary()
>>> isinstance(summary["sharpe_ratio_mean"], float)
True

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

    >>> from datetime import datetime
    >>> from quant_trading.monte_carlo import run_monte_carlo
    >>> from quant_trading.backtest.engine import BacktestResult
    >>> from quant_trading.backtest.metrics import calculate_backtest_metrics
    >>> import pandas as pd
    >>> import numpy as np
    >>> rng = np.random.default_rng(123)
    >>> returns = rng.normal(loc=0.0008, scale=0.01, size=59)
    >>> equity = 100000.0 * np.cumprod(1 + returns)
    >>> equity = np.concatenate([[100000.0], equity])
    >>> equity_series = pd.Series(equity)
    >>> metrics = calculate_backtest_metrics(equity_series)
    >>> result = BacktestResult(
    ...     equity_curve=equity_series,
    ...     trades=pd.DataFrame(),
    ...     positions={},
    ...     metrics=metrics,
    ...     start_date=datetime(2024, 1, 1),
    ...     end_date=datetime(2024, 3, 1),
    ...     initial_capital=100000.0,
    ...     final_value=float(equity_series.iloc[-1]),
    ...     total_return=float(equity_series.iloc[-1] - equity_series.iloc[0]),
    ...     total_return_pct=float((equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100),
    ... )
    >>> mc = run_monte_carlo(result, n_simulations=20, random_state=42)
    >>> profit_prob = mc.probability_of_profit()
    >>> 0.0 <= profit_prob <= 1.0
    True
    >>> lower, upper = mc.get_confidence_interval("max_drawdown_pct")
    >>> lower <= upper
    True

    """

    simulations: list[BacktestMetrics]
    original_metrics: BacktestMetrics
    n_simulations: int
    confidence_level: float
    start_time: datetime
    end_time: datetime

    def _ensure_simulations(self) -> None:
        """Raise if no simulation results are available for statistics.

        Raises:
            ValueError: If :attr:`simulations` is empty.

        """
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
        """Get the percentile value for a metric across simulations.

        Args:
            metric: Name of the :class:`BacktestMetrics` attribute to read.
            percentile: Percentile in the range 0-100.

        Returns:
            The requested percentile as a float.

        Raises:
            ValueError: If no simulations are available.

        """
        self._ensure_simulations()
        values = [getattr(s, metric) for s in self.simulations]
        return float(np.percentile(values, percentile))

    def get_confidence_interval(self, metric: str) -> tuple[float, float]:
        """Get the confidence interval for a metric across simulations.

        The interval is centered on the configured :attr:`confidence_level`,
        computed via the corresponding percentiles.

        Args:
            metric: Name of the :class:`BacktestMetrics` attribute to read.

        Returns:
            Tuple of ``(lower, upper)`` bounds.

        Raises:
            ValueError: If no simulations are available.

        """
        self._ensure_simulations()
        alpha = (1 - self.confidence_level) / 2
        lower = self.get_percentile(metric, alpha * 100)
        upper = self.get_percentile(metric, (1 - alpha) * 100)
        return (lower, upper)

    def probability_of_profit(self) -> float:
        """Get the probability that total return is positive.

        Returns:
            Fraction of simulations with a positive ``total_return_pct``,
            in the range 0.0-1.0.

        Raises:
            ValueError: If no simulations are available.

        """
        self._ensure_simulations()
        returns = [s.total_return_pct for s in self.simulations]
        return sum(1 for r in returns if r > 0) / len(returns)

    def probability_of_beat_benchmark(self, benchmark_return_pct: float) -> float:
        """Get the probability that total return exceeds a benchmark.

        Args:
            benchmark_return_pct: Benchmark total return to compare against.

        Returns:
            Fraction of simulations whose ``total_return_pct`` exceeds the
            benchmark, in the range 0.0-1.0.

        Raises:
            ValueError: If no simulations are available.

        """
        self._ensure_simulations()
        returns = [s.total_return_pct for s in self.simulations]
        return sum(1 for r in returns if r > benchmark_return_pct) / len(returns)

    def expected_shortfall(self, metric: str, confidence: float = 0.95) -> float:
        """Get expected shortfall (CVaR) for a metric at a given confidence level.

        Expected shortfall is the average of the worst ``1 - confidence``
        fraction of observations, providing a more conservative tail-risk
        measure than Value at Risk.

        Args:
            metric: Name of the :class:`BacktestMetrics` attribute to read.
            confidence: Confidence level (e.g. 0.95 for the 95% ES).

        Returns:
            The expected shortfall value.

        Raises:
            ValueError: If no simulations are available.

        """
        self._ensure_simulations()
        values = [getattr(s, metric) for s in self.simulations]
        var = np.percentile(values, (1 - confidence) * 100)
        tail_values = [v for v in values if v <= var]
        return float(np.mean(tail_values)) if tail_values else var

    def to_dataframe(self) -> pd.DataFrame:
        """Convert simulation results to a DataFrame for analysis.

        Returns:
            DataFrame with one row per simulation, or an empty DataFrame
            when no simulations were run.

        """
        if not self.simulations:
            empty: pd.DataFrame = pd.DataFrame()
            return empty
        data = [s.to_dict() for s in self.simulations]
        frame: pd.DataFrame = pd.DataFrame(data)
        return frame

    def summary(self) -> dict[str, Any]:
        """Get summary statistics for the simulation distribution.

        Returns:
            Dictionary with ``n_simulations``, ``confidence_level``,
            ``probability_of_profit``, and mean/std/median/confidence-interval
            entries for each tracked metric. Empty when no simulations ran.

        """
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

    Simulates alternative equity curves by resampling the backtest's daily
    returns, then aggregates the distribution of performance metrics across
    simulations. Two methods are supported:

    * ``"bootstrap"`` - non-parametric resampling with replacement.
    * ``"parametric"`` - sampling from a fitted normal distribution.

    Attributes:
        n_simulations: Number of alternative equity curves to generate.
        confidence_level: Confidence level used for intervals (0-1).
        random_state: Seed for reproducible simulation runs.
        risk_free_rate: Annual risk-free rate used for the simulated
            Sharpe/Sortino metrics (default 0.02).
        _rng: Internal numpy random generator.

    Examples:
        >>> from quant_trading.monte_carlo.simulator import MonteCarloSimulator
        >>> sim = MonteCarloSimulator(n_simulations=10, random_state=0)
        >>> sim.n_simulations
        10
        >>> sim.confidence_level
        0.95

    """

    def __init__(
        self,
        n_simulations: int = 1000,
        confidence_level: float = 0.95,
        random_state: int | None = None,
        periods_per_year: int = 252,
        risk_free_rate: float = 0.02,
    ):
        """Initialize the Monte Carlo simulator.

        Args:
            n_simulations: Number of simulations to run.
            confidence_level: Confidence level for intervals (default 0.95).
            random_state: Random seed for reproducibility.
            periods_per_year: Trading periods per year of the resampled
                returns, used to annualize the simulated metrics (default 252
                for daily data).
            risk_free_rate: Annual risk-free rate used for the simulated
                Sharpe/Sortino metrics (default 0.02).

        """
        self.n_simulations = n_simulations
        self.confidence_level = confidence_level
        self.random_state = random_state
        self.periods_per_year = periods_per_year
        self.risk_free_rate = risk_free_rate
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
            >>> from datetime import datetime
            >>> from quant_trading.monte_carlo.simulator import MonteCarloSimulator
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import calculate_backtest_metrics
            >>> import pandas as pd
            >>> import numpy as np
            >>> rng = np.random.default_rng(5)
            >>> returns = rng.normal(loc=0.0008, scale=0.01, size=59)
            >>> equity = 100000.0 * np.cumprod(1 + returns)
            >>> equity = np.concatenate([[100000.0], equity])
            >>> equity_series = pd.Series(equity)
            >>> metrics = calculate_backtest_metrics(equity_series)
            >>> result = BacktestResult(
            ...     equity_curve=equity_series,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=datetime(2024, 1, 1),
            ...     end_date=datetime(2024, 3, 1),
            ...     initial_capital=100000.0,
            ...     final_value=float(equity_series.iloc[-1]),
            ...     total_return=float(equity_series.iloc[-1] - equity_series.iloc[0]),
            ...     total_return_pct=float((equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100),
            ... )
            >>> sim = MonteCarloSimulator(n_simulations=50, random_state=0)
            >>> mc = sim.run(result, method="bootstrap")
            >>> mc.summary()["n_simulations"]
            50

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
        """Extract daily returns from the backtest's equity curve.

        Args:
            result: Backtest result whose equity curve is analyzed.

        Returns:
            NumPy array of daily simple returns (one fewer element than the
            equity curve, since the first bar has no prior return).

        """
        equity = result.equity_curve
        returns = equity.pct_change().dropna().values
        return np.asarray(returns)

    def _run_bootstrap(
        self,
        returns: np.ndarray,
        initial_capital: float,
        original_metrics: BacktestMetrics,
    ) -> list[BacktestMetrics]:
        """Run a bootstrap resampling simulation.

        Each simulation resamples the historical returns with replacement,
        rebuilds an equity curve from the resampled returns, and computes
        performance metrics for it.

        Args:
            returns: Historical daily returns to resample.
            initial_capital: Starting capital for each simulated curve.
            original_metrics: Metrics of the original backtest (unused but
                kept for API symmetry with :meth:`_run_parametric`).

        Returns:
            List of :class:`BacktestMetrics`, one per simulation.

        """
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

            metrics = calculate_backtest_metrics(
                equity_series,
                risk_free_rate=self.risk_free_rate,
                periods_per_year=self.periods_per_year,
            )
            simulations.append(metrics)

        return simulations

    def _run_parametric(
        self,
        returns: np.ndarray,
        initial_capital: float,
        original_metrics: BacktestMetrics,
    ) -> list[BacktestMetrics]:
        """Run a parametric simulation assuming a normal distribution.

        Each simulation draws returns from a normal distribution fitted to
        the historical returns' mean and standard deviation, then rebuilds
        an equity curve and computes performance metrics.

        Args:
            returns: Historical daily returns used to fit the distribution.
            initial_capital: Starting capital for each simulated curve.
            original_metrics: Metrics of the original backtest (unused but
                kept for API symmetry with :meth:`_run_bootstrap`).

        Returns:
            List of :class:`BacktestMetrics`, one per simulation.

        """
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

            metrics = calculate_backtest_metrics(
                equity_series,
                risk_free_rate=self.risk_free_rate,
                periods_per_year=self.periods_per_year,
            )
            simulations.append(metrics)

        return simulations


def run_monte_carlo(
    result: BacktestResult,
    n_simulations: int = 1000,
    confidence_level: float = 0.95,
    method: str = "bootstrap",
    random_state: int | None = None,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.02,
) -> MonteCarloResult:
    """Run Monte Carlo simulation for a backtest result.

    Args:
        result: BacktestResult to analyze.
        n_simulations: Number of simulations to run.
        confidence_level: Confidence level for intervals.
        method: Simulation method ("bootstrap" or "parametric").
        random_state: Random seed for reproducibility.
        periods_per_year: Trading periods per year of the resampled returns,
            used to annualize the simulated metrics (default 252 for daily
            data).
        risk_free_rate: Annual risk-free rate used for the simulated
            Sharpe/Sortino metrics (default 0.02).

    Returns:
        MonteCarloResult with simulation statistics.

    Examples:
        >>> from datetime import datetime
        >>> from quant_trading.monte_carlo import run_monte_carlo
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import calculate_backtest_metrics
        >>> import pandas as pd
        >>> import numpy as np
        >>> rng = np.random.default_rng(9)
        >>> returns = rng.normal(loc=0.0008, scale=0.01, size=59)
        >>> equity = 100000.0 * np.cumprod(1 + returns)
        >>> equity = np.concatenate([[100000.0], equity])
        >>> equity_series = pd.Series(equity)
        >>> metrics = calculate_backtest_metrics(equity_series)
        >>> result = BacktestResult(
        ...     equity_curve=equity_series,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=datetime(2024, 1, 1),
        ...     end_date=datetime(2024, 3, 1),
        ...     initial_capital=100000.0,
        ...     final_value=float(equity_series.iloc[-1]),
        ...     total_return=float(equity_series.iloc[-1] - equity_series.iloc[0]),
        ...     total_return_pct=float((equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100),
        ... )
        >>> mc = run_monte_carlo(result, n_simulations=25, random_state=42)
        >>> profit_prob = mc.probability_of_profit()
        >>> 0.0 <= profit_prob <= 1.0
        True

    """
    simulator = MonteCarloSimulator(
        n_simulations=n_simulations,
        confidence_level=confidence_level,
        random_state=random_state,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )
    return simulator.run(result, method=method)
