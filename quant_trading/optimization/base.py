"""Base classes and utilities for parameter optimization."""

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

    Can be used for both grid search (discrete values) and random search (distributions).
    """

    name: str
    values: list[Any] | None = None
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    distribution: str | None = None
    param_type: type = float  # Type to cast values to (int, float, bool)

    def __post_init__(self):
        if self.values is None and self.min_val is None:
            raise ValueError("Either values or min_val must be provided")

    def generate_grid(self) -> list[Any]:
        """Generate all values for grid search."""
        if self.values is not None:
            return [self.param_type(v) for v in self.values]
        if self.min_val is not None and self.max_val is not None and self.step is not None:
            vals = []
            v = self.min_val
            while v <= self.max_val + 1e-10:
                vals.append(self.param_type(v))
                v += self.step
            return vals
        return []

    def sample_random(self, n: int, rng: Any | None = None) -> list[Any]:
        """Sample n random values for random search."""
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
    """Collection of parameter spaces defining a grid."""

    spaces: dict[str, ParameterSpace] = field(default_factory=dict)

    def add(self, space: ParameterSpace) -> "ParameterGrid":
        self.spaces[space.name] = space
        return self

    def generate_combinations(self) -> list[dict[str, Any]]:
        """Generate all parameter combinations (Cartesian product)."""
        import itertools

        if not self.spaces:
            return [{}]

        keys = list(self.spaces.keys())
        value_lists = [self.spaces[k].generate_grid() for k in keys]

        combinations = []
        for combo in itertools.product(*value_lists):
            combinations.append(dict(zip(keys, combo)))
        return combinations

    def sample_random(self, n: int, rng: Any | None = None) -> list[dict[str, Any]]:
        """Sample n random parameter combinations."""
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
    """Objective: maximize Sharpe ratio."""
    return result.metrics.sharpe_ratio


def maximize_total_return(result: BacktestResult) -> float:
    """Objective: maximize total return percentage."""
    return result.total_return_pct


def maximize_calmar(result: BacktestResult) -> float:
    """Objective: maximize Calmar ratio."""
    return result.metrics.calmar_ratio


def minimize_max_drawdown(result: BacktestResult) -> float:
    """Objective: minimize max drawdown (negative for maximization)."""
    return -result.metrics.max_drawdown_pct


def maximize_profit_factor(result: BacktestResult) -> float:
    """Objective: maximize profit factor."""
    return result.metrics.profit_factor


def maximize_win_rate(result: BacktestResult) -> float:
    """Objective: maximize win rate."""
    return result.metrics.win_rate


@dataclass
class OptimizationResult:
    """Result of a parameter optimization run."""

    best_params: dict[str, Any]
    best_score: float
    best_result: BacktestResult | None = None
    all_results: list[dict[str, Any]] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all results to a DataFrame for analysis."""
        if not self.all_results:
            return pd.DataFrame()
        return pd.DataFrame(self.all_results)

    def get_top_n(self, n: int = 10) -> list[dict[str, Any]]:
        """Get top N results by score."""
        sorted_results = sorted(self.all_results, key=lambda x: x["score"], reverse=True)
        return sorted_results[:n]


class BaseOptimizer(ABC):
    """Base class for parameter optimizers."""

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
        verbose: bool = False,
    ):
        self.strategy_cls = strategy_cls
        self.param_grid = param_grid
        self.objective = objective
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
        self.verbose = verbose

    @abstractmethod
    def run(self) -> OptimizationResult:
        """Run the optimization."""
        ...

    def _assert_dates(self) -> tuple[datetime, datetime]:
        """Assert that start and end dates are set."""
        assert self.start is not None, "start date must be set"
        assert self.end is not None, "end date must be set"
        return self.start, self.end

    def _create_strategy(self, params: dict[str, Any]) -> Strategy:
        """Create strategy instance with given parameters."""
        return self.strategy_cls(**params)

    def _run_single_backtest(self, params: dict[str, Any]) -> BacktestResult:
        """Run a single backtest with given parameters."""
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
        )

    def _evaluate_params(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], float, BacktestResult | None]:
        """Evaluate a single parameter combination."""
        try:
            result = self._run_single_backtest(params)
            score = self.objective(result)
            return params, score, result
        except (ValueError, RuntimeError, KeyError) as e:
            if self.verbose:
                print(f"Error evaluating {params}: {e}")
            return params, float("-inf"), None
