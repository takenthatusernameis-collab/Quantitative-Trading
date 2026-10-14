"""Random search parameter optimization."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import numpy as np

from quant_trading.backtest.engine import BacktestResult

from .base import BaseOptimizer, OptimizationResult


def _evaluate_params_worker(
    strategy_cls: type,
    param_grid_dict: dict[str, Any],
    objective_func: Any,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_capital: float,
    commission: float,
    slippage: float,
    interval: str,
    data_config: Any,
    params: dict[str, Any],
) -> tuple[dict[str, Any], float, Any]:
    """Worker function for parallel parameter evaluation.

    This function must be at module level to be picklable.
    """
    from quant_trading.backtest.engine import run_backtest
    from quant_trading.config.settings import Config, DataConfig
    from quant_trading.data.providers import create_data_manager_from_config

    # Create strategy instance
    strategy = strategy_cls(**params)

    # Create data manager from config if provided
    data_manager = None
    if data_config is not None:
        if isinstance(data_config, Config):
            data_manager = create_data_manager_from_config(data_config.data)
        elif isinstance(data_config, DataConfig):
            data_manager = create_data_manager_from_config(data_config)

    # Run backtest
    result = run_backtest(
        strategy=strategy,
        symbols=symbols,
        start=start,
        end=end,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        interval=interval,
        data_manager=data_manager,
        config=data_config,
    )

    # Evaluate objective
    score = objective_func(result)

    return params, score, result


class RandomSearch(BaseOptimizer):
    """Random search optimizer for strategy parameters.

    Samples random parameter combinations from the parameter space.
    More efficient than grid search for high-dimensional spaces.
    Supports parallel execution via n_jobs parameter.
    """

    def __init__(
        self,
        n_iter: int = 100,
        random_state: int | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.n_iter = n_iter
        self.random_state = random_state
        self._rng = np.random.default_rng(random_state)

    def run(self) -> OptimizationResult:
        """Run random search optimization.

        Returns:
            OptimizationResult with best parameters and all results.
        """
        start_time = datetime.now()
        all_results: list[dict[str, Any]] = []
        best_score = float("-inf")
        best_params: dict[str, Any] = {}
        best_result: BacktestResult | None = None

        # Assert dates are set (required for parallel execution)
        start, end = self._assert_dates()

        combinations = self.param_grid.sample_random(self.n_iter, self._rng)

        if self.verbose:
            print(f"RandomSearch: Evaluating {self.n_iter} random parameter combinations...")

        if self.n_jobs > 1 and self.n_iter > 1:
            all_results, best_score, best_params, best_result = self._run_parallel(
                combinations, all_results, best_score, best_params, best_result, start, end
            )
        else:
            all_results, best_score, best_params, best_result = self._run_sequential(
                combinations, all_results, best_score, best_params, best_result
            )

        end_time = datetime.now()

        if self.verbose:
            print(f"\nRandomSearch complete in {(end_time - start_time).total_seconds():.1f}s")
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

    def _run_sequential(
        self,
        combinations: list[dict[str, Any]],
        all_results: list,
        best_score: float,
        best_params: dict,
        best_result: Any,
    ) -> tuple[list, float, dict, Any]:
        """Run optimization sequentially."""
        for i, params in enumerate(combinations):
            if self.verbose:
                print(f"  [{i+1}/{self.n_iter}] {params}")

            params, score, result = self._evaluate_params(params)

            all_results.append(
                {
                    "params": params,
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
                best_params = params
                best_result = result
                if self.verbose:
                    print(f"    -> New best: {score:.4f}")

        return all_results, best_score, best_params, best_result

    def _run_parallel(
        self,
        combinations: list[dict[str, Any]],
        all_results: list,
        best_score: float,
        best_params: dict,
        best_result: Any,
        start: datetime,
        end: datetime,
    ) -> tuple[list, float, dict, Any]:
        """Run optimization in parallel using ProcessPoolExecutor."""
        from quant_trading.config.settings import Config

        # Prepare data config for workers
        data_config = self.config
        if isinstance(data_config, Config):
            data_config = data_config.data

        # Get objective function (must be picklable)
        objective_func = self.objective

        with ProcessPoolExecutor(max_workers=self.n_jobs) as executor:
            # Submit all tasks
            future_to_params = {
                executor.submit(
                    _evaluate_params_worker,
                    self.strategy_cls,
                    {k: v.__dict__ for k, v in self.param_grid.spaces.items()},
                    objective_func,
                    self.symbols,
                    start,
                    end,
                    self.initial_capital,
                    self.commission,
                    self.slippage,
                    self.interval,
                    data_config,
                    params,
                ): params
                for params in combinations
            }

            # Collect results as they complete
            for completed, future in enumerate(as_completed(future_to_params), 1):
                params = future_to_params[future]

                try:
                    params, score, result = future.result()
                except (ValueError, RuntimeError, KeyError) as e:
                    if self.verbose:
                        print(f"  [{completed}/{self.n_iter}] {params} -> Error: {e}")
                    score = float("-inf")
                    result = None

                if self.verbose:
                    print(f"  [{completed}/{self.n_iter}] {params}")

                all_results.append(
                    {
                        "params": params,
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
                    best_params = params
                    best_result = result
                    if self.verbose:
                        print(f"    -> New best: {score:.4f}")

        return all_results, best_score, best_params, best_result