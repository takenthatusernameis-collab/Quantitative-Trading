"""Bayesian parameter optimization using scikit-optimize.

Examples:
    Run Bayesian optimization over a strategy's parameter grid::

        from quant_trading.optimization import (
            BayesianOptimizer,
            ParameterGrid,
            ParameterSpace,
            maximize_sharpe,
        )
        from quant_trading.strategies.examples import MovingAverageCrossover

        param_grid = ParameterGrid()
        param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
        param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

        optimizer = BayesianOptimizer(
            strategy_cls=MovingAverageCrossover,
            param_grid=param_grid,
            objective=maximize_sharpe,
            symbols=["AAPL"],
            start=start,
            end=end,
            data_manager=data_manager,
            random_state=42,
        )
        result = optimizer.run()
        print(f"Best parameters: {result.best_params}")

"""

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
    """Convert numpy types to native Python types.

    Args:
        obj: Object to convert (numpy scalar, array, dict, list, or other).

    Returns:
        Native Python equivalent of the input.

    Examples:
        >>> from quant_trading.optimization.bayesian import _convert_to_native
        >>> import numpy as np
        >>> _convert_to_native(np.int64(5))
        5
        >>> _convert_to_native(np.float64(1.5))
        1.5
        >>> _convert_to_native(np.array([1, 2]))
        [1, 2]
        >>> _convert_to_native({"a": np.int64(1)})
        {'a': 1}

    """
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
    """Configuration for :class:`BayesianOptimizer`.

    Attributes:
        n_initial_points: Number of random points evaluated before the
            Gaussian Process surrogate is fit.
        n_calls: Total number of objective evaluations (initial plus guided).
        acq_func: Acquisition function name (e.g. ``"EI"`` for expected
            improvement).
        acq_optimizer: Optimizer used to propose the next point (``"auto"``
            picks a sensible default).
        random_state: Seed for reproducible optimization runs.
        noise: Observation noise added to the GP kernel.

    Examples:
        >>> from quant_trading.optimization.bayesian import BayesianOptimizerConfig
        >>> cfg = BayesianOptimizerConfig(n_calls=20, random_state=42)
        >>> cfg.n_calls
        20
        >>> cfg.acq_func
        'EI'

    """

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

    Examples:
        optimizer = BayesianOptimizer(
            strategy_cls=MovingAverageCrossover,
            param_grid=param_grid,
            objective=maximize_sharpe,
            symbols=["AAPL"],
            start=start,
            end=end,
            data_manager=data_manager,
            random_state=42,
        )
        result = optimizer.run()
        assert result.best_params is not None

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
        periods_per_year: int = 252,
        verbose: bool = False,
    ):
        """Initialize the Bayesian optimizer.

        Args:
            strategy_cls: Strategy class to instantiate per candidate.
            param_grid: Parameter grid defining the search space.
            objective: Objective function mapping a backtest result to a
                score. Defaults to :func:`maximize_sharpe` when ``None``.
            symbols: Symbols to backtest.
            start: Backtest start date.
            end: Backtest end date.
            initial_capital: Starting capital.
            commission: Commission rate.
            slippage: Slippage rate.
            interval: Data interval.
            data_manager: Optional data manager.
            config: Optional config.
            n_initial_points: Number of initial random evaluations.
            n_calls: Total number of objective evaluations.
            acq_func: Acquisition function name.
            acq_optimizer: Acquisition optimizer name.
            random_state: Seed for reproducibility.
            periods_per_year: Trading periods per year used to annualize the
                return, volatility, Sharpe, Sortino and Calmar metrics.
            verbose: Whether to print progress.

        Raises:
            ImportError: If ``scikit-optimize`` is not installed.

        """
        try:
            from skopt.utils import use_named_args
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
            periods_per_year=periods_per_year,
            verbose=verbose,
        )

        self.n_initial_points = n_initial_points
        self.n_calls = n_calls
        self.acq_func = acq_func
        self.acq_optimizer = acq_optimizer
        self.random_state = random_state
        self._space = self._create_skopt_space()
        self._use_named_args = use_named_args(self._space)

    def _create_skopt_space(self) -> list[Any]:
        """Convert the parameter grid into a scikit-optimize search space.

        Each :class:`~quant_trading.optimization.base.ParameterSpace` is
        translated to a scikit-optimize dimension:

        * Discrete ``values`` become a :class:`Categorical` dimension.
        * Integer bounds become an :class:`Integer` dimension.
        * Float bounds become a :class:`Real` dimension, using a
            ``"log-uniform"`` prior when ``distribution == "log"``.

        Returns:
            List of scikit-optimize dimension objects, one per parameter.

        """
        from skopt.space import Categorical, Integer, Real

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
        from skopt import gp_minimize

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

        @self._use_named_args  # type: ignore[untyped-decorator]
        def objective_func(**params: Any) -> float:
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
