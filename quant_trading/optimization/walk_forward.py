"""Walk-forward optimization for strategy parameters.

Walk-forward analysis splits data into in-sample (training) and out-of-sample (testing)
periods, optimizing parameters on in-sample data and validating on out-of-sample data.
This reduces overfitting compared to simple backtest optimization.
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
    """A single walk-forward window with in-sample and out-of-sample periods."""

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: dict[str, Any] | None = None
    train_result: BacktestResult | None = None
    test_result: BacktestResult | None = None


@dataclass
class WalkForwardResult:
    """Result of walk-forward optimization."""

    windows: list[WalkForwardWindow]
    combined_test_result: BacktestResult | None = None
    anchored: bool = True

    def to_dataframe(self) -> pd.DataFrame:
        """Convert window results to DataFrame."""
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
        """Get summary statistics."""
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

    Splits data into multiple in-sample/out-of-sample windows,
    optimizes parameters on in-sample data, and tests on out-of-sample data.
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
            step_size: Step size between windows as fraction (default: 1 - train_size for non-anchored).
            anchored: If True, training window expands (anchored walk-forward).
                      If False, training window slides (rolling walk-forward).
            optimizer: Optimizer type ("grid" or "random").
            optimizer_kwargs: Additional kwargs for optimizer.
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
        self.verbose = verbose

        if step_size is None:
            self.step_size = 1.0 - train_size if not anchored else train_size / n_windows
        else:
            self.step_size = step_size

    def _create_optimizer(self) -> BaseOptimizer:
        """Create optimizer instance."""
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
                verbose=self.verbose,
                **self.optimizer_kwargs,
            )
        else:
            raise ValueError(f"Unknown optimizer type: {self.optimizer_type}")

    def _generate_windows(self) -> list[WalkForwardWindow]:
        """Generate walk-forward windows."""
        if self.start is None or self.end is None:
            raise ValueError("start and end dates must be provided")

        total_days = (self.end - self.start).days
        window_days = total_days // self.n_windows
        train_days = int(window_days * self.train_size)
        step_days = int(window_days * self.step_size)

        windows = []
        current_start = self.start

        for i in range(self.n_windows):
            if self.anchored:
                # Anchored: training start is fixed, training end expands
                train_start = self.start
                train_end = self.start + timedelta(days=train_days + i * step_days)
            else:
                # Rolling: both training start and end move forward
                train_start = current_start
                train_end = current_start + timedelta(days=train_days)

            test_start = train_end
            test_end = min(train_end + timedelta(days=window_days - train_days), self.end)

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

            if not self.anchored:
                current_start += timedelta(days=step_days)

        return windows

    def run(self) -> WalkForwardResult:
        """Run walk-forward optimization.

        Returns:
            WalkForwardResult with all window results and combined test result.
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
        """Combine test period results from all windows into a single result."""
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

        initial_capital = self.initial_capital
        cumulative_final = initial_capital
        for w in valid_windows:
            assert w.test_result is not None
            eq = w.test_result.equity_curve
            if len(eq) < 2:
                continue
            # Scale this window's curve so its start aligns with the previous
            # windows' cumulative final equity, then drop the duplicated first bar.
            scale = cumulative_final / initial_capital
            scaled = eq.to_numpy(dtype=float) * scale
            all_equity.extend(scaled[1:].tolist())
            all_trades.append(w.test_result.trades)
            all_dates.extend(eq.index[1:].tolist())
            cumulative_final = float(scaled[-1])

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
            risk_free_rate=0.02,
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
        )
