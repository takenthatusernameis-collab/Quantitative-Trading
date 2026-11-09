from __future__ import annotations

from typing import TYPE_CHECKING

from .base import (
    ObjectiveFunction,
    OptimizationResult,
    ParameterGrid,
    ParameterSpace,
    maximize_calmar,
    maximize_profit_factor,
    maximize_sharpe,
    maximize_sortino,
    maximize_total_return,
    maximize_win_rate,
    minimize_max_drawdown,
)

if TYPE_CHECKING:
    from .bayesian import BayesianOptimizer as BayesianOptimizer
else:
    try:
        from .bayesian import BayesianOptimizer
    except ImportError:  # pragma: no cover
        BayesianOptimizer = None  # type: ignore[assignment]
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
    "maximize_sortino",
    "maximize_total_return",
    "maximize_win_rate",
    "minimize_max_drawdown",
]
