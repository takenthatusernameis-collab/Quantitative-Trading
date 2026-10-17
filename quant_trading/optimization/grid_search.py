"""Grid search parameter optimization."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from typing import Any

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


class GridSearch(BaseOptimizer):
    """Grid search optimizer for strategy parameters.

    Exhaustively searches all parameter combinations in the grid.
    Supports parallel execution via n_jobs parameter.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._combinations = self.param_grid.generate_combinations()

    def run(self) -> OptimizationResult:
        """Run grid search optimization.

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

        total = len(self._combinations)
        if self.verbose:
            print(f"GridSearch: Evaluating {total} parameter combinations...")

        if self.n_jobs > 1 and total > 1:
            all_results, best_score, best_params, best_result = self._run_parallel(
                total, all_results, best_score, best_params, best_result, start, end
            )
        else:
            all_results, best_score, best_params, best_result = self._run_sequential(
                total, all_results, best_score, best_params, best_result
            )

        end_time = datetime.now()

        if self.verbose:
            print(f"\nGridSearch complete in {(end_time - start_time).total_seconds():.1f}s")
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
        total: int,
        all_results: list,
        best_score: float,
        best_params: dict,
        best_result: Any,
    ) -> tuple[list, float, dict, Any]:
        """Run optimization sequentially."""
        for i, params in enumerate(self._combinations):
            if self.verbose:
                print(f"  [{i+1}/{total}] {params}")

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
        total: int,
        all_results: list,
        best_score: float,
        best_params: dict,
        best_result: Any,
        start: datetime,
        end: datetime,
    ) -> tuple[list, float, dict, Any]:
        """Run optimization in parallel using ProcessPoolExecutor.

        If a worker process terminates abruptly (for example under heavy
        system load when forking the parent process is unreliable), fall
        back to sequential evaluation of the remaining combinations instead
        of returning an empty result.
        """
        from quant_trading.config.settings import Config

        # Prepare data config for workers
        data_config = self.config
        if isinstance(data_config, Config):
            data_config = data_config.data

        # Get objective function (must be picklable)
        objective_func = self.objective

        def record(params: dict[str, Any], score: float, result: Any) -> None:
            nonlocal best_score, best_params, best_result

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

        processed_indices: set[int] = set()
        pool_broken = False

        try:
            with ProcessPoolExecutor(max_workers=self.n_jobs) as executor:
                # Submit all tasks and remember each future's combination index
                submitted: list = []
                for params in self._combinations:
                    submitted.append(
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
                        )
                    )
                future_to_params = dict(zip(submitted, self._combinations))
                index_of = {id(future): index for index, future in enumerate(submitted)}

                # Collect results as they complete. A worker process may be
                # terminated abruptly under heavy system load; those
                # combinations are re-run sequentially below so the run still
                # returns a result for every combination.
                for completed, future in enumerate(as_completed(submitted), 1):
                    index = index_of[id(future)]
                    params = future_to_params[future]

                    try:
                        params, score, result = future.result()
                    except BrokenProcessPool as e:
                        pool_broken = True
                        if self.verbose:
                            print(f"  [{completed}/{total}] {params} -> Error: {e}")
                        continue
                    except (ValueError, RuntimeError, KeyError) as e:
                        if self.verbose:
                            print(f"  [{completed}/{total}] {params} -> Error: {e}")
                        score = float("-inf")
                        result = None

                    if self.verbose:
                        print(f"  [{completed}/{total}] {params}")

                    record(params, score, result)
                    processed_indices.add(index)
        except BrokenProcessPool:
            pool_broken = True

        if pool_broken:
            if self.verbose:
                print(
                    "  [parallel] a worker process terminated; finishing remaining combinations sequentially"
                )
            completed = len(processed_indices)
            for index, params in enumerate(self._combinations):
                if index in processed_indices:
                    continue
                completed += 1
                params, score, result = self._evaluate_params(params)
                if self.verbose:
                    print(f"  [{completed}/{total}] {params}")
                record(params, score, result)

        return all_results, best_score, best_params, best_result

    @property
    def n_combinations(self) -> int:
        """Total number of parameter combinations."""
        return len(self._combinations)
