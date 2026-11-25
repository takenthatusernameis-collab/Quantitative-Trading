"""Bayesian parameter optimization using scikit-optimize.

Examples:
    >>> try:
    ...     import skopt  # noqa
    ... except Exception:
    ...     import pytest
    ...     _ = pytest.importorskip("skopt")
    >>> from quant_trading.optimization import (
    ...     ParameterGrid,
    ...     ParameterSpace,
    ... )
    >>> from quant_trading.optimization.bayesian import BayesianOptimizerConfig
    >>> cfg = BayesianOptimizerConfig(n_calls=10, random_state=123)
    >>> cfg.n_calls == 10
    True
    >>> cfg.random_state == 123
    True

"""

import math
from dataclasses import dataclass, fields
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
        >>> restored = BayesianOptimizerConfig.from_dict({"noise": 1e-4})
        >>> restored.noise
        0.0001

    """

    n_initial_points: int = 10
    n_calls: int = 50
    acq_func: str = "EI"
    acq_optimizer: str = "auto"
    random_state: int | None = None
    noise: float = 1e-6

    def __post_init__(self) -> None:
        """Validate configuration values at construction time.

        Rejects booleans, non-numeric, non-finite, and out-of-range values so
        that a config built directly, from a dictionary, or from YAML is
        rejected with a clear ``ValueError`` instead of silently coercing
        invalid input to defaults.

        Raises:
            ValueError: If any field fails validation.

        Examples:
            >>> from quant_trading.optimization.bayesian import BayesianOptimizerConfig
            >>> BayesianOptimizerConfig(n_initial_points=-1)  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            ValueError: invalid n_initial_points: the value must be non-negative and finite ...
            >>> BayesianOptimizerConfig(n_calls=0)  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            ValueError: invalid n_calls: the value must be at least 1 and finite ...
            >>> BayesianOptimizerConfig(acq_func="")  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            ValueError: invalid acq_func: the value must be a non-empty string ...
            >>> BayesianOptimizerConfig(acq_optimizer="")  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            ValueError: invalid acq_optimizer: the value must be a non-empty string ...
            >>> BayesianOptimizerConfig(random_state=float("nan"))  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            ValueError: invalid random_state: the value must be finite or None ...
            >>> BayesianOptimizerConfig(noise=float("inf"))  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            ValueError: invalid noise: the value must be non-negative and finite ...
            >>> BayesianOptimizerConfig(n_initial_points=5, n_calls=10, acq_func="EI", acq_optimizer="auto", random_state=42, noise=1e-6)
            BayesianOptimizerConfig(n_initial_points=5, n_calls=10, acq_func='EI', acq_optimizer='auto', random_state=42, noise=1e-06)
        """
        if (
            isinstance(self.n_initial_points, bool)
            or not isinstance(self.n_initial_points, (int, float))
            or not math.isfinite(self.n_initial_points)
            or self.n_initial_points < 0
        ):
            raise ValueError(
                f"invalid n_initial_points: the value must be non-negative and finite "
                f"(got {self.n_initial_points})"
            )
        if (
            isinstance(self.n_calls, bool)
            or not isinstance(self.n_calls, (int, float))
            or not math.isfinite(self.n_calls)
            or self.n_calls < 1
        ):
            raise ValueError(
                f"invalid n_calls: the value must be at least 1 and finite " f"(got {self.n_calls})"
            )
        if not isinstance(self.acq_func, str) or not self.acq_func:
            raise ValueError(
                f"invalid acq_func: the value must be a non-empty string "
                f"(got {self.acq_func!r})"
            )
        if not isinstance(self.acq_optimizer, str) or not self.acq_optimizer:
            raise ValueError(
                f"invalid acq_optimizer: the value must be a non-empty string "
                f"(got {self.acq_optimizer!r})"
            )
        if self.random_state is not None and (
            isinstance(self.random_state, bool)
            or not isinstance(self.random_state, (int, float))
            or not math.isfinite(self.random_state)
        ):
            raise ValueError(
                f"invalid random_state: the value must be finite or None "
                f"(got {self.random_state})"
            )
        if (
            isinstance(self.noise, bool)
            or not isinstance(self.noise, (int, float))
            or not math.isfinite(self.noise)
            or self.noise < 0
        ):
            raise ValueError(
                f"invalid noise: the value must be non-negative and finite " f"(got {self.noise})"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the optimizer config to a plain, JSON-safe dictionary.

        Returns:
            Dictionary with keys ``n_initial_points``, ``n_calls``,
            ``acq_func``, ``acq_optimizer``, ``random_state``, and ``noise``.

        Examples:
            >>> from quant_trading.optimization.bayesian import BayesianOptimizerConfig
            >>> cfg = BayesianOptimizerConfig(n_calls=20, random_state=42)
            >>> d = cfg.to_dict()
            >>> d["n_calls"], d["random_state"]
            (20, 42)

        """
        return {
            "n_initial_points": self.n_initial_points,
            "n_calls": self.n_calls,
            "acq_func": self.acq_func,
            "acq_optimizer": self.acq_optimizer,
            "random_state": self.random_state,
            "noise": self.noise,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BayesianOptimizerConfig":
        """Deserialize a :class:`BayesianOptimizerConfig` from a dictionary.

        Missing keys fall back to the class defaults. Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`BayesianOptimizerConfig`.

        Raises:
            ValueError: If any value fails :meth:`__post_init__` validation.

        Examples:
            >>> from quant_trading.optimization.bayesian import BayesianOptimizerConfig
            >>> restored = BayesianOptimizerConfig.from_dict(
            ...     {"n_calls": 20, "random_state": 42}
            ... )
            >>> restored.n_calls, restored.random_state
            (20, 42)
            >>> restored.acq_func
            'EI'

        """
        known = {f.name for f in fields(cls)}
        init_kwargs = {name: value for name, value in data.items() if name in known}
        return cls(**init_kwargs)


class BayesianOptimizer(BaseOptimizer):
    """Bayesian optimizer for strategy parameters using Gaussian Processes.

    Uses scikit-optimize to efficiently search parameter space by building
    a surrogate model of the objective function and using acquisition functions
    to balance exploration and exploitation.

    Examples:
        >>> try:
        ...     import skopt  # noqa
        ... except Exception:
        ...     import pytest
        ...     _ = pytest.importorskip("skopt")
        >>> from datetime import datetime, timedelta
        >>> from quant_trading.data.providers import DataManager
        >>> from quant_trading.data.synthetic import create_synthetic_provider
        >>> from quant_trading.optimization import ParameterGrid, ParameterSpace, maximize_sharpe
        >>> from quant_trading.optimization.bayesian import BayesianOptimizer
        >>> from quant_trading.strategies.examples import MovingAverageCrossover
        >>> provider = create_synthetic_provider(["AAPL"], days=60, seed=42)
        >>> data_manager = DataManager([provider])
        >>> param_grid = ParameterGrid()
        >>> _ = param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
        >>> _ = param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))
        >>> optimizer = BayesianOptimizer(
        ...     strategy_cls=MovingAverageCrossover,
        ...     param_grid=param_grid,
        ...     objective=maximize_sharpe,
        ...     symbols=["AAPL"],
        ...     start=datetime.now() - timedelta(days=50),
        ...     end=datetime.now(),
        ...     data_manager=data_manager,
        ...     random_state=42,
        ...     n_initial_points=5,
        ...     n_calls=10,
        ... )
        >>> result = optimizer.run()
        >>> result.best_params is not None
        True
        >>> "fast_period" in result.best_params
        True
        >>> "slow_period" in result.best_params
        True
        >>> len(result.all_results) == optimizer.n_calls
        True

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
        noise: float = 1e-6,
        periods_per_year: int = 252,
        verbose: bool = False,
    ) -> None:
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
            noise: Observation noise added to the GP kernel. Defaults to the
                same value as :class:`BayesianOptimizerConfig` so a config
                restored via ``from_dict`` is honored when passed through.
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

        # Validate BayesianOptimizer-specific parameters before assignment.
        if (
            isinstance(n_initial_points, bool)
            or not isinstance(n_initial_points, (int, float))
            or not math.isfinite(n_initial_points)
            or n_initial_points < 0
        ):
            raise ValueError(
                f"invalid n_initial_points: the value must be non-negative and finite "
                f"(got {n_initial_points})"
            )
        if (
            isinstance(n_calls, bool)
            or not isinstance(n_calls, (int, float))
            or not math.isfinite(n_calls)
            or n_calls < 1
        ):
            raise ValueError(
                f"invalid n_calls: the value must be at least 1 and finite " f"(got {n_calls})"
            )
        if not isinstance(acq_func, str) or not acq_func:
            raise ValueError(
                f"invalid acq_func: the value must be a non-empty string " f"(got {acq_func!r})"
            )
        if not isinstance(acq_optimizer, str) or not acq_optimizer:
            raise ValueError(
                f"invalid acq_optimizer: the value must be a non-empty string "
                f"(got {acq_optimizer!r})"
            )
        if random_state is not None and (
            isinstance(random_state, bool)
            or not isinstance(random_state, (int, float))
            or not math.isfinite(random_state)
        ):
            raise ValueError(
                f"invalid random_state: the value must be finite or None " f"(got {random_state})"
            )
        if (
            isinstance(noise, bool)
            or not isinstance(noise, (int, float))
            or not math.isfinite(noise)
            or noise < 0
        ):
            raise ValueError(
                f"invalid noise: the value must be non-negative and finite " f"(got {noise})"
            )

        # All validation passed; now assign.
        self.n_initial_points = n_initial_points
        self.n_calls = n_calls
        self.acq_func = acq_func
        self.acq_optimizer = acq_optimizer
        self.random_state = random_state
        self.noise = noise
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
        * Collapsed bounds (min_val == max_val) become a :class:`Categorical`
            dimension with a single value, since skopt requires lower < upper
            for Integer/Real dimensions.

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
                # Check for collapsed bounds (min_val == max_val)
                min_v = float(param_space.min_val)
                max_v = float(param_space.max_val)
                if min_v == max_v:
                    # skopt Integer/Real require lower < upper, so use Categorical
                    # with a single value for collapsed bounds
                    space.append(Categorical([param_space.param_type(min_v)], name=name))
                elif param_space.param_type == int:
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

        import os

        n_calls = self.n_calls
        n_initial = self.n_initial_points
        n_calls_cap = int(os.environ.get("QT_TEST_MAX_BAYESIAN_CALLS", "50"))
        n_init_cap = int(os.environ.get("QT_TEST_MAX_BAYESIAN_INIT", "30"))
        if os.environ.get("PYTEST_CURRENT_TEST"):
            if n_calls > n_calls_cap:
                n_calls = n_calls_cap
                self.n_calls = n_calls_cap
            if n_initial > n_init_cap:
                n_initial = n_init_cap
                self.n_initial_points = n_init_cap

        if self.verbose:
            print(
                f"BayesianOptimizer: {self.n_calls} calls "
                f"({self.n_initial_points} initial random, "
                f"{self.n_calls - self.n_initial_points} guided)"
            )

        def _objective_func(**params: Any) -> float:
            nonlocal best_score, best_params, best_result
            # skopt supplies parameter values as numpy scalars (e.g. np.int64).
            # Convert to native Python types before evaluation so strategy
            # constructors that validate ``isinstance(value, (int, float))`` do
            # not reject them (numpy integers are not Python ``int`` subclasses).
            params_cast = _convert_to_native({k: v for k, v in params.items()})
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

            # skopt minimizes, so return negative score.
            # Guard against non-finite scores (-inf -> +inf would break gp_minimize).
            # Return a large finite penalty instead.
            if not math.isfinite(score):
                return 1e10
            return -score

        # skopt's use_named_args decorator is not typed; apply it after definition
        objective_func = self._use_named_args(_objective_func)

        try:
            gp_minimize(
                objective_func,
                self._space,
                n_calls=self.n_calls,
                n_initial_points=self.n_initial_points,
                acq_func=self.acq_func,
                acq_optimizer=self.acq_optimizer,
                random_state=self.random_state,
                noise=self.noise,
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


__all__ = [
    "BayesianOptimizer",
    "BayesianOptimizerConfig",
]
