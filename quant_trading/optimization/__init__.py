"""Parameter optimization for trading strategies."""

from .base import (
    ObjectiveFunction,
    OptimizationResult,
    ParameterGrid,
    ParameterSpace,
    maximize_calmar,
    maximize_profit_factor,
    maximize_sharpe,
    maximize_total_return,
    maximize_win_rate,
    minimize_max_drawdown,
)

try:
    from .bayesian import BayesianOptimizer
except ImportError:
    BayesianOptimizer = None  # type: ignore[assignment,misc]
from .grid_search import GridSearch
from .random_search import RandomSearch
from .walk_forward import WalkForwardOptimizer

__all__ = [
    "BayesianOptimizer",
    "GridSearch",
    "ObjectiveFunction",
    "OptimizationResult",
    "ParameterGrid",
    "ParameterSpace",
    "RandomSearch",
    "WalkForwardOptimizer",
    "maximize_calmar",
    "maximize_profit_factor",
    "maximize_sharpe",
    "maximize_total_return",
    "maximize_win_rate",
    "minimize_max_drawdown",
]
