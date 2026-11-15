from __future__ import annotations

from typing import TYPE_CHECKING

from .base import (
    BaseOptimizer,
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
    from .bayesian import BayesianOptimizer as BayesianOptimizer  # pragma: no cover
else:
    try:
        from .bayesian import BayesianOptimizer as _BayesianOptimizer
    except ImportError:  # pragma: no cover
        _BayesianOptimizer = None
    BayesianOptimizer = _BayesianOptimizer
from .grid_search import GridSearch
from .random_search import RandomSearch
from .sensitivity import (
    SensitivityConfig,
    create_1d_sensitivity_plot,
    create_2d_sensitivity_heatmap,
    create_parameter_interaction_heatmap,
    generate_sensitivity_report_html,
    prepare_sensitivity_data,
)
from .walk_forward import WalkForwardOptimizer

__all__ = [
    "BaseOptimizer",
    "BayesianOptimizer",
    "BayesianOptimizerConfig",
    "GridSearch",
    "ObjectiveFunction",
    "OptimizationResult",
    "ParameterGrid",
    "ParameterSpace",
    "RandomSearch",
    "SensitivityConfig",
    "WalkForwardOptimizer",
    "create_1d_sensitivity_plot",
    "create_2d_sensitivity_heatmap",
    "create_parameter_interaction_heatmap",
    "generate_sensitivity_report_html",
    "maximize_calmar",
    "maximize_profit_factor",
    "maximize_sharpe",
    "maximize_sortino",
    "maximize_total_return",
    "maximize_win_rate",
    "minimize_max_drawdown",
    "prepare_sensitivity_data",
]
