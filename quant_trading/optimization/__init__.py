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
from .bayesian import BayesianOptimizerConfig

_BayesianOptimizer: type | None
if TYPE_CHECKING:
    from .bayesian import BayesianOptimizer as BayesianOptimizer
else:
    try:
        from .bayesian import BayesianOptimizer as _BayesianOptimizer
    except ImportError:  # pragma: no cover
        _BayesianOptimizer = None
    BayesianOptimizer = _BayesianOptimizer
from .grid_search import GridSearch
from .random_search import RandomSearch
from .walk_forward import WalkForwardOptimizer

__all__ = [
    "BayesianOptimizer",
    "BayesianOptimizerConfig",
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
