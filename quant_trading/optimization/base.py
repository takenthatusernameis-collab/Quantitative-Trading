"""Base classes and utilities for parameter optimization.

This module provides the foundational building blocks used by every
concrete optimizer in :mod:`quant_trading.optimization`: a
:class:`ParameterSpace` describing one tunable parameter, a
:class:`ParameterGrid` composing multiple spaces into candidate
combinations, common objective functions, an :class:`OptimizationResult`
container, and the abstract :class:`BaseOptimizer`.

Examples:
    >>> from quant_trading.optimization.base import ParameterSpace, ParameterGrid
    >>> space = ParameterSpace(name="x", values=[1, 2, 3])
    >>> grid = ParameterGrid().add(space)
    >>> grid.generate_combinations()
    [{'x': 1.0}, {'x': 2.0}, {'x': 3.0}]

"""

# mypy: disable-error-code="no-any-return"

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from quant_trading.backtest.engine import BacktestResult
from quant_trading.strategies.base import Strategy


@dataclass
class ParameterSpace:
    """Defines a parameter space for optimization.

    Can be used for both grid search (discrete values) and random search
    (distributions).

    Attributes:
        name: Name of the parameter.
        values: Discrete candidate values for grid search.
        min_val: Lower bound for continuous sampling.
        max_val: Upper bound for continuous sampling.
        step: Step size used when generating a grid from bounds.
        distribution: Sampling distribution name (e.g. ``"log"``).
        param_type: Type to cast sampled/generated values to.

    Examples:
        >>> from quant_trading.optimization.base import ParameterSpace
        >>> space = ParameterSpace(name="x", values=[1, 2, 3])
        >>> space.generate_grid()
        [1.0, 2.0, 3.0]
        >>> space = ParameterSpace(name="y", min_val=0.0, max_val=1.0, step=0.5)
        >>> space.generate_grid()
        [0.0, 0.5, 1.0]

    """

    name: str
    values: list[Any] | None = None
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    distribution: str | None = None
    param_type: type = float  # Type to cast values to (int, float, bool)

    def __post_init__(self) -> None:
        """Validate that at least one of ``values`` or ``min_val`` is set.

        Raises:
            ValueError: If both ``values`` and ``min_val`` are None.

        """
        if self.values is None and self.min_val is None:
            raise ValueError("Either values or min_val must be provided")

    def generate_grid(self) -> list[Any]:
        """Generate all values for grid search.

        Returns:
            List of candidate values for this parameter space. Empty list if
            neither ``values`` nor bounds/step are configured.

        Raises:
            ValueError: If the grid is generated from bounds and ``step`` is
                not greater than zero. The loop would never reach ``max_val``
                and would not terminate.

        """
        if self.values is not None:
            return [self.param_type(v) for v in self.values]
        if self.min_val is not None and self.max_val is not None and self.step is not None:
            if self.step <= 0:
                raise ValueError(
                    f"step must be greater than 0 to generate a grid (got {self.step})"
                )
            if self.min_val > self.max_val:
                raise ValueError(
                    f"minimum ({self.min_val}) is greater than the maximum "
                    f"({self.max_val}) to generate a grid"
                )
            vals = []
            v = self.min_val
            while v <= self.max_val + 1e-10:
                vals.append(self.param_type(v))
                v += self.step
            return vals
        return []

    def sample_random(self, n: int, rng: Any | None = None) -> list[Any]:
        """Sample n random values for random search.

        Args:
            n: Number of values to sample.
            rng: Optional numpy random generator. Created if None.

        Returns:
            List of n sampled values.

        """
        import numpy as np

        if rng is None:
            rng = np.random.default_rng()

        if self.values is not None:
            return [self.param_type(v) for v in rng.choice(self.values, size=n, replace=True)]
        if self.min_val is not None and self.max_val is not None:
            if self.distribution == "log":
                log_min = np.log(self.min_val)
                log_max = np.log(self.max_val)
                return [self.param_type(v) for v in np.exp(rng.uniform(log_min, log_max, n))]
            return [self.param_type(v) for v in rng.uniform(self.min_val, self.max_val, n)]
        return []


@dataclass
class ParameterGrid:
    """Collection of parameter spaces defining a grid.

    Attributes:
        spaces: Mapping of parameter name to :class:`ParameterSpace`.
        validator: Optional cross-parameter validation callable.

    Examples:
        >>> from quant_trading.optimization.base import ParameterSpace, ParameterGrid
        >>> grid = ParameterGrid()
        >>> grid.add(ParameterSpace(name="x", values=[1, 2]))  # doctest: +ELLIPSIS
        ParameterGrid(...)
        >>> grid.generate_combinations()
        [{'x': 1.0}, {'x': 2.0}]

    """

    spaces: dict[str, ParameterSpace] = field(default_factory=dict)
    validator: Callable[[dict[str, Any]], bool] | None = None

    def add(self, space: ParameterSpace) -> "ParameterGrid":
        """Add a parameter space to the grid.

        Args:
            space: The parameter space to add.

        Returns:
            This grid instance (for chaining).

        """
        self.spaces[space.name] = space
        return self

    def set_validator(self, validator: Callable[[dict[str, Any]], bool]) -> "ParameterGrid":
        """Set a cross-parameter validation function.

        The validator receives a parameter combination dict and should return
        True if the combination is valid, False otherwise.

        Args:
            validator: Callable taking a params dict and returning bool.

        Returns:
            This grid instance (for chaining).

        """
        self.validator = validator
        return self

    def generate_combinations(self) -> list[dict[str, Any]]:
        """Generate all valid parameter combinations (Cartesian product).

        Returns:
            List of parameter dicts, filtered by the validator if set.

        """
        import itertools

        if not self.spaces:
            return [{}]

        keys = list(self.spaces.keys())
        value_lists = [self.spaces[k].generate_grid() for k in keys]

        combinations = []
        for combo in itertools.product(*value_lists):
            params = dict(zip(keys, combo))
            if self.validator is None or self.validator(params):
                combinations.append(params)
        return combinations

    def sample_random(self, n: int, rng: Any | None = None) -> list[dict[str, Any]]:
        """Sample n random parameter combinations.

        Args:
            n: Number of combinations to sample.
            rng: Optional numpy random generator. Created if None.

        Returns:
            List of n parameter dicts.

        """
        import numpy as np

        if rng is None:
            rng = np.random.default_rng()

        if not self.spaces:
            return [{}] * n

        keys = list(self.spaces.keys())
        combinations = []
        for _ in range(n):
            combo = {}
            for k in keys:
                samples = self.spaces[k].sample_random(1, rng)
                combo[k] = samples[0] if samples else None
            combinations.append(combo)
        return combinations


ObjectiveFunction = Callable[[BacktestResult], float]


def maximize_sharpe(result: BacktestResult) -> float:
    """Objective function that maximizes the Sharpe ratio.

    Args:
        result: Backtest result containing performance metrics.

    Returns:
        Sharpe ratio value, or 0.0 if the Sharpe ratio is None.

    Examples:
        >>> from quant_trading.optimization.base import maximize_sharpe
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.5)
        >>> eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> maximize_sharpe(res)
        1.5

    """
    return result.metrics.sharpe_ratio or 0.0


def maximize_total_return(result: BacktestResult) -> float:
    """Objective function that maximizes total return percentage.

    Args:
        result: Backtest result containing total return information.

    Returns:
        Total return as a percentage.

    Examples:
        >>> from quant_trading.optimization.base import maximize_total_return
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.0)
        >>> eq = pd.Series([100000, 110000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=110000,
        ...     total_return=10000,
        ...     total_return_pct=10.0,
        ... )
        >>> maximize_total_return(res)
        10.0

    """
    return result.total_return_pct


def maximize_calmar(result: BacktestResult) -> float:
    """Objective function that maximizes the Calmar ratio.

    Args:
        result: Backtest result containing performance metrics.

    Returns:
        Calmar ratio value, or 0.0 if the Calmar ratio is None.

    Examples:
        >>> from quant_trading.optimization.base import maximize_calmar
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.0, calmar_ratio=2.0)
        >>> eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> maximize_calmar(res)
        2.0

    """
    return result.metrics.calmar_ratio or 0.0


def maximize_sortino(result: BacktestResult) -> float:
    """Objective function that maximizes the Sortino ratio.

    The Sortino ratio only penalizes downside deviation, so it is a useful
    objective when large negative returns are more costly than large positive
    ones.

    Args:
        result: Backtest result containing performance metrics.

    Returns:
        Sortino ratio value, or 0.0 if the Sortino ratio is None.

    Examples:
        >>> from quant_trading.optimization.base import maximize_sortino
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.0, sortino_ratio=2.5)
        >>> eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> maximize_sortino(res)
        2.5

    """
    return result.metrics.sortino_ratio or 0.0


def minimize_max_drawdown(result: BacktestResult) -> float:
    """Objective function that minimizes maximum drawdown.

    Returns the negative maximum drawdown so the score increases as drawdown
    decreases (for maximization objective).

    Args:
        result: Backtest result containing performance metrics.

    Returns:
        Negative maximum drawdown value (e.g., -0.05 for 5% drawdown).

    Examples:
        >>> from quant_trading.optimization.base import minimize_max_drawdown
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.0, max_drawdown_pct=5.0)
        >>> eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> minimize_max_drawdown(res)
        -5.0

    """
    return -result.metrics.max_drawdown_pct


def maximize_profit_factor(result: BacktestResult) -> float:
    """Objective function that maximizes the profit factor.

    Args:
        result: Backtest result containing performance metrics.

    Returns:
        Profit factor value, or 0.0 if the profit factor is None.

    Examples:
        >>> from quant_trading.optimization.base import maximize_profit_factor
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.0, profit_factor=2.5)
        >>> eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> maximize_profit_factor(res)
        2.5

    """
    return result.metrics.profit_factor or 0.0


def maximize_win_rate(result: BacktestResult) -> float:
    """Objective function that maximizes the win rate.

    Args:
        result: Backtest result containing win rate information.

    Returns:
        Win rate (typically 0-100 if stored as percentage).

    Examples:
        >>> from quant_trading.optimization.base import maximize_win_rate
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> import pandas as pd
        >>> metrics = BacktestMetrics(sharpe_ratio=1.0, win_rate=0.7)
        >>> eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> maximize_win_rate(res)
        0.7

    """
    return getattr(result, "win_rate_pct", getattr(result.metrics, "win_rate", 0.0))


@dataclass
class OptimizationResult:
    """Result of a parameter optimization run.

    Attributes:
        best_params: Best parameter combination found.
        best_score: Score achieved by the best combination.
        best_result: Backtest result for the best combination.
        all_results: List of dicts with params/score for all combinations.
        start_time: Optimization start timestamp.
        end_time: Optimization end timestamp.

    Examples:
        >>> from quant_trading.optimization.base import OptimizationResult
        >>> r = OptimizationResult(best_params={"x": 1}, best_score=1.0)
        >>> r.duration_seconds is None
        True

    """

    best_params: dict[str, Any]
    best_score: float
    best_result: BacktestResult | None = None
    all_results: list[dict[str, Any]] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Elapsed wall-clock seconds between start and end, or None."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all results to a DataFrame for analysis.

        Returns:
            DataFrame of all recorded results, or empty DataFrame if none.

        """
        if not self.all_results:
            return pd.DataFrame()
        return pd.DataFrame(self.all_results)

    def get_top_n(self, n: int = 10) -> list[dict[str, Any]]:
        """Get top N results by score.

        Args:
            n: Number of top results to return.

        Returns:
            List of the n highest-scoring result dicts.

        """
        sorted_results = sorted(self.all_results, key=lambda x: x["score"], reverse=True)
        return sorted_results[:n]


class BaseOptimizer(ABC):
    """Base class for parameter optimizers.

    Attributes:
        strategy_cls: Strategy class to instantiate per combination.
        param_grid: Parameter grid defining the search space.
        objective: Objective function mapping a backtest result to a score.
        symbols: Symbols to backtest.
        start: Backtest start date.
        end: Backtest end date.
        initial_capital: Starting capital.
        commission: Commission rate.
        slippage: Slippage rate.
        interval: Data interval.
        data_manager: Optional data manager.
        config: Optional config.
        n_jobs: Number of parallel jobs.
        periods_per_year: Trading periods per year used for annualization.
        verbose: Whether to print progress.

    Examples:
        >>> from quant_trading.optimization.base import BaseOptimizer, ParameterGrid
        >>> class Dummy(BaseOptimizer):
        ...     def run(self):
        ...         return None
        >>> opt = Dummy(strategy_cls=object, param_grid=ParameterGrid())
        >>> opt.symbols
        ['AAPL']

    """

    def __init__(
        self,
        strategy_cls: type[Strategy],
        param_grid: ParameterGrid,
        objective: ObjectiveFunction = maximize_sharpe,
        symbols: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        interval: str = "1d",
        data_manager: Any | None = None,
        config: Any | None = None,
        n_jobs: int = 1,
        periods_per_year: int = 252,
        verbose: bool = False,
    ):
        """Initialize the base optimizer.

        Args:
            strategy_cls: Strategy class to instantiate per combination.
            param_grid: Parameter grid defining the search space.
            objective: Objective function mapping a backtest result to a score.
            symbols: Symbols to backtest.
            start: Backtest start date.
            end: Backtest end date.
            initial_capital: Starting capital.
            commission: Commission rate.
            slippage: Slippage rate.
            interval: Data interval.
            data_manager: Optional data manager.
            config: Optional config.
            n_jobs: Number of parallel jobs.
            periods_per_year: Trading periods per year used to annualize the
                return, volatility, Sharpe, Sortino and Calmar metrics
                (default 252 for daily data).
            verbose: Whether to print progress.

        """
        self.objective = objective
        self.strategy_cls = strategy_cls
        self.param_grid = param_grid
        self.symbols = symbols or ["AAPL"]
        self.start = start
        self.end = end
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.interval = interval
        self.data_manager = data_manager
        self.config = config
        self.n_jobs = n_jobs
        self.periods_per_year = periods_per_year
        self.verbose = verbose

    @abstractmethod
    def run(self) -> OptimizationResult:
        """Run the optimization.

        Returns:
            OptimizationResult with best parameters and score.

        """
        ...  # pragma: no cover

    def _assert_dates(self) -> tuple[datetime, datetime]:
        """Assert that start and end dates are set.

        Returns:
            Tuple of (start, end) datetimes.

        Raises:
            AssertionError: If start or end is None.

        """
        assert self.start is not None, "start date must be set"
        assert self.end is not None, "end date must be set"
        return self.start, self.end

    def _create_strategy(self, params: dict[str, Any]) -> Strategy:
        """Create strategy instance with given parameters.

        Args:
            params: Parameter dict passed to strategy constructor.

        Returns:
            Instantiated strategy.

        """
        return self.strategy_cls(**params)

    def _run_single_backtest(self, params: dict[str, Any]) -> BacktestResult:
        """Run a single backtest with given parameters.

        Args:
            params: Parameter dict for the strategy.

        Returns:
            Backtest result.

        """
        from quant_trading.backtest.engine import run_backtest

        strategy = self._create_strategy(params)
        start, end = self._assert_dates()
        return run_backtest(
            strategy=strategy,
            symbols=self.symbols,
            start=start,
            end=end,
            initial_capital=self.initial_capital,
            commission=self.commission,
            slippage=self.slippage,
            interval=self.interval,
            data_manager=self.data_manager,
            config=self.config,
            periods_per_year=self.periods_per_year,
        )

    def _evaluate_params(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], float, BacktestResult | None]:
        """Evaluate a single parameter combination.

        Args:
            params: Parameter dict to evaluate.

        Returns:
            Tuple of (params, score, result or None on failure).

        """
        try:
            result = self._run_single_backtest(params)
            score = self.objective(result)
            return params, score, result
        except (ValueError, RuntimeError, KeyError) as e:
            if self.verbose:
                print(f"Error evaluating {params}: {e}")
            return params, float("-inf"), None
