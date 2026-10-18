"""Grid search parameter optimization.

Grid search exhaustively evaluates every combination of the parameter grid,
making it ideal for small, well-understood search spaces where the optimum is
guaranteed to be found. For high-dimensional spaces, consider
:mod:`quant_trading.optimization.random_search` instead.

Examples:
    >>> from datetime import datetime, timedelta
    >>> from quant_trading.optimization.grid_search import GridSearch
    >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace
    >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    >>> optimizer = GridSearch(strategy_cls=None, param_grid=grid)
    >>> optimizer.n_combinations
    2
    >>> optimizer.symbols
    ['AAPL']
"""

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
    """Evaluate a single parameter combination in a worker process.

    This function must remain at module level so it can be pickled and sent to
    a :class:`concurrent.futures.ProcessPoolExecutor` worker.

    Args:
        strategy_cls: Strategy class to instantiate with ``params``.
        param_grid_dict: Mapping of parameter name to its
            :class:`~quant_trading.optimization.base.ParameterSpace` (used only
            to preserve the original grid definition in the worker).
        objective_func: Callable mapping a backtest result to a score.
        symbols: Symbols to backtest.
        start: Backtest start date.
        end: Backtest end date.
        initial_capital: Starting capital for the backtest.
        commission: Commission rate.
        slippage: Slippage rate.
        interval: Data interval.
        data_config: Optional config (``Config`` or ``DataConfig``) used to
            build a data manager inside the worker.
        params: Parameter combination to evaluate.

    Returns:
        Tuple of ``(params, score, result)`` where ``result`` is the
        :class:`~quant_trading.backtest.engine.BacktestResult` (or ``None`` on
        failure) and ``score`` is ``float("-inf")`` when the backtest fails.

    Examples:
        >>> from quant_trading.optimization.base import ParameterSpace
        >>> import inspect
        >>> "param_grid_dict" in inspect.signature(_evaluate_params_worker).parameters
        True
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

    Exhaustively evaluates every combination of the parameter grid. Because the
    search space is fully enumerated, grid search guarantees finding the global
    optimum *within the grid*, but the number of combinations grows
    multiplicatively with the number of parameters, making it unsuitable for
    high-dimensional spaces (see
    :class:`~quant_trading.optimization.random_search.RandomSearch` instead).

    Execution is sequential by default; set ``n_jobs > 1`` to parallelize across
    worker processes. If a worker dies under heavy system load, the remaining
    combinations are evaluated sequentially so a result is still returned for
    every combination.

    Attributes:
        _combinations: Pre-computed list of all parameter combinations
            (Cartesian product of the grid). Exposed via :attr:`n_combinations`.

    Examples:
        >>> from quant_trading.optimization.grid_search import GridSearch
        >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace
        >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
        >>> optimizer = GridSearch(strategy_cls=None, param_grid=grid)
        >>> optimizer.n_combinations
        2
        >>> optimizer.symbols
        ['AAPL']
    """

    def __init__(self, *args, **kwargs):
        """Initialize the grid search optimizer.

        All arguments are forwarded to
        :meth:`quant_trading.optimization.base.BaseOptimizer.__init__`; see that
        method for the full parameter list (``strategy_cls``, ``param_grid``,
        ``objective``, ``symbols``, ``start``, ``end``, ``initial_capital``,
        ``commission``, ``slippage``, ``interval``, ``data_manager``,
        ``config``, ``n_jobs``, ``verbose``).

        After delegating to the base class, the full Cartesian product of the
        parameter grid is pre-computed and stored on ``self._combinations``.

        Args:
            *args: Positional arguments forwarded to ``BaseOptimizer.__init__``.
            **kwargs: Keyword arguments forwarded to ``BaseOptimizer.__init__``.

        Returns:
            None
        """
        super().__init__(*args, **kwargs)
        self._combinations = self.param_grid.generate_combinations()

    def run(self) -> OptimizationResult:
        """Run grid search optimization.

        Evaluates every parameter combination in the grid (either sequentially
        or in parallel, depending on ``n_jobs``) and returns the combination
        with the highest objective score.

        Returns:
            :class:`~quant_trading.optimization.base.OptimizationResult`
            containing ``best_params``, ``best_score``, ``best_result``, and
            ``all_results`` (one entry per combination).

        Examples:
            >>> from quant_trading.optimization.grid_search import GridSearch
            >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace
            >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5], param_type=int))
            >>> optimizer = GridSearch(strategy_cls=None, param_grid=grid)
            >>> result = optimizer.run()  # doctest: +SKIP
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
        """Evaluate every combination in ``self._combinations`` one at a time.

        This is the default execution path when ``n_jobs == 1`` or when there is
        only a single combination. Each combination is backtested via
        :meth:`_evaluate_params` and the running best is tracked.

        Args:
            total: Total number of combinations (used for progress output).
            all_results: List to append per-combination result dicts to.
            best_score: Current best score (updated in place).
            best_params: Current best parameters (updated in place).
            best_result: Current best backtest result (updated in place).

        Returns:
            Tuple of ``(all_results, best_score, best_params, best_result)``
            with the running best updated.

        Examples:
            >>> from quant_trading.optimization.grid_search import GridSearch
            >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace
            >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5], param_type=int))
            >>> optimizer = GridSearch(strategy_cls=None, param_grid=grid)
            >>> optimizer._run_sequential(1, [], float("-inf"), {}, None)  # doctest: +SKIP
        """
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
        """Evaluate combinations in parallel using a ``ProcessPoolExecutor``.

        Each combination is submitted to a worker process via the module-level
        :func:`_evaluate_params_worker`. Results are collected as they
        complete and the running best is updated. If a worker process
        terminates abruptly (for example under heavy system load when forking
        the parent process is unreliable), the combinations that did not
        complete are re-evaluated sequentially so a result is still returned
        for every combination.

        Args:
            total: Total number of combinations (used for progress output).
            all_results: List to append per-combination result dicts to.
            best_score: Current best score (updated in place).
            best_params: Current best parameters (updated in place).
            best_result: Current best backtest result (updated in place).
            start: Backtest start date forwarded to workers.
            end: Backtest end date forwarded to workers.

        Returns:
            Tuple of ``(all_results, best_score, best_params, best_result)``
            with the running best updated.

        Examples:
            >>> from quant_trading.optimization.grid_search import GridSearch
            >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace
            >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5], param_type=int))
            >>> optimizer = GridSearch(strategy_cls=None, param_grid=grid)
            >>> optimizer._run_parallel(1, [], float("-inf"), {}, None, None, None)  # doctest: +SKIP
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
