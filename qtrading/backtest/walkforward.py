from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import product
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from qtrading.strategy import Strategy, StrategyParams

if TYPE_CHECKING:
    from qtrading.backtest import BacktestResult


@dataclass
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_data: dict[str, pd.DataFrame]
    test_data: dict[str, pd.DataFrame]


@dataclass
class WalkForwardResult:
    window_idx: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: dict[str, Any]
    train_result: "BacktestResult"
    test_result: "BacktestResult"
    param_combinations_tested: int


@dataclass
class WalkForwardSummary:
    total_windows: int
    results: list["WalkForwardResult"]
    aggregate_train_return: float
    aggregate_test_return: float
    aggregate_train_sharpe: float
    aggregate_test_sharpe: float
    avg_win_rate_train: float
    avg_win_rate_test: float
    parameter_stability: dict[str, float]


class WalkForwardAnalyzer:
    def __init__(
        self,
        strategy_class: type[Strategy],
        param_grid: dict[str, list[Any]],
        initial_capital: Decimal | None = None,
        commission_rate: Decimal | None = None,
        slippage_rate: Decimal | None = None,
        max_positions: int | None = None,
    ):
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.engine_kwargs: dict[str, Decimal | int] = {}
        if initial_capital is not None:
            self.engine_kwargs["initial_capital"] = initial_capital
        if commission_rate is not None:
            self.engine_kwargs["commission_rate"] = commission_rate
        if slippage_rate is not None:
            self.engine_kwargs["slippage_rate"] = slippage_rate
        if max_positions is not None:
            self.engine_kwargs["max_positions"] = max_positions

    def generate_param_combinations(self) -> list[dict[str, Any]]:
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        combinations = []
        for combo in product(*values):
            combinations.append(dict(zip(keys, combo, strict=False)))
        return combinations

    def create_windows(
        self,
        market_data: dict[str, pd.DataFrame],
        train_window_size: int,
        test_window_size: int,
        step_size: int | None = None,
        min_train_size: int | None = None,
    ) -> list[WalkForwardWindow]:
        if step_size is None:
            step_size = test_window_size

        all_timestamps = set()
        for df in market_data.values():
            if not df.empty:
                all_timestamps.update(df.index)
        timestamps = sorted(all_timestamps)

        if min_train_size is None:
            min_train_size = train_window_size

        windows = []
        window_idx = 0

        while True:
            train_end_idx = min_train_size + window_idx * step_size
            test_end_idx = train_end_idx + test_window_size

            if test_end_idx > len(timestamps):
                break

            train_start_idx = max(0, train_end_idx - train_window_size)

            train_start = timestamps[train_start_idx]
            train_end = timestamps[train_end_idx - 1]
            test_start = timestamps[train_end_idx]
            test_end = timestamps[min(test_end_idx - 1, len(timestamps) - 1)]

            train_data = {}
            test_data = {}
            for symbol, df in market_data.items():
                train_mask = (df.index >= train_start) & (df.index <= train_end)
                test_mask = (df.index >= test_start) & (df.index <= test_end)
                train_data[symbol] = df[train_mask].copy()
                test_data[symbol] = df[test_mask].copy()

            if all(len(df) > 0 for df in train_data.values()) and all(
                len(df) > 0 for df in test_data.values()
            ):
                windows.append(WalkForwardWindow(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_data=train_data,
                    test_data=test_data,
                ))

            window_idx += 1

        return windows

    def run_walkforward(
        self,
        market_data: dict[str, pd.DataFrame],
        strategy_params: StrategyParams,
        train_window_size: int,
        test_window_size: int,
        step_size: int | None = None,
        min_train_size: int | None = None,
        metric: str = "sharpe_ratio",
    ) -> "WalkForwardSummary":
        windows = self.create_windows(
            market_data, train_window_size, test_window_size, step_size, min_train_size
        )

        param_combinations = self.generate_param_combinations()
        results = []

        for window_idx, window in enumerate(windows):
            best_params = None
            best_metric = -np.inf
            best_train_result = None

            for params in param_combinations:
                test_params = StrategyParams(
                    name=strategy_params.name,
                    symbols=strategy_params.symbols,
                    timeframes=strategy_params.timeframes,
                    parameters={**strategy_params.parameters, **params},
                )

                strategy = self.strategy_class(test_params)
                from qtrading.backtest import BacktestEngine
                engine = BacktestEngine(**self.engine_kwargs)
                train_result = engine.run(strategy, window.train_data)

                metric_value = getattr(train_result, metric, 0.0)
                if metric_value > best_metric:
                    best_metric = metric_value
                    best_params = params.copy()
                    best_train_result = train_result

            if best_params is None:
                continue

            assert best_train_result is not None

            test_params = StrategyParams(
                name=strategy_params.name,
                symbols=strategy_params.symbols,
                timeframes=strategy_params.timeframes,
                parameters={**strategy_params.parameters, **best_params},
            )

            strategy = self.strategy_class(test_params)
            from qtrading.backtest import BacktestEngine
            engine = BacktestEngine(**self.engine_kwargs)
            test_result = engine.run(strategy, window.test_data)

            results.append(WalkForwardResult(
                window_idx=window_idx,
                train_start=window.train_start,
                train_end=window.train_end,
                test_start=window.test_start,
                test_end=window.test_end,
                best_params=best_params,
                train_result=best_train_result,
                test_result=test_result,
                param_combinations_tested=len(param_combinations),
            ))

        return self._calculate_summary(results)

    def _calculate_summary(self, results: list["WalkForwardResult"]) -> "WalkForwardSummary":
        if not results:
            return WalkForwardSummary(
                total_windows=0,
                results=[],
                aggregate_train_return=0.0,
                aggregate_test_return=0.0,
                aggregate_train_sharpe=0.0,
                aggregate_test_sharpe=0.0,
                avg_win_rate_train=0.0,
                avg_win_rate_test=0.0,
                parameter_stability={},
            )

        train_returns = [r.train_result.total_return_pct for r in results]
        test_returns = [r.test_result.total_return_pct for r in results]
        train_sharpes = [r.train_result.sharpe_ratio for r in results]
        test_sharpes = [r.test_result.sharpe_ratio for r in results]
        train_win_rates = [r.train_result.win_rate for r in results]
        test_win_rates = [r.test_result.win_rate for r in results]

        all_params: dict[str, list[Any]] = {}
        for r in results:
            for k, v in r.best_params.items():
                if k not in all_params:
                    all_params[k] = []
                all_params[k].append(v)

        param_stability = {}
        for k, values in all_params.items():
            if isinstance(values[0], (int, float)):
                param_stability[k] = float(np.std(values) / (np.mean(values) + 1e-10))
            else:
                unique_count = len({str(v) for v in values})
                param_stability[k] = float(unique_count / len(values))

        return WalkForwardSummary(
            total_windows=len(results),
            results=results,
            aggregate_train_return=float(np.mean(train_returns)),
            aggregate_test_return=float(np.mean(test_returns)),
            aggregate_train_sharpe=float(np.mean(train_sharpes)),
            aggregate_test_sharpe=float(np.mean(test_sharpes)),
            avg_win_rate_train=float(np.mean(train_win_rates)),
            avg_win_rate_test=float(np.mean(test_win_rates)),
            parameter_stability=param_stability,
        )

    def run_anchored_walkforward(
        self,
        market_data: dict[str, pd.DataFrame],
        strategy_params: StrategyParams,
        initial_train_size: int,
        test_window_size: int,
        step_size: int | None = None,
        metric: str = "sharpe_ratio",
    ) -> "WalkForwardSummary":
        if step_size is None:
            step_size = test_window_size

        all_timestamps = set()
        for df in market_data.values():
            if not df.empty:
                all_timestamps.update(df.index)
        timestamps = sorted(all_timestamps)

        param_combinations = self.generate_param_combinations()
        results = []

        train_end_idx = initial_train_size
        window_idx = 0

        while True:
            test_end_idx = train_end_idx + test_window_size

            if test_end_idx > len(timestamps):
                break

            train_start = timestamps[0]
            train_end = timestamps[train_end_idx - 1]
            test_start = timestamps[train_end_idx]
            test_end = timestamps[min(test_end_idx - 1, len(timestamps) - 1)]

            train_data = {}
            test_data = {}
            for symbol, df in market_data.items():
                train_mask = (df.index >= train_start) & (df.index <= train_end)
                test_mask = (df.index >= test_start) & (df.index <= test_end)
                train_data[symbol] = df[train_mask].copy()
                test_data[symbol] = df[test_mask].copy()

            if all(len(df) > 0 for df in train_data.values()) and all(
                len(df) > 0 for df in test_data.values()
            ):
                best_params = None
                best_metric = -np.inf
                best_train_result = None

                for params in param_combinations:
                    test_params = StrategyParams(
                        name=strategy_params.name,
                        symbols=strategy_params.symbols,
                        timeframes=strategy_params.timeframes,
                        parameters={**strategy_params.parameters, **params},
                    )

                    strategy = self.strategy_class(test_params)
                    from qtrading.backtest import BacktestEngine
                    engine = BacktestEngine(**self.engine_kwargs)
                    train_result = engine.run(strategy, train_data)

                    metric_value = getattr(train_result, metric, 0.0)
                    if metric_value > best_metric:
                        best_metric = metric_value
                        best_params = params.copy()
                        best_train_result = train_result

                if best_params is not None:
                    assert best_train_result is not None

                    test_params = StrategyParams(
                        name=strategy_params.name,
                        symbols=strategy_params.symbols,
                        timeframes=strategy_params.timeframes,
                        parameters={**strategy_params.parameters, **best_params},
                    )

                    strategy = self.strategy_class(test_params)
                    from qtrading.backtest import BacktestEngine
                    engine = BacktestEngine(**self.engine_kwargs)
                    test_result = engine.run(strategy, test_data)

                    results.append(WalkForwardResult(
                        window_idx=window_idx,
                        train_start=train_start,
                        train_end=train_end,
                        test_start=test_start,
                        test_end=test_end,
                        best_params=best_params,
                        train_result=best_train_result,
                        test_result=test_result,
                        param_combinations_tested=len(param_combinations),
                    ))

            train_end_idx += step_size
            window_idx += 1

        return self._calculate_summary(results)
