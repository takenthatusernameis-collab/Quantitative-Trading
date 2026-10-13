"""Bayesian parameter optimization using scikit-optimize."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import (
    BaseOptimizer,
    ObjectiveFunction,
    OptimizationResult,
    ParameterGrid,
)


def _convert_to_native(obj: Any) -> Any:
    """Convert numpy types to native Python types."""
    import numpy as np

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _convert_to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert_to_native(v) for v in obj]
    return obj


@dataclass
class BayesianOptimizerConfig:
    """Configuration for Bayesian optimizer."""

    n_initial_points: int = 10
    n_calls: int = 50
    acq_func: str = "EI"
    acq_optimizer: str = "auto"
    random_state: int | None = None
    noise: float = 1e-6


class BayesianOptimizer(BaseOptimizer):
    """Bayesian optimizer for strategy parameters using Gaussian Processes.

    Uses scikit-optimize to efficiently search parameter space by building
    a surrogate model of the objective function and using acquisition functions
    to balance exploration and exploitation.
    """

    def __init__(
        self,
        strategy_cls: type,
        param_grid: ParameterGrid,
        objective: ObjectiveFunction | None = None,
        symbols: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        interval: str = "1d",
        data_manager: Any | None = None,
        config: Any | None = None,
        n_initial_points: int = 10,
        n_calls: int = 50,
        acq_func: str = "EI",
        acq_optimizer: str = "auto",
        random_state: int | None = None,
        verbose: bool = False,
    ):
        try:
            from skopt.utils import use_named_args  # type: ignore[import]
        except ImportError as e:
            raise ImportError(
                "BayesianOptimizer requires scikit-optimize. "
                "Install with: pip install quant-trading[bayesian]"
            ) from e

        if objective is None:
            from .base import maximize_sharpe

            objective = maximize_sharpe

        super().__init__(
            strategy_cls=strategy_cls,
            param_grid=param_grid,
            objective=objective,
            symbols=symbols,
            start=start,
            end=end,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            interval=interval,
            data_manager=data_manager,
            config=config,
            verbose=verbose,
        )

        self.n_initial_points = n_initial_points
        self.n_calls = n_calls
        self.acq_func = acq_func
        self.acq_optimizer = acq_optimizer
        self.random_state = random_state
        self._space = self._create_skopt_space()
        self._use_named_args = use_named_args(self._space)

    def _create_skopt_space(self) -> list:
        """Convert ParameterGrid to skopt space."""
        from skopt.space import Categorical, Integer, Real  # type: ignore[import]

        space = []
        for name, param_space in self.param_grid.spaces.items():
            if param_space.values is not None:
                # Categorical space for discrete values
                space.append(Categorical(param_space.values, name=name))
            elif param_space.min_val is not None and param_space.max_val is not None:
                if param_space.param_type == int:
                    space.append(
                        Integer(
                            int(param_space.min_val),
                            int(param_space.max_val),
                            name=name,
                        )
                    )
                else:
                    prior = "log-uniform" if param_space.distribution == "log" else "uniform"
                    space.append(
                        Real(
                            float(param_space.min_val),
                            float(param_space.max_val),
                            prior=prior,
                            name=name,
                        )
                    )
        return space

    def run(self) -> OptimizationResult:
        """Run Bayesian optimization.

        Returns:
            OptimizationResult with best parameters and all results.
        """
        from skopt import gp_minimize  # type: ignore[import]

        start_time = datetime.now()
        all_results = []
        best_score = float("-inf")
        best_params: dict[str, Any] = {}
        best_result = None

        if self.verbose:
            print(
                f"BayesianOptimizer: {self.n_calls} calls "
                f"({self.n_initial_points} initial random, "
                f"{self.n_calls - self.n_initial_points} guided)"
            )

        @self._use_named_args
        def objective_func(**params):
            nonlocal best_score, best_params, best_result
            params_cast = {k: v for k, v in params.items()}
            params_eval, score, result = self._evaluate_params(params_cast)

            # Convert numpy types to native Python types for JSON serialization
            params_eval = _convert_to_native(params_eval)

            all_results.append(
                {
                    "params": params_eval,
                    "score": score,
                    "total_return_pct": result.total_return_pct if result else None,
                    "sharpe_ratio": result.metrics.sharpe_ratio if result else None,
                    "max_drawdown_pct": result.metrics.max_drawdown_pct if result else None,
                    "win_rate": result.metrics.win_rate if result else None,
                    "profit_factor": result.metrics.profit_factor if result else None,
                    "num_trades": result.metrics.num_trades if result else None,
                }
            )

            if score > best_score:
                best_score = score
                best_params = params_eval
                best_result = result
                if self.verbose:
                    print(f"  -> New best: {score:.4f} with {params_eval}")

            # skopt minimizes, so return negative score
            return -score

        try:
            gp_minimize(
                objective_func,
                self._space,
                n_calls=self.n_calls,
                n_initial_points=self.n_initial_points,
                acq_func=self.acq_func,
                acq_optimizer=self.acq_optimizer,
                random_state=self.random_state,
                noise=1e-6,
                verbose=self.verbose,
            )
        except (ValueError, RuntimeError, KeyError) as e:
            if self.verbose:
                print(f"Bayesian optimization error: {e}")

        end_time = datetime.now()

        if self.verbose:
            print(f"\nBayesianOptimizer complete in {(end_time - start_time).total_seconds():.1f}s")
            print(f"Best parameters: {best_params}")
            print(f"Best score: {best_score:.4f}")

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            best_result=best_result,
            all_results=all_results,
            start_time=start_time,
            end_time=end_time,
        )
