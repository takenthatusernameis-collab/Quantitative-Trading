"""Walk-forward optimization for strategy parameters.

Walk-forward analysis splits data into in-sample (training) and out-of-sample (testing)
periods, optimizing parameters on in-sample data and validating on out-of-sample data.
This reduces overfitting compared to simple backtest optimization.

Examples:
    >>> from datetime import datetime
    >>> from quant_trading.optimization.walk_forward import WalkForwardWindow
    >>> w = WalkForwardWindow(
    ...     train_start=datetime(2024, 1, 1),
    ...     train_end=datetime(2024, 2, 1),
    ...     test_start=datetime(2024, 2, 1),
    ...     test_end=datetime(2024, 3, 1),
    ... )
    >>> w.to_dict()["test_start"].isoformat()
    '2024-02-01T00:00:00'

"""

# mypy: disable-error-code="no-any-return"

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from quant_trading.backtest.engine import BacktestResult, run_backtest
from quant_trading.optimization.base import (
    BaseOptimizer,
    ObjectiveFunction,
    ParameterGrid,
    maximize_sharpe,
)
from quant_trading.optimization.grid_search import GridSearch
from quant_trading.strategies.base import Strategy


@dataclass
class WalkForwardWindow:
    """A single walk-forward window with in-sample and out-of-sample periods.

    Each window represents one fold of the walk-forward procedure: parameters
    are optimized on the in-sample (training) span and then validated on the
    adjacent out-of-sample (test) span. The :attr:`best_params`,
    :attr:`train_result`, and :attr:`test_result` fields are populated by
    :meth:`WalkForwardOptimizer.run` after optimization and validation complete.

    Attributes:
        train_start: Start timestamp of the in-sample (training) period.
        train_end: End timestamp of the in-sample (training) period.
        test_start: Start timestamp of the out-of-sample (test) period.
        test_end: End timestamp of the out-of-sample (test) period.
        best_params: Parameter combination selected by the optimizer on the
            training data. ``None`` until optimization runs.
        train_result: Backtest result on the training data using the best
            parameters. ``None`` until optimization runs.
        test_result: Backtest result on the out-of-sample data using the best
            parameters. ``None`` until validation runs.

    Examples:
        >>> from datetime import datetime
        >>> from quant_trading.optimization.walk_forward import WalkForwardWindow
        >>> w = WalkForwardWindow(
        ...     train_start=datetime(2024, 1, 1),
        ...     train_end=datetime(2024, 2, 1),
        ...     test_start=datetime(2024, 2, 1),
        ...     test_end=datetime(2024, 3, 1),
        ... )
        >>> w.to_dict()["test_start"].isoformat()
        '2024-02-01T00:00:00'
        >>> w.best_params is None
        True

    """

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: dict[str, Any] | None = None
    train_result: BacktestResult | None = None
    test_result: BacktestResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the window to a plain dictionary.

        Returns:
            Dictionary with keys ``train_start``, ``train_end``,
            ``test_start``, ``test_end``, ``best_params``, ``train_result``,
            and ``test_result``. Backtest results are included as-is (they are
            not recursively serialized).

        Examples:
            >>> from datetime import datetime
            >>> from quant_trading.optimization.walk_forward import WalkForwardWindow
            >>> w = WalkForwardWindow(
            ...     train_start=datetime(2024, 1, 1),
            ...     train_end=datetime(2024, 2, 1),
            ...     test_start=datetime(2024, 2, 1),
            ...     test_end=datetime(2024, 3, 1),
            ...     best_params={"fast_period": 5},
            ... )
            >>> w.to_dict()["best_params"]
            {'fast_period': 5}

        """
        return {
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "best_params": self.best_params,
            "train_result": self.train_result,
            "test_result": self.test_result,
        }


@dataclass
class WalkForwardResult:
    """Result of walk-forward optimization.

    Aggregates every :class:`WalkForwardWindow` produced by a single
    :meth:`WalkForwardOptimizer.run` call along with a combined out-of-sample
    backtest that chains each window's test-period equity curve together.

    Attributes:
        windows: List of per-window results in chronological order.
        combined_test_result: Backtest result spanning the full out-of-sample
            period, built by chaining each window's test equity curve. ``None``
            when no window produced a valid test result.
        anchored: Whether anchored (expanding) walk-forward was used. When
            ``False``, rolling (sliding) walk-forward was used.

    Examples:
        >>> from datetime import datetime
        >>> from quant_trading.optimization.walk_forward import WalkForwardResult, WalkForwardWindow
        >>> w = WalkForwardWindow(
        ...     train_start=datetime(2024, 1, 1),
        ...     train_end=datetime(2024, 2, 1),
        ...     test_start=datetime(2024, 2, 1),
        ...     test_end=datetime(2024, 3, 1),
        ... )
        >>> r = WalkForwardResult(windows=[w], combined_test_result=None, anchored=True)
        >>> r.anchored
        True
        >>> r.summary()["n_windows"]
        1

    """

    windows: list[WalkForwardWindow]
    combined_test_result: BacktestResult | None = None
    anchored: bool = True

    def to_dataframe(self) -> pd.DataFrame:
        """Convert window results to a DataFrame.

        Returns:
            A DataFrame with one row per window. Columns include ``window``,
            the train/test date boundaries, training and test performance
            metrics (return, Sharpe, max drawdown), and one ``param_<name>``
            column per entry in the window's ``best_params``.

        Examples:
            >>> from datetime import datetime
            >>> from quant_trading.optimization.walk_forward import WalkForwardResult, WalkForwardWindow
            >>> w = WalkForwardWindow(
            ...     train_start=datetime(2024, 1, 1),
            ...     train_end=datetime(2024, 2, 1),
            ...     test_start=datetime(2024, 2, 1),
            ...     test_end=datetime(2024, 3, 1),
            ...     best_params={"fast_period": 5},
            ... )
            >>> df = WalkForwardResult(windows=[w], anchored=True).to_dataframe()
            >>> "param_fast_period" in df.columns
            True
            >>> len(df)
            1

        """
        rows: list[dict[str, Any]] = []
        for i, w in enumerate(self.windows):
            row: dict[str, Any] = {
                "window": i,
                "train_start": w.train_start,
                "train_end": w.train_end,
                "test_start": w.test_start,
                "test_end": w.test_end,
                "train_return_pct": w.train_result.total_return_pct if w.train_result else None,
                "train_sharpe": w.train_result.metrics.sharpe_ratio if w.train_result else None,
                "test_return_pct": w.test_result.total_return_pct if w.test_result else None,
                "test_sharpe": w.test_result.metrics.sharpe_ratio if w.test_result else None,
                "test_max_dd": w.test_result.metrics.max_drawdown_pct if w.test_result else None,
            }
            if w.best_params:
                row.update({f"param_{k}": v for k, v in w.best_params.items()})
            rows.append(row)
        return pd.DataFrame(rows)

    def summary(self) -> dict[str, Any]:
        """Get summary statistics.

        Returns:
            Dictionary with ``n_windows``, average test return, average test
            Sharpe, average test max drawdown, win-rate of positive-test-return
            windows, and the combined test result's return and Sharpe.

        Examples:
            >>> from datetime import datetime
            >>> from quant_trading.optimization.walk_forward import WalkForwardResult, WalkForwardWindow
            >>> w = WalkForwardWindow(
            ...     train_start=datetime(2024, 1, 1),
            ...     train_end=datetime(2024, 2, 1),
            ...     test_start=datetime(2024, 2, 1),
            ...     test_end=datetime(2024, 3, 1),
            ... )
            >>> s = WalkForwardResult(windows=[w], anchored=True).summary()
            >>> s["n_windows"]
            1
            >>> s["avg_test_return_pct"]
            0

        """
        test_returns = [w.test_result.total_return_pct for w in self.windows if w.test_result]
        test_sharpes = [w.test_result.metrics.sharpe_ratio for w in self.windows if w.test_result]
        test_dds = [w.test_result.metrics.max_drawdown_pct for w in self.windows if w.test_result]

        return {
            "n_windows": len(self.windows),
            "avg_test_return_pct": sum(test_returns) / len(test_returns) if test_returns else 0,
            "avg_test_sharpe": sum(test_sharpes) / len(test_sharpes) if test_sharpes else 0,
            "avg_test_max_dd_pct": sum(test_dds) / len(test_dds) if test_dds else 0,
            "win_rate_windows": (
                sum(1 for r in test_returns if r > 0) / len(test_returns) if test_returns else 0
            ),
            "combined_test_return_pct": (
                self.combined_test_result.total_return_pct if self.combined_test_result else None
            ),
            "combined_test_sharpe": (
                self.combined_test_result.metrics.sharpe_ratio
                if self.combined_test_result
                else None
            ),
        }


class WalkForwardOptimizer:
    """Walk-forward optimizer for strategy parameters.

    Walk-forward analysis splits the available data into a sequence of
    in-sample (training) and out-of-sample (testing) windows. For each window,
    the optimizer searches for the parameters that maximize the chosen
    objective on the training data, then validates those parameters on the
    adjacent out-of-sample window. Aggregating out-of-sample performance
    across windows gives a more realistic estimate of strategy performance
    than optimizing once over the entire period, because it reduces
    overfitting to a single historical segment.

    Two walk-forward modes are supported:

    * **Anchored** (``anchored=True``): the training window starts at a fixed
      point and expands forward as each window progresses. This mimics the
      real-world scenario where all information available up to the current
      date is used for optimization.
    * **Rolling** (``anchored=False``): the training window keeps a fixed
      length and slides forward with each window.

    Attributes:
        strategy_cls: Strategy class being optimized.
        param_grid: Parameter grid defining the search space.
        objective: Objective function maximized during optimization.
        symbols: Symbols traded during each backtest.
        start: Start date of the full walk-forward period.
        end: End date of the full walk-forward period.
        initial_capital: Initial capital for each backtest.
        commission: Commission rate applied to each trade.
        slippage: Slippage rate applied to each trade.
        interval: Data interval used for backtests.
        data_manager: DataManager instance supplying price data.
        config: Optional configuration object passed to strategies.
        n_windows: Number of walk-forward windows to generate.
        train_size: Fraction of each window allocated to training (0-1).
        step_size: Step size between windows as a fraction of a window's span.
            It defaults to 1.0, so consecutive windows advance by one window
            and the windows tile the requested period exactly.
        anchored: Whether anchored (expanding) walk-forward is used.
        optimizer_type: Backend optimizer identifier ("grid", "random", or
            "bayesian").
        optimizer_kwargs: Additional keyword arguments forwarded to the
            backend optimizer.
        risk_free_rate: Annual risk-free rate used for risk-adjusted metrics
            in the combined test result (default 0.02).
        verbose: Whether to print progress information.

    Examples:
        >>> from datetime import datetime
        >>> from quant_trading.optimization.walk_forward import WalkForwardOptimizer
        >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace, maximize_sharpe
        >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5], param_type=int))
        >>> optimizer = WalkForwardOptimizer(
        ...     strategy_cls=None,
        ...     param_grid=grid,
        ...     objective=maximize_sharpe,
        ...     start=None,
        ...     end=None,
        ... )
        >>> optimizer.optimizer_type
        'grid'
        >>> optimizer.anchored
        True

    """

    def __init__(
        self,
        strategy_cls: type[Strategy],
        param_grid: ParameterGrid,
        objective: ObjectiveFunction = maximize_sharpe,
        symbols: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        interval: str = "1d",
        data_manager: Any | None = None,
        config: Any | None = None,
        n_windows: int = 5,
        train_size: float = 0.7,
        step_size: float | None = None,
        anchored: bool = True,
        optimizer: str = "grid",
        optimizer_kwargs: dict[str, Any] | None = None,
        periods_per_year: int = 252,
        risk_free_rate: float = 0.02,
        verbose: bool = False,
    ):
        """Initialize walk-forward optimizer.

        Args:
            strategy_cls: Strategy class to optimize.
            param_grid: Parameter grid for optimization.
            objective: Objective function for optimization.
            symbols: List of symbols to trade.
            start: Start date for full period.
            end: End date for full period.
            initial_capital: Initial capital for backtests.
            commission: Commission rate.
            slippage: Slippage rate.
            interval: Data interval.
            data_manager: DataManager instance.
            config: Config instance.
            n_windows: Number of walk-forward windows.
            train_size: Fraction of each window for training (0-1).
            step_size: Step size between windows as a fraction of a window's
                span (default: 1.0, so the windows tile the requested period).
            anchored: If True, training window expands (anchored walk-forward).
                      If False, training window slides (rolling walk-forward).
            optimizer: Optimizer type ("grid" or "random").
            optimizer_kwargs: Additional kwargs for optimizer.
            periods_per_year: Trading periods per year used to annualize the
                return, volatility, Sharpe, Sortino and Calmar metrics
                (default 252 for daily data).
            risk_free_rate: Annual risk-free rate used for risk-adjusted
                metrics in the combined test result (default 0.02).
            verbose: Print progress.

        """
        self.strategy_cls = strategy_cls
        self.param_grid = param_grid
        self.objective = objective
        self.symbols = symbols or ["AAPL"]
        self.start = start
        self.end = end
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.interval = interval
        self.data_manager = data_manager
        self.config = config
        self.n_windows = n_windows
        self.train_size = train_size
        self.anchored = anchored
        self.optimizer_type = optimizer
        self.optimizer_kwargs = optimizer_kwargs or {}
        self.periods_per_year = periods_per_year
        self.risk_free_rate = risk_free_rate
        self.verbose = verbose

        if step_size is None:
            # One step per window: the windows tile the requested period, so
            # every sub-interval is used exactly once.
            self.step_size = 1.0
        else:
            self.step_size = step_size

    def _create_optimizer(self) -> BaseOptimizer:
        """Create the backend optimizer instance for the current window.

        Returns:
            A fresh optimizer configured with this walk-forward optimizer's
            strategy, parameter grid, objective, and backtest settings.

        Raises:
            ValueError: If ``optimizer_type`` is not one of "grid", "random",
                or "bayesian".

        Examples:
            >>> from quant_trading.optimization.walk_forward import WalkForwardOptimizer
            >>> from quant_trading.optimization.base import ParameterGrid, ParameterSpace, maximize_sharpe
            >>> grid = ParameterGrid().add(ParameterSpace("fast_period", values=[5], param_type=int))
            >>> optimizer = WalkForwardOptimizer(
            ...     strategy_cls=None,  # doctest: +SKIP
            ...     param_grid=grid,
            ...     objective=maximize_sharpe,
            ...     start=None,
            ...     end=None,
            ... )
            >>> optimizer._create_optimizer()  # doctest: +SKIP
            GridSearch(...)

        """
        if self.optimizer_type == "grid":
            return GridSearch(
                strategy_cls=self.strategy_cls,
                param_grid=self.param_grid,
                objective=self.objective,
                symbols=self.symbols,
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
                interval=self.interval,
                data_manager=self.data_manager,
                config=self.config,
                periods_per_year=self.periods_per_year,
                verbose=self.verbose,
                **self.optimizer_kwargs,
            )
        elif self.optimizer_type == "random":
            from .random_search import RandomSearch

            return RandomSearch(
                strategy_cls=self.strategy_cls,
                param_grid=self.param_grid,
                objective=self.objective,
                symbols=self.symbols,
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
                interval=self.interval,
                data_manager=self.data_manager,
                config=self.config,
                periods_per_year=self.periods_per_year,
                verbose=self.verbose,
                **self.optimizer_kwargs,
            )
        elif self.optimizer_type == "bayesian":
            from .bayesian import BayesianOptimizer

            return BayesianOptimizer(
                strategy_cls=self.strategy_cls,
                param_grid=self.param_grid,
                objective=self.objective,
                symbols=self.symbols,
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
                interval=self.interval,
                data_manager=self.data_manager,
                config=self.config,
                periods_per_year=self.periods_per_year,
                verbose=self.verbose,
                **self.optimizer_kwargs,
            )
        else:
            raise ValueError(f"Unknown optimizer type: {self.optimizer_type}")

    def _generate_windows(self) -> list[WalkForwardWindow]:
        """Generate the walk-forward windows for the configured period.

        The full span from ``start`` to ``end`` is divided into ``n_windows``
        sub-intervals of ``window_days`` days each. Every sub-interval is split
        into a training span and an out-of-sample (test) span, and the test
        span is the part that follows the training span inside the
        sub-interval.

        For anchored walk-forward, the training start is fixed at ``start`` and
        the training end expands forward by one step per window; for rolling
        walk-forward, the training span keeps its length and slides forward by
        one step per window. One step is ``step_size`` sub-intervals, and it
        defaults to one sub-interval, so the sub-intervals tile the requested
        period and no part of it is left untested.

        The test span of a window stops where the next window's training span
        begins, so the out-of-sample periods of two consecutive windows never
        overlap. A period is therefore evaluated out-of-sample at most once,
        and it is counted at most once in the combined out-of-sample result.

        Returns:
            List of :class:`WalkForwardWindow` objects, one per valid window.
            Windows whose test span degenerates to zero length are skipped.

        Raises:
            ValueError: If ``start`` or ``end`` is not set.

        Examples:
            >>> from datetime import datetime
            >>> from quant_trading.optimization.walk_forward import WalkForwardOptimizer
            >>> from quant_trading.optimization.base import ParameterGrid, maximize_sharpe
            >>> optimizer = WalkForwardOptimizer(
            ...     strategy_cls=None,  # doctest: +SKIP
            ...     param_grid=ParameterGrid(),
            ...     objective=maximize_sharpe,
            ...     start=datetime(2024, 1, 1),
            ...     end=datetime(2024, 1, 11),
            ...     n_windows=2,
            ...     train_size=0.5,
            ...     anchored=True,
            ... )
            >>> [(w.train_start, w.train_end, w.test_start, w.test_end) for w in optimizer._generate_windows()]  # doctest: +SKIP
            [(datetime.datetime(2024, 1, 1, 0, 0), datetime.datetime(2024, 1, 3, 0, 0), datetime.datetime(2024, 1, 3, 0, 0), datetime.datetime(2024, 1, 6, 0, 0)), (datetime.datetime(2024, 1, 1, 0, 0), datetime.datetime(2024, 1, 6, 0, 0), datetime.datetime(2024, 1, 6, 0, 0), datetime.datetime(2024, 1, 11, 0, 0))]

        """
        if self.start is None or self.end is None:
            raise ValueError("start and end dates must be provided")

        total_days = (self.end - self.start).days
        window_days = total_days // self.n_windows
        train_days = int(window_days * self.train_size)
        test_days = window_days - train_days
        step_days = int(window_days * self.step_size)

        # The training span of every window, in chronological order.
        spans: list[tuple[datetime, datetime]] = []
        for i in range(self.n_windows):
            if self.anchored:
                # Anchored: the training start is fixed and the training end
                # expands forward by one step per window.
                train_start = self.start
                train_end = self.start + timedelta(days=train_days + i * step_days)
            else:
                # Rolling: the training span slides forward by one step and
                # keeps its length.
                train_start = self.start + timedelta(days=i * step_days)
                train_end = train_start + timedelta(days=train_days)
            spans.append((train_start, train_end))

        windows: list[WalkForwardWindow] = []
        for i, (train_start, train_end) in enumerate(spans):
            test_start = train_end
            # The test period follows the training period inside the window,
            # but it never reaches into the next window's training period, so
            # two consecutive out-of-sample periods never overlap.
            next_train_end = spans[i + 1][1] if i + 1 < len(spans) else self.end
            test_end = min(train_end + timedelta(days=test_days), next_train_end, self.end)

            if test_start >= test_end:
                break

            windows.append(
                WalkForwardWindow(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )

        return windows

    def run(self) -> WalkForwardResult:
        """Run walk-forward optimization.

        For each generated window, the backend optimizer searches for the best
        parameters on the training data, then those parameters are validated on
        the out-of-sample test data. Test-period equity curves are chained
        together into a single combined out-of-sample result.

        Returns:
            WalkForwardResult with all window results and the combined test
            result. Windows whose optimization or validation fails are kept
            with their ``best_params``/``test_result`` left as ``None``.

        Raises:
            ValueError: If the windows cannot be generated (e.g. missing
                start/end dates) or an unknown optimizer type was configured.

        Examples:
            >>> from quant_trading.optimization.walk_forward import WalkForwardOptimizer
            >>> optimizer = WalkForwardOptimizer(
            ...     strategy_cls=None,  # doctest: +SKIP
            ...     param_grid=ParameterGrid(),
            ...     objective=maximize_sharpe,
            ...     start=None,
            ...     end=None,
            ... )
            >>> optimizer.run()  # doctest: +SKIP
            WalkForwardResult(windows=[...], anchored=True)

        """
        windows = self._generate_windows()

        if self.verbose:
            print(f"WalkForwardOptimizer: {len(windows)} windows, anchored={self.anchored}")

        for i, window in enumerate(windows):
            if self.verbose:
                print(f"\nWindow {i+1}/{len(windows)}:")
                print(f"  Train: {window.train_start.date()} to {window.train_end.date()}")
                print(f"  Test:  {window.test_start.date()} to {window.test_end.date()}")

            # Optimize on training data
            optimizer = self._create_optimizer()
            optimizer.start = window.train_start
            optimizer.end = window.train_end

            opt_result = optimizer.run()
            window.best_params = opt_result.best_params
            window.train_result = opt_result.best_result

            if self.verbose and window.best_params:
                print(f"  Best params: {window.best_params}")
                print(f"  Train score: {opt_result.best_score:.4f}")

            # Test on out-of-sample data
            if window.best_params:
                strategy = self.strategy_cls(**window.best_params)
                test_result = run_backtest(
                    strategy=strategy,
                    symbols=self.symbols,
                    start=window.test_start,
                    end=window.test_end,
                    initial_capital=self.initial_capital,
                    commission=self.commission,
                    slippage=self.slippage,
                    interval=self.interval,
                    data_manager=self.data_manager,
                    config=self.config,
                    periods_per_year=self.periods_per_year,
                )
                window.test_result = test_result

                if self.verbose:
                    print(f"  Test return: {test_result.total_return_pct:.2f}%")
                    print(f"  Test Sharpe: {test_result.metrics.sharpe_ratio:.4f}")

        # Combine all test period results into a single equity curve
        combined_test_result = self._combine_test_results(windows)

        return WalkForwardResult(
            windows=windows,
            combined_test_result=combined_test_result,
            anchored=self.anchored,
        )

    def _combine_test_results(self, windows: list[WalkForwardWindow]) -> BacktestResult | None:
        """Combine test period results from all windows into a single result.

        Each window's backtest starts fresh at ``initial_capital``, so the
        out-of-sample equity segments are chained together: the final equity of
        one window seeds the next. The first bar of each window's curve is
        dropped because it duplicates the previous window's last bar (or, for
        the first window, is the initial capital itself). The resulting
        combined equity curve is re-evaluated into a fresh :class:`BacktestResult`.

        The combined curve is a time series, so its index is strictly
        increasing: a point that is not later than the last emitted one is
        skipped, which keeps the curve valid even when the caller supplies
        windows whose out-of-sample periods overlap.

        The combined trade log is the concatenation of the windows' trade logs.
        Its ``pnl`` column is expressed in the combined account's dollars (each
        window's PnL is scaled by the same factor as its equity curve), so the
        realized PnL of the combined result agrees with the combined equity
        curve. The remaining columns describe the trade as it was executed in
        its own window.

        Args:
            windows: Walk-forward windows, some of which may have a ``None``
                ``test_result`` (skipped during combination).

        Returns:
            A single :class:`BacktestResult` spanning the combined out-of-sample
            period, or ``None`` when no window produced a usable test result.

        Examples:
            >>> from datetime import datetime
            >>> from quant_trading.optimization.walk_forward import WalkForwardOptimizer
            >>> from quant_trading.optimization.base import ParameterGrid, maximize_sharpe
            >>> optimizer = WalkForwardOptimizer(
            ...     strategy_cls=None,  # doctest: +SKIP
            ...     param_grid=ParameterGrid(),
            ...     objective=maximize_sharpe,
            ...     start=datetime(2024, 1, 1),
            ...     end=datetime(2024, 1, 11),
            ... )
            >>> optimizer._combine_test_results([])  # doctest: +SKIP
            None

        """
        import pandas as pd

        valid_windows = [w for w in windows if w.test_result is not None]
        if not valid_windows:
            return None

        # Combine equity curves. Each window's backtest starts fresh at
        # initial_capital, so the out-of-sample segments must be chained together:
        # the final equity of one window seeds the next. The first value of each
        # window's curve is dropped because it duplicates the previous window's
        # last bar (or, for the first window, is the initial capital itself).
        all_equity: list[float] = []
        all_trades: list[pd.DataFrame] = []
        all_dates: list[datetime] = []
        combined_costs = 0.0

        initial_capital = self.initial_capital
        cumulative_final = initial_capital
        last_timestamp: datetime | None = None
        for w in valid_windows:
            assert w.test_result is not None
            eq = w.test_result.equity_curve
            if len(eq) < 2:
                continue
            # Scale this window's curve so its start aligns with the previous
            # windows' cumulative final equity, then drop the duplicated first bar.
            scale = (cumulative_final / initial_capital) if initial_capital else 1.0
            scaled = eq.to_numpy(dtype=float) * scale
            for timestamp, value in zip(eq.index[1:], scaled[1:]):
                if last_timestamp is not None and timestamp <= last_timestamp:
                    # The point is not later than the last emitted one, so it
                    # belongs to a period that is already in the curve.
                    continue
                all_dates.append(timestamp)
                all_equity.append(float(value))
                last_timestamp = timestamp
            if all_equity:
                # The next window starts where the combined curve ends.
                cumulative_final = all_equity[-1]
            trades = w.test_result.trades
            if not trades.empty and "pnl" in trades.columns:
                # The window's PnL is booked in the window's own capital base,
                # so it is scaled into the combined account's dollars with the
                # same factor as the window's equity curve.
                trades = trades.copy()
                trades["pnl"] = trades["pnl"].astype(float) * scale
            all_trades.append(trades)
            # Costs are paid per window, so the combined total is their sum.
            combined_costs += w.test_result.total_costs

        if not all_equity:
            return None

        assert self.start is not None, "start date must be set"
        assert self.end is not None, "end date must be set"

        # Build combined equity curve. The first point is the initial capital;
        # each subsequent point is the chained value from the previous window.
        combined_equity = pd.Series([initial_capital] + all_equity, index=[self.start] + all_dates)
        combined_trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()

        from quant_trading.backtest.metrics import calculate_backtest_metrics

        metrics = calculate_backtest_metrics(
            combined_equity,
            combined_trades,
            risk_free_rate=self.risk_free_rate,
            periods_per_year=self.periods_per_year,
        )

        return BacktestResult(
            equity_curve=combined_equity,
            trades=combined_trades,
            positions={},
            metrics=metrics,
            start_date=self.start,
            end_date=self.end,
            initial_capital=initial_capital,
            final_value=combined_equity.iloc[-1],
            total_return=combined_equity.iloc[-1] - initial_capital,
            total_return_pct=(combined_equity.iloc[-1] / initial_capital - 1) * 100,
            total_costs=combined_costs,
        )
