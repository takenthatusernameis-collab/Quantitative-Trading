"""Tests for the optimization module."""

import importlib.util
import itertools
import json
import os
from concurrent.futures import _base
from concurrent.futures.process import BrokenProcessPool, ProcessPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from quant_trading.data.providers import DataManager
from quant_trading.optimization import (
    GridSearch,
    OptimizationResult,
    ParameterGrid,
    ParameterSpace,
    RandomSearch,
    WalkForwardOptimizer,
    maximize_calmar,
    maximize_profit_factor,
    maximize_sharpe,
    maximize_sortino,
    maximize_total_return,
    maximize_win_rate,
    minimize_max_drawdown,
)

try:
    from quant_trading.optimization import BayesianOptimizer
except ImportError:
    BayesianOptimizer: Any = None  # type: ignore[no-redef]
try:
    from quant_trading.optimization.bayesian import BayesianOptimizerConfig
except ImportError:
    BayesianOptimizerConfig: Any = None  # type: ignore[no-redef]
from quant_trading.strategies.base import Signal, Strategy
from quant_trading.strategies.examples import MovingAverageCrossover, RSIStrategy


# Optional dependencies used by some tests. Tests that require them are
# skipped (not failed) when the dependency is unavailable so the suite is
# deterministic in any environment without network or extra packages.
def _module_available(name: str) -> bool:
    """Return True if a top-level module can be imported."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


_HAS_SKOPT = _module_available("skopt")
_HAS_YFINANCE = _module_available("yfinance")

skip_if_no_skopt = pytest.mark.skipif(
    not _HAS_SKOPT, reason="scikit-optimize (skopt) is not installed"
)
skip_if_no_yfinance = pytest.mark.skipif(not _HAS_YFINANCE, reason="yfinance is not installed")


class MockDataProvider:
    """Mock data provider for testing."""

    def __init__(self, data: dict):
        self._data = data
        self._name = "mock"

    @property
    def name(self) -> str:
        return self._name

    def fetch(
        self,
        symbols: list,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ):
        from quant_trading.data.providers import FetchResult, MarketData

        result = FetchResult()
        for symbol in symbols:
            if symbol in self._data:
                df = self._data[symbol]
                if start is not None:
                    df = df[df.index >= start]
                if end is not None:
                    df = df[df.index <= end]
                result.data[symbol] = MarketData(
                    symbol=symbol,
                    data=df,
                    source=self.name,
                    fetched_at=datetime(2026, 1, 15),
                )
            else:
                result.missing.append(symbol)
        return result

    def fetch_latest(self, symbols: list):
        return self.fetch(symbols)

    def fetch_many(self, requests: list[dict]):
        results = {}
        for req in requests:
            symbols = req.get("symbols", [])
            start = req.get("start")
            end = req.get("end")
            interval = req.get("interval", "1d")
            key = self._request_key(symbols, start, end, interval)
            results[key] = self.fetch(symbols, start, end, interval)
        return results

    @staticmethod
    def _request_key(
        symbols: list, start: datetime | None, end: datetime | None, interval: str
    ) -> str:
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{symbols_str}|{start_str}|{end_str}|{interval}"


def create_test_data(symbol: str, days: int = 100, end: datetime | None = None) -> pd.DataFrame:
    """Create deterministic test price data."""
    np.random.seed(42)
    dates = pd.date_range(end=end or datetime(2026, 1, 15), periods=days, freq="D")
    returns = np.random.normal(0.0005, 0.02, days)
    prices = 100 * np.exp(np.cumsum(returns))

    df: pd.DataFrame = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
            "high": prices * (1 + np.random.uniform(0, 0.01, days)),
            "low": prices * (1 - np.random.uniform(0, 0.01, days)),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df


def test_parameter_space_grid():
    """Test ParameterSpace grid generation."""
    space = ParameterSpace("test", min_val=1, max_val=5, step=1, param_type=int)
    values = space.generate_grid()
    assert values == [1, 2, 3, 4, 5]

    space_float = ParameterSpace("test", min_val=1.0, max_val=2.0, step=0.5)
    values = space_float.generate_grid()
    assert values == [1.0, 1.5, 2.0]

    space_values = ParameterSpace("test", values=[1, 2, 3, 5, 8])
    values = space_values.generate_grid()
    assert values == [1, 2, 3, 5, 8]


def test_parameter_space_random():
    """Test ParameterSpace random sampling."""
    space = ParameterSpace("test", min_val=0, max_val=10, param_type=int)
    samples = space.sample_random(5)
    assert len(samples) == 5
    assert all(0 <= s <= 10 for s in samples)
    assert all(isinstance(s, int) for s in samples)

    space_values = ParameterSpace("test", values=[1, 2, 3])
    samples = space_values.sample_random(10)
    assert len(samples) == 10
    assert all(s in [1, 2, 3] for s in samples)


def test_parameter_grid():
    """Test ParameterGrid combination generation."""
    grid = ParameterGrid()
    grid.add(ParameterSpace("a", values=[1, 2]))
    grid.add(ParameterSpace("b", values=[10, 20]))

    combos = grid.generate_combinations()
    assert len(combos) == 4
    assert {"a": 1, "b": 10} in combos
    assert {"a": 1, "b": 20} in combos
    assert {"a": 2, "b": 10} in combos
    assert {"a": 2, "b": 20} in combos


def test_parameter_grid_validator():
    """Test ParameterGrid with cross-parameter validator."""
    grid = ParameterGrid()
    grid.add(ParameterSpace("fast_period", values=[5, 10, 15], param_type=int))
    grid.add(ParameterSpace("slow_period", values=[10, 20, 30], param_type=int))
    grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])

    combos = grid.generate_combinations()
    # Should filter out invalid combinations where fast_period >= slow_period
    assert all(c["fast_period"] < c["slow_period"] for c in combos)
    # Total combinations without filter: 3 * 3 = 9
    # Valid: (5,10), (5,20), (5,30), (10,20), (10,30), (15,20), (15,30) = 7
    assert len(combos) == 7


def test_parameter_grid_random():
    """Test ParameterGrid random sampling."""
    grid = ParameterGrid()
    grid.add(ParameterSpace("a", min_val=1, max_val=10, param_type=int))
    grid.add(ParameterSpace("b", values=[10, 20, 30]))

    combos = grid.sample_random(5)
    assert len(combos) == 5
    for combo in combos:
        assert "a" in combo
        assert "b" in combo
        assert 1 <= combo["a"] <= 10
        assert combo["b"] in [10, 20, 30]


def test_parameter_space_to_dict():
    """Test ParameterSpace.to_dict serialization."""
    space = ParameterSpace("test_param", values=[1, 2, 3], min_val=0.0, max_val=10.0, step=1.0, distribution="log", param_type=int)
    data = space.to_dict()

    assert data["name"] == "test_param"
    assert data["values"] == [1, 2, 3]
    assert data["min_val"] == 0.0
    assert data["max_val"] == 10.0
    assert data["step"] == 1.0
    assert data["distribution"] == "log"
    assert data["param_type"] == "int"


def test_parameter_space_to_dict_none_values():
    """Test ParameterSpace.to_dict with None values."""
    space = ParameterSpace("test_param", min_val=0.0, max_val=10.0, step=1.0, param_type=float)
    data = space.to_dict()

    assert data["name"] == "test_param"
    assert data["values"] is None
    assert data["min_val"] == 0.0
    assert data["max_val"] == 10.0
    assert data["step"] == 1.0
    assert data["distribution"] is None
    assert data["param_type"] == "float"


def test_parameter_space_from_dict():
    """Test ParameterSpace.from_dict deserialization."""
    data = {
        "name": "test_param",
        "values": [1, 2, 3],
        "min_val": 0.0,
        "max_val": 10.0,
        "step": 1.0,
        "distribution": "log",
        "param_type": "int",
    }
    space = ParameterSpace.from_dict(data)

    assert space.name == "test_param"
    assert space.values == [1, 2, 3]
    assert space.min_val == 0.0
    assert space.max_val == 10.0
    assert space.step == 1.0
    assert space.distribution == "log"
    assert space.param_type == int


def test_parameter_space_from_dict_defaults():
    """Test ParameterSpace.from_dict with missing optional fields."""
    data = {"name": "test_param", "values": []}
    space = ParameterSpace.from_dict(data)

    assert space.name == "test_param"
    assert space.values == []
    assert space.min_val is None
    assert space.max_val is None
    assert space.step is None
    assert space.distribution is None
    assert space.param_type == float


def test_parameter_space_round_trip():
    """Test ParameterSpace round-trip serialization."""
    original = ParameterSpace("test_param", values=[1, 2, 3], min_val=0.0, max_val=10.0, step=1.0, distribution="log", param_type=int)
    data = original.to_dict()
    restored = ParameterSpace.from_dict(data)

    assert restored.name == original.name
    assert restored.values == original.values
    assert restored.min_val == original.min_val
    assert restored.max_val == original.max_val
    assert restored.step == original.step
    assert restored.distribution == original.distribution
    assert restored.param_type == original.param_type


def test_parameter_grid_to_dict():
    """Test ParameterGrid.to_dict serialization."""
    grid = ParameterGrid()
    grid.add(ParameterSpace("a", values=[1, 2], param_type=int))
    grid.add(ParameterSpace("b", min_val=0.0, max_val=1.0, step=0.5, param_type=float))

    data = grid.to_dict()

    assert "spaces" in data
    assert "a" in data["spaces"]
    assert "b" in data["spaces"]
    assert data["spaces"]["a"]["name"] == "a"
    assert data["spaces"]["a"]["values"] == [1, 2]
    assert data["spaces"]["a"]["param_type"] == "int"
    assert data["spaces"]["b"]["name"] == "b"
    assert data["spaces"]["b"]["min_val"] == 0.0
    assert data["spaces"]["b"]["max_val"] == 1.0
    assert data["spaces"]["b"]["step"] == 0.5
    assert data["spaces"]["b"]["param_type"] == "float"


def test_parameter_grid_from_dict():
    """Test ParameterGrid.from_dict deserialization."""
    data = {
        "spaces": {
            "a": {"name": "a", "values": [1, 2], "param_type": "int"},
            "b": {"name": "b", "min_val": 0.0, "max_val": 1.0, "step": 0.5, "param_type": "float"},
        }
    }
    grid = ParameterGrid.from_dict(data)

    assert "a" in grid.spaces
    assert "b" in grid.spaces
    assert grid.spaces["a"].name == "a"
    assert grid.spaces["a"].values == [1, 2]
    assert grid.spaces["a"].param_type == int
    assert grid.spaces["b"].name == "b"
    assert grid.spaces["b"].min_val == 0.0
    assert grid.spaces["b"].max_val == 1.0
    assert grid.spaces["b"].step == 0.5
    assert grid.spaces["b"].param_type == float


def test_parameter_grid_round_trip():
    """Test ParameterGrid round-trip serialization."""
    original = ParameterGrid()
    original.add(ParameterSpace("a", values=[1, 2], param_type=int))
    original.add(ParameterSpace("b", min_val=0.0, max_val=1.0, step=0.5, param_type=float))

    data = original.to_dict()
    restored = ParameterGrid.from_dict(data)

    assert list(restored.spaces.keys()) == list(original.spaces.keys())
    for name in original.spaces:
        orig_space = original.spaces[name]
        rest_space = restored.spaces[name]
        assert rest_space.name == orig_space.name
        assert rest_space.values == orig_space.values
        assert rest_space.min_val == orig_space.min_val
        assert rest_space.max_val == orig_space.max_val
        assert rest_space.step == orig_space.step
        assert rest_space.distribution == orig_space.distribution
        assert rest_space.param_type == orig_space.param_type


def test_parameter_grid_from_dict_empty():
    """Test ParameterGrid.from_dict with empty spaces."""
    grid = ParameterGrid.from_dict({})
    assert grid.spaces == {}

    grid = ParameterGrid.from_dict({"spaces": {}})
    assert grid.spaces == {}


def test_objective_functions():
    """Test objective functions."""
    from quant_trading.backtest.metrics import BacktestMetrics

    equity_curve = pd.Series([100000, 101000, 102000, 101500, 103000])
    trades = pd.DataFrame(
        [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200},
        ]
    )

    metrics = BacktestMetrics()
    metrics.sharpe_ratio = 1.5
    metrics.total_return_pct = 3.0
    metrics.calmar_ratio = 2.0
    metrics.max_drawdown_pct = -2.0
    metrics.profit_factor = 2.5
    metrics.win_rate = 0.67
    metrics.sortino_ratio = 3.0
    metrics.num_trades = 3

    from quant_trading.backtest.engine import BacktestResult

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime(2026, 1, 15) - timedelta(days=10),
        end_date=datetime(2026, 1, 15),
        initial_capital=100000.0,
        final_value=103000.0,
        total_return=3000.0,
        total_return_pct=3.0,
    )

    assert maximize_sharpe(result) == 1.5
    assert maximize_total_return(result) == 3.0
    assert maximize_calmar(result) == 2.0
    assert minimize_max_drawdown(result) == 2.0  # negative of -2.0
    assert maximize_profit_factor(result) == 2.5
    assert maximize_win_rate(result) == 0.67
    assert maximize_sortino(result) == 3.0


def test_maximize_sortino_none_returns_zero():
    """maximize_sortino returns 0.0 when the Sortino ratio is unset."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import BacktestMetrics

    metrics = BacktestMetrics()
    eq = pd.Series([100000, 105000], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")])
    result = BacktestResult(
        equity_curve=eq,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=pd.Timestamp("2024-01-01"),
        end_date=pd.Timestamp("2024-01-31"),
        initial_capital=100000,
        final_value=105000,
        total_return=5000,
        total_return_pct=5.0,
    )
    assert maximize_sortino(result) == 0.0


def test_grid_search():
    """Test GridSearch optimization."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


def test_grid_search_periods_per_year_is_threaded():
    """The optimizer must annualize its backtests with the requested period count."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[2], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[3], param_type=int))

    def _score(periods_per_year: int) -> float:
        optimizer = GridSearch(
            strategy_cls=MovingAverageCrossover,
            param_grid=param_grid,
            objective=maximize_sharpe,
            symbols=symbols,
            start=datetime(2026, 1, 15) - timedelta(days=50),
            end=datetime(2026, 1, 15),
            initial_capital=100000.0,
            data_manager=data_manager,
            periods_per_year=periods_per_year,
            verbose=False,
        )
        return optimizer.run().best_score

    assert _score(12) != pytest.approx(_score(252))


def test_random_search():
    """Test RandomSearch optimization."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_iter=5,
        random_state=42,
        verbose=False,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 5


def test_optimization_result_to_dataframe():
    """Test OptimizationResult to_dataframe method."""
    from quant_trading.optimization.base import OptimizationResult

    result = OptimizationResult(
        best_params={"a": 1},
        best_score=1.0,
        all_results=[
            {"params": {"a": 1}, "score": 1.0},
            {"params": {"a": 2}, "score": 0.5},
        ],
    )

    df = result.to_dataframe()
    assert len(df) == 2
    assert list(df.columns) == ["params", "score"]


def test_optimization_result_get_top_n():
    """Test OptimizationResult get_top_n method."""
    from quant_trading.optimization.base import OptimizationResult

    result = OptimizationResult(
        best_params={"a": 1},
        best_score=1.0,
        all_results=[
            {"params": {"a": 1}, "score": 1.0},
            {"params": {"a": 2}, "score": 0.5},
            {"params": {"a": 3}, "score": 0.8},
        ],
    )

    top = result.get_top_n(2)
    assert len(top) == 2
    assert top[0]["score"] == 1.0
    assert top[1]["score"] == 0.8


def test_walk_forward_optimizer():
    """Test WalkForwardOptimizer."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=180),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=3,
        train_size=0.7,
        anchored=True,
        optimizer="grid",
        verbose=False,
    )

    result = optimizer.run()

    assert len(result.windows) == 3
    for window in result.windows:
        assert window.best_params is not None
        assert window.train_result is not None
        assert window.test_result is not None

    df = result.to_dataframe()
    assert len(df) == 3
    assert "train_return_pct" in df.columns
    assert "test_return_pct" in df.columns

    summary = result.summary()
    assert "n_windows" in summary
    assert summary["n_windows"] == 3


def test_grid_search_with_multiple_symbols():
    """Test GridSearch with multiple symbols."""
    symbols = ["AAPL", "MSFT"]
    mock_data = {
        "AAPL": create_test_data("AAPL", days=60),
        "MSFT": create_test_data("MSFT", days=60),
    }
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert len(result.all_results) == 4


def test_random_search_different_objectives():
    """Test RandomSearch with different objective functions."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("period", values=[10, 14, 20], param_type=int))
    param_grid.add(ParameterSpace("oversold", values=[20, 30], param_type=int))
    param_grid.add(ParameterSpace("overbought", values=[70, 80], param_type=int))

    for objective in [
        maximize_sharpe,
        maximize_total_return,
        maximize_calmar,
        minimize_max_drawdown,
        maximize_profit_factor,
        maximize_win_rate,
    ]:
        optimizer = RandomSearch(
            strategy_cls=RSIStrategy,
            param_grid=param_grid,
            objective=objective,
            symbols=symbols,
            start=datetime(2026, 1, 15) - timedelta(days=50),
            end=datetime(2026, 1, 15),
            initial_capital=100000.0,
            data_manager=data_manager,
            n_iter=3,
            random_state=42,
            verbose=False,
        )

        result = optimizer.run()
        assert result.best_params is not None
        assert result.best_score != float("-inf")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_walk_forward_combine_with_partial_windows():
    """Test WalkForwardOptimizer _combine_test_results with some None test results."""
    from quant_trading.backtest.engine import run_backtest
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=100)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=90),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=2,
        train_size=0.5,
        anchored=True,
        verbose=False,
    )

    start_dt = datetime(2026, 1, 15) - timedelta(days=90)
    windows = [
        WalkForwardWindow(
            train_start=start_dt,
            train_end=start_dt + timedelta(days=30),
            test_start=start_dt + timedelta(days=30),
            test_end=start_dt + timedelta(days=60),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=None,
        ),
        WalkForwardWindow(
            train_start=start_dt,
            train_end=start_dt + timedelta(days=45),
            test_start=start_dt + timedelta(days=45),
            test_end=start_dt + timedelta(days=75),
            best_params={"fast_period": 5, "slow_period": 20},
        ),
    ]
    strategy = MovingAverageCrossover(fast_period=5, slow_period=20)
    windows[1].test_result = run_backtest(
        strategy=strategy,
        symbols=symbols,
        start=windows[1].test_start,
        end=windows[1].test_end,
        initial_capital=100000.0,
        data_manager=data_manager,
    )

    combined = optimizer._combine_test_results(windows)
    assert combined is not None


def test_parameter_space_log_distribution():
    """Test ParameterSpace log distribution sampling."""
    space = ParameterSpace("test", min_val=1, max_val=100, distribution="log")
    samples = space.sample_random(5, rng=np.random.default_rng(42))
    assert len(samples) == 5
    assert all(1 <= s <= 100 for s in samples)
    # Log distribution should produce values in range


@skip_if_no_skopt
def test_bayesian_optimizer():
    """Test BayesianOptimizer optimization."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=3,
        n_calls=8,
        random_state=42,
        verbose=False,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 8


@skip_if_no_skopt
def test_bayesian_optimizer_categorical():
    """Test BayesianOptimizer with categorical parameters."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10, 15], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 25, 30], param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=3,
        n_calls=8,
        random_state=42,
        verbose=False,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 8


@skip_if_no_skopt
def test_bayesian_optimizer_multiple_symbols():
    """Test BayesianOptimizer with multiple symbols."""
    symbols = ["AAPL", "MSFT"]
    mock_data = {
        "AAPL": create_test_data("AAPL", days=60),
        "MSFT": create_test_data("MSFT", days=60),
    }
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=3,
        n_calls=8,
        random_state=42,
        verbose=False,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert len(result.all_results) == 8


@skip_if_no_skopt
def test_bayesian_optimizer_different_objectives():
    """Test BayesianOptimizer with different objective functions."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("period", min_val=10, max_val=20, param_type=int))
    param_grid.add(ParameterSpace("oversold", min_val=20, max_val=35, param_type=int))
    param_grid.add(ParameterSpace("overbought", min_val=65, max_val=80, param_type=int))

    for objective in [
        maximize_sharpe,
        maximize_total_return,
        maximize_calmar,
        minimize_max_drawdown,
        maximize_profit_factor,
        maximize_win_rate,
    ]:
        optimizer = BayesianOptimizer(
            strategy_cls=RSIStrategy,
            param_grid=param_grid,
            objective=objective,
            symbols=symbols,
            start=datetime(2026, 1, 15) - timedelta(days=50),
            end=datetime(2026, 1, 15),
            initial_capital=100000.0,
            data_manager=data_manager,
            n_initial_points=3,
            n_calls=8,
            random_state=42,
            verbose=False,
        )

        result = optimizer.run()
        assert result.best_params is not None
        assert result.best_score != float("-inf")


@skip_if_no_skopt
def test_walk_forward_with_bayesian():
    """Test WalkForwardOptimizer with Bayesian optimizer."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=180),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=3,
        train_size=0.7,
        anchored=True,
        optimizer="bayesian",
        optimizer_kwargs={"n_initial_points": 2, "n_calls": 5, "random_state": 42},
        verbose=False,
    )

    result = optimizer.run()

    assert len(result.windows) == 3
    for window in result.windows:
        assert window.best_params is not None
        assert window.train_result is not None
        assert window.test_result is not None

    df = result.to_dataframe()
    assert len(df) == 3
    assert "train_return_pct" in df.columns
    assert "test_return_pct" in df.columns

    summary = result.summary()
    assert "n_windows" in summary
    assert summary["n_windows"] == 3


class RaisingStrategy(Strategy):
    """Strategy that raises ValueError in generate_signals for error handling tests."""

    def __init__(self, name: str = "Raising", **kwargs):
        super().__init__(name, kwargs)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        raise ValueError("boom")


def test_parameter_space_requires_values_or_min():
    """Test ParameterSpace __post_init__ raises when neither values nor min_val provided."""
    with pytest.raises(ValueError, match="Either values or min_val must be provided"):
        ParameterSpace("test")


def test_parameter_space_generate_grid_fallback():
    """Test generate_grid returns empty list when min_val set but max_val/step not."""
    space = ParameterSpace("test", min_val=1.0)
    assert space.generate_grid() == []


@pytest.mark.parametrize("step", [0, 0.0, -1, -0.5])
def test_parameter_space_generate_grid_rejects_a_non_positive_step(step):
    """A step of zero would make the grid loop forever, so it is rejected."""
    space = ParameterSpace("test", min_val=1.0, max_val=5.0, step=step)
    with pytest.raises(ValueError, match="step must be greater than 0"):
        space.generate_grid()


def test_parameter_space_generate_grid_with_values_ignores_the_step():
    """An explicit list of values is used as it is, whatever the step is."""
    space = ParameterSpace("test", values=[1, 2, 3], step=0)
    assert space.generate_grid() == [1, 2, 3]


def test_parameter_space_generate_grid_rejects_an_inverted_range():
    """A minimum above the maximum cannot generate a grid."""
    space = ParameterSpace("test", min_val=5.0, max_val=2.0, step=1.0)
    with pytest.raises(ValueError, match="minimum.*greater than the maximum"):
        space.generate_grid()


def test_parameter_space_generate_grid_rejects_an_inverted_range_with_float_step():
    """An inverted range is rejected whatever the step size is."""
    space = ParameterSpace("test", min_val=10.0, max_val=1.0, step=0.5)
    with pytest.raises(ValueError, match="minimum.*greater than the maximum"):
        space.generate_grid()


def test_parameter_space_sample_random_fallback():
    """Test sample_random returns empty list when min_val set but max_val not."""
    space = ParameterSpace("test", min_val=1.0)
    assert space.sample_random(3) == []


def test_parameter_grid_empty_generate_combinations():
    """Test empty ParameterGrid generates a single empty combination."""
    grid = ParameterGrid()
    assert grid.generate_combinations() == [{}]


def test_parameter_grid_empty_sample_random():
    """Test empty ParameterGrid samples empty dicts."""
    grid = ParameterGrid()
    assert grid.sample_random(3) == [{}, {}, {}]


def test_optimization_result_duration_none():
    """Test duration_seconds is None when start/end not set."""
    result = OptimizationResult(best_params={}, best_score=0.0)
    assert result.duration_seconds is None


def test_optimization_result_duration_set():
    """Test duration_seconds calculates when start/end set."""
    start = datetime(2026, 1, 15)
    end = start + timedelta(seconds=5)
    result = OptimizationResult(best_params={}, best_score=0.0, start_time=start, end_time=end)
    assert result.duration_seconds == pytest.approx(5.0, abs=0.1)


def test_optimization_result_to_dataframe_empty():
    """Test to_dataframe returns empty DataFrame when no results."""
    result = OptimizationResult(best_params={}, best_score=0.0)
    df = result.to_dataframe()
    assert df.empty


def test_base_optimizer_evaluate_params_error():
    """Test _evaluate_params catches ValueError and returns -inf score."""
    from quant_trading.optimization.base import BaseOptimizer, ParameterGrid, ParameterSpace

    class TestOptimizer(BaseOptimizer):
        def run(self) -> OptimizationResult:
            return OptimizationResult(best_params={}, best_score=0.0)

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = TestOptimizer(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=True,
    )

    params, score, result = optimizer._evaluate_params({"fast_period": 5, "slow_period": 20})
    assert params == {"fast_period": 5, "slow_period": 20}
    assert score == float("-inf")
    assert result is None


def test_base_optimizer_evaluate_params_error_quiet():
    """_evaluate_params with verbose=False skips the error print (265->267)."""
    from quant_trading.optimization.base import BaseOptimizer, ParameterGrid, ParameterSpace

    class TestOptimizer(BaseOptimizer):
        def run(self) -> OptimizationResult:
            return OptimizationResult(best_params={}, best_score=0.0)

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = TestOptimizer(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
    )

    _params, score, result = optimizer._evaluate_params({"fast_period": 5, "slow_period": 20})
    assert score == float("-inf")
    assert result is None


def test_base_optimizer_n_jobs_minus_one_uses_cpu_count():
    """n_jobs=-1 resolves to os.cpu_count() (base.py:640-641)."""
    from quant_trading.optimization.base import BaseOptimizer, ParameterGrid, ParameterSpace

    class TestOptimizer(BaseOptimizer):
        def run(self) -> OptimizationResult:
            return OptimizationResult(best_params={}, best_score=0.0)

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))

    optimizer = TestOptimizer(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_jobs=-1,
    )
    expected = os.cpu_count() or 1
    assert optimizer.n_jobs == max(expected, 1)


def test_grid_search_verbose(capsys):
    """Test GridSearch verbose prints progress."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=True,
    )

    optimizer.run()
    out = capsys.readouterr().out
    assert "GridSearch: Evaluating" in out
    assert "New best" in out
    assert "GridSearch complete" in out


def test_grid_search_n_combinations():
    """Test n_combinations property returns total count."""
    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("a", values=[1, 2]))
    param_grid.add(ParameterSpace("b", values=[10, 20]))
    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2026, 1, 15) - timedelta(days=10),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
        verbose=False,
    )
    assert optimizer.n_combinations == 4


def test_grid_search_pytest_time_cap_respects_env(monkeypatch):
    """The pytest-time combination cap is read from ``QT_TEST_MAX_GRID_COMBINATIONS``.

    The grid cap is only applied when ``PYTEST_CURRENT_TEST`` is set (i.e. under
    pytest) and the grid is larger than the cap. When the env var overrides the
    default, the sampled combination count matches the override rather than the
    built-in default of 60.
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_grid_search_pytest_time_cap_respects_env")
    monkeypatch.setenv("QT_TEST_MAX_GRID_COMBINATIONS", "7")

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("a", values=[1, 2, 3, 4, 5]))
    param_grid.add(ParameterSpace("b", values=[10, 20, 30, 40, 50]))
    param_grid.add(ParameterSpace("c", values=[100, 200, 300, 400, 500]))
    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2026, 1, 15) - timedelta(days=10),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
        verbose=False,
    )
    assert optimizer.n_combinations == 125
    optimizer.run()
    assert optimizer.n_combinations == 7


def test_random_search_pytest_time_cap_respects_env(monkeypatch):
    """The pytest-time iteration cap is read from ``QT_TEST_MAX_RANDOM_ITERATIONS``.

    The random-search cap is only applied under pytest (``PYTEST_CURRENT_TEST``
    set) and only when the requested iteration count exceeds the cap. The
    override env var lowers the effective iteration count below the built-in
    default of 30.
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_random_search_pytest_time_cap_respects_env")
    monkeypatch.setenv("QT_TEST_MAX_RANDOM_ITERATIONS", "5")

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_iter=200,
        verbose=False,
    )
    assert optimizer.n_iter == 200
    optimizer.run()
    assert optimizer.n_iter == 5


@skip_if_no_skopt
def test_bayesian_pytest_time_cap_respects_env(monkeypatch):
    """The pytest-time Bayesian caps are read from the env vars.

    Both ``QT_TEST_MAX_BAYESIAN_CALLS`` and ``QT_TEST_MAX_BAYESIAN_INIT`` are
    honored when ``PYTEST_CURRENT_TEST`` is set and the requested values exceed
    the caps, so a run configured with large values still evaluates only the
    capped number of combinations.
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_bayesian_pytest_time_cap_respects_env")
    monkeypatch.setenv("QT_TEST_MAX_BAYESIAN_CALLS", "6")
    monkeypatch.setenv("QT_TEST_MAX_BAYESIAN_INIT", "2")

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=50,
        n_calls=200,
        random_state=42,
        verbose=False,
    )
    assert optimizer.n_calls == 200
    assert optimizer.n_initial_points == 50
    result = optimizer.run()
    assert optimizer.n_calls == 6
    assert optimizer.n_initial_points == 2
    assert len(result.all_results) == 6


@skip_if_no_skopt
def test_bayesian_pytest_time_cap_disabled_outside_pytest(monkeypatch):
    """When ``PYTEST_CURRENT_TEST`` is unset the caps are not applied.

    pytest itself sets ``PYTEST_CURRENT_TEST`` for every test, so the
    cap-ignoring branch (``if os.environ.get("PYTEST_CURRENT_TEST"):``
    False path) is never hit during a normal pytest run. Unsetting the var
    explicitly exercises that branch and confirms a non-pytest invocation
    honors the full requested ``n_calls`` / ``n_initial_points``.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=3,
        n_calls=8,
        random_state=42,
        verbose=False,
    )
    assert optimizer.n_calls == 8
    assert optimizer.n_initial_points == 3
    result = optimizer.run()
    assert optimizer.n_calls == 8
    assert optimizer.n_initial_points == 3
    assert len(result.all_results) == 8


def test_random_search_verbose(capsys):
    """Test RandomSearch verbose prints progress."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_iter=3,
        random_state=42,
        verbose=True,
    )

    optimizer.run()
    out = capsys.readouterr().out
    assert "RandomSearch: Evaluating" in out
    assert "New best" in out
    assert "RandomSearch complete" in out


def test_walk_forward_rolling_mode():
    """Test WalkForwardOptimizer with rolling (non-anchored) windows."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=180),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=3,
        train_size=0.7,
        anchored=False,
        optimizer="grid",
        verbose=False,
    )

    result = optimizer.run()
    assert len(result.windows) >= 1
    for window in result.windows:
        assert window.best_params is not None
        assert window.train_result is not None
        assert window.test_result is not None


def test_walk_forward_step_size_override():
    """Test WalkForwardOptimizer with explicit step_size override."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=180),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=3,
        train_size=0.5,
        step_size=0.3,
        anchored=False,
        optimizer="grid",
        verbose=False,
    )

    result = optimizer.run()
    assert len(result.windows) >= 1


def test_walk_forward_unknown_optimizer():
    """Test WalkForwardOptimizer raises for unknown optimizer type."""
    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=ParameterGrid(),
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2026, 1, 15) - timedelta(days=10),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
        optimizer="unknown",
    )
    with pytest.raises(ValueError, match="Unknown optimizer type"):
        optimizer.run()


def test_walk_forward_no_dates():
    """Test WalkForwardOptimizer _generate_windows raises when dates not set."""
    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=ParameterGrid(),
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=None,
        end=None,
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )
    with pytest.raises(ValueError, match="start and end dates must be provided"):
        optimizer.run()


def test_walk_forward_combine_no_valid_windows():
    """Test _combine_test_results returns None when no windows have test results."""
    from quant_trading.optimization.walk_forward import WalkForwardOptimizer, WalkForwardWindow

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=ParameterGrid(),
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2026, 1, 15) - timedelta(days=10),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )

    windows = [
        WalkForwardWindow(
            train_start=datetime(2026, 1, 15) - timedelta(days=5),
            train_end=datetime(2026, 1, 15) - timedelta(days=3),
            test_start=datetime(2026, 1, 15) - timedelta(days=3),
            test_end=datetime(2026, 1, 15),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=None,
        )
    ]
    combined = optimizer._combine_test_results(windows)
    assert combined is None


def test_walk_forward_combine_no_equity():
    """Test _combine_test_results returns None when equity curves have no data."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import BacktestMetrics
    from quant_trading.optimization.walk_forward import WalkForwardOptimizer, WalkForwardWindow

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=ParameterGrid(),
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2026, 1, 15) - timedelta(days=10),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )

    # Create test result with single-point equity curve (no returns)
    metrics = BacktestMetrics()
    test_result = BacktestResult(
        equity_curve=pd.Series([100000.0], index=[datetime(2026, 1, 15)]),
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=datetime(2026, 1, 15) - timedelta(days=1),
        end_date=datetime(2026, 1, 15),
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )

    windows = [
        WalkForwardWindow(
            train_start=datetime(2026, 1, 15) - timedelta(days=5),
            train_end=datetime(2026, 1, 15) - timedelta(days=3),
            test_start=datetime(2026, 1, 15) - timedelta(days=3),
            test_end=datetime(2026, 1, 15),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=test_result,
        )
    ]
    combined = optimizer._combine_test_results(windows)
    assert combined is None


def test_walk_forward_combine_chains_equity_across_windows():
    """Test _combine_test_results chains window equity curves instead of resetting.

    Each window's backtest starts fresh at initial_capital, so the combined
    out-of-sample curve must scale each subsequent window so it continues from
    the previous windows' final equity. Regression test for a bug where the
    combined curve reset to initial_capital at every window boundary.
    """
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=ParameterGrid(),
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 4, 1),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 200)})]),
    )

    start_dt = datetime(2024, 1, 1)
    windows = [
        WalkForwardWindow(
            train_start=start_dt,
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5, "slow_period": 20},
        ),
        WalkForwardWindow(
            train_start=start_dt,
            train_end=datetime(2024, 3, 1),
            test_start=datetime(2024, 3, 1),
            test_end=datetime(2024, 4, 1),
            best_params={"fast_period": 5, "slow_period": 20},
        ),
    ]

    eq1 = pd.Series(
        [100000.0, 110000.0, 105000.0],
        index=pd.to_datetime(["2024-02-01", "2024-02-15", "2024-03-01"]),
    )
    eq2 = pd.Series(
        [100000.0, 95000.0, 100000.0],
        index=pd.to_datetime(["2024-03-01", "2024-03-15", "2024-04-01"]),
    )
    m1 = calculate_backtest_metrics(eq1)
    m2 = calculate_backtest_metrics(eq2)
    windows[0].test_result = BacktestResult(
        equity_curve=eq1,
        trades=pd.DataFrame(),
        positions={},
        metrics=m1,
        start_date=windows[0].test_start,
        end_date=windows[0].test_end,
        initial_capital=100000.0,
        final_value=eq1.iloc[-1],
        total_return=eq1.iloc[-1] - 100000.0,
        total_return_pct=(eq1.iloc[-1] / 100000.0 - 1) * 100,
    )
    windows[1].test_result = BacktestResult(
        equity_curve=eq2,
        trades=pd.DataFrame(),
        positions={},
        metrics=m2,
        start_date=windows[1].test_start,
        end_date=windows[1].test_end,
        initial_capital=100000.0,
        final_value=eq2.iloc[-1],
        total_return=eq2.iloc[-1] - 100000.0,
        total_return_pct=(eq2.iloc[-1] / 100000.0 - 1) * 100,
    )

    combined = optimizer._combine_test_results(windows)
    assert combined is not None
    # Window 1 ends at 105000; window 2 returns -5% from that base -> 99750,
    # then +5.26% -> 105000. Total chained return is +5.0% from initial capital.
    assert [round(float(v), 2) for v in combined.equity_curve.values] == [
        100000.0,
        110000.0,
        105000.0,
        99750.0,
        105000.0,
    ]
    assert abs(combined.total_return_pct - 5.0) < 1e-9


def test_walk_forward_combine_sums_window_costs():
    """The combined walk-forward result reports the total costs of all windows.

    Each window pays its own commission and slippage, so the combined result
    must expose their sum rather than zero or one window's costs.
    """
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=ParameterGrid(),
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 4, 1),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 200)})]),
    )

    start_dt = datetime(2024, 1, 1)
    windows = [
        WalkForwardWindow(
            train_start=start_dt,
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5, "slow_period": 20},
        ),
        WalkForwardWindow(
            train_start=start_dt,
            train_end=datetime(2024, 3, 1),
            test_start=datetime(2024, 3, 1),
            test_end=datetime(2024, 4, 1),
            best_params={"fast_period": 5, "slow_period": 20},
        ),
    ]

    eq1 = pd.Series(
        [100000.0, 110000.0, 105000.0],
        index=pd.to_datetime(["2024-02-01", "2024-02-15", "2024-03-01"]),
    )
    eq2 = pd.Series(
        [100000.0, 95000.0, 100000.0],
        index=pd.to_datetime(["2024-03-01", "2024-03-15", "2024-04-01"]),
    )
    windows[0].test_result = BacktestResult(
        equity_curve=eq1,
        trades=pd.DataFrame(),
        positions={},
        metrics=calculate_backtest_metrics(eq1),
        start_date=windows[0].test_start,
        end_date=windows[0].test_end,
        initial_capital=100000.0,
        final_value=eq1.iloc[-1],
        total_return=eq1.iloc[-1] - 100000.0,
        total_return_pct=(eq1.iloc[-1] / 100000.0 - 1) * 100,
        total_costs=12.5,
    )
    windows[1].test_result = BacktestResult(
        equity_curve=eq2,
        trades=pd.DataFrame(),
        positions={},
        metrics=calculate_backtest_metrics(eq2),
        start_date=windows[1].test_start,
        end_date=windows[1].test_end,
        initial_capital=100000.0,
        final_value=eq2.iloc[-1],
        total_return=eq2.iloc[-1] - 100000.0,
        total_return_pct=(eq2.iloc[-1] / 100000.0 - 1) * 100,
        total_costs=7.25,
    )

    combined = optimizer._combine_test_results(windows)
    assert combined is not None
    assert combined.total_costs == pytest.approx(19.75)


WALK_FORWARD_START = datetime(2024, 1, 1)
WALK_FORWARD_END = datetime(2024, 6, 28)


def _walk_forward_optimizer(**overrides):
    """Build a walk-forward optimizer over deterministic mock data."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200, end=WALK_FORWARD_END)}
    data_manager = DataManager([MockDataProvider(mock_data)])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[2], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[5], param_type=int))

    settings = {
        "strategy_cls": MovingAverageCrossover,
        "param_grid": param_grid,
        "objective": maximize_sharpe,
        "symbols": symbols,
        "start": WALK_FORWARD_START,
        "end": WALK_FORWARD_END,
        "initial_capital": 100000.0,
        "data_manager": data_manager,
        "n_windows": 4,
        "train_size": 0.6,
    }
    settings.update(overrides)
    return WalkForwardOptimizer(**settings)


@pytest.mark.parametrize("anchored", [True, False])
def test_walk_forward_test_periods_do_not_overlap(anchored):
    """The out-of-sample periods of two windows never overlap.

    A period that is evaluated out-of-sample by two windows would be counted
    twice in the combined out-of-sample result, so the test period of a window
    stops where the next window's training period begins.
    """
    optimizer = _walk_forward_optimizer(anchored=anchored)
    windows = optimizer._generate_windows()

    assert len(windows) == optimizer.n_windows
    for previous, current in itertools.pairwise(windows):
        # The out-of-sample periods are chronological and never overlap.
        assert current.test_start >= previous.test_end
        # The test period follows the training period of its own window, so the
        # training data never reaches into the period it is scored on.
        assert current.test_start == current.train_end
        # The training period of a window never starts before the training
        # period of the previous window.
        assert current.train_start >= previous.train_start

    # The out-of-sample periods reach the end of the requested period, up to
    # the remainder of the last window.
    window_days = (optimizer.end - optimizer.start).days // optimizer.n_windows
    assert windows[-1].test_end <= optimizer.end
    assert (optimizer.end - windows[-1].test_end).days <= window_days


@pytest.mark.parametrize("anchored", [True, False])
def test_walk_forward_combined_equity_is_strictly_increasing(anchored):
    """The combined out-of-sample equity curve is a valid time series.

    The combined curve is the chain of the windows' equity curves, so its
    index has to increase strictly: a period that appears twice would put the
    index out of order and break every time-series operation on it.
    """
    optimizer = _walk_forward_optimizer(anchored=anchored)
    result = optimizer.run()

    combined = result.combined_test_result
    assert combined is not None

    index = combined.equity_curve.index
    assert index.is_monotonic_increasing
    assert index.is_unique

    # Every bar of every window is in the combined curve exactly once.
    expected_bars = sum(
        len(w.test_result.equity_curve) - 1
        for w in result.windows
        if w.test_result is not None and len(w.test_result.equity_curve) >= 2
    )
    assert len(combined.equity_curve) == expected_bars + 1


def test_walk_forward_combined_pnl_is_the_chained_realized_pnl():
    """The combined result's realized PnL is the chained PnL of the windows.

    Every window's backtest starts fresh at the initial capital, so its PnL is
    booked in its own capital base. The combined account is the chain of those
    windows, so the combined PnL is the sum of the windows' PnL, each scaled by
    the factor that scales the window's equity curve.
    """
    optimizer = _walk_forward_optimizer()
    result = optimizer.run()

    combined = result.combined_test_result
    assert combined is not None

    cumulative = optimizer.initial_capital
    expected_pnl = 0.0
    for window in result.windows:
        test_result = window.test_result
        if test_result is None or len(test_result.equity_curve) < 2:
            continue
        scale = cumulative / optimizer.initial_capital
        trades = test_result.trades
        if not trades.empty and "pnl" in trades.columns:
            expected_pnl += scale * float(trades["pnl"].sum())
        cumulative = float(test_result.equity_curve.iloc[-1]) * scale

    assert combined.metrics.total_pnl == pytest.approx(expected_pnl)
    assert combined.final_value == pytest.approx(cumulative)


def test_walk_forward_combined_result_can_be_analyzed():
    """The combined out-of-sample result can be analyzed like any other result.

    The trade analysis looks equity values up by timestamp, which needs an
    index that increases strictly.
    """
    from quant_trading.backtest.trade_analysis import analyze_trades

    optimizer = _walk_forward_optimizer()
    result = optimizer.run()

    combined = result.combined_test_result
    assert combined is not None

    analysis = analyze_trades(combined)
    assert analysis.total_trades >= 0
    assert analysis.total_pnl == pytest.approx(combined.metrics.total_pnl)


def test_walk_forward_to_dataframe_is_json_safe():
    """``WalkForwardResult.to_dataframe()`` must be JSON-serializable.

    The frame's four date-boundary columns hold raw ``datetime`` objects, which
    are not JSON-serializable. A consumer that dumps the frame to JSON (for
    example ``examples/cli.py --walk-forward --output out.json``) would raise
    ``TypeError: Object of type Timestamp is not JSON serializable`` unless the
    boundaries are emitted as ISO-8601 strings, matching the contract already
    enforced by :meth:`WalkForwardWindow.to_dict`.
    """
    import json

    optimizer = _walk_forward_optimizer()
    result = optimizer.run()

    df = result.to_dataframe()
    assert not df.empty

    # The frame must round-trip through a JSON encoder with no default hook.
    records = json.loads(json.dumps(df.to_dict(orient="records")))

    # The serialized boundaries are ISO-8601 strings, not raw datetimes.
    first = records[0]
    for column in ("train_start", "train_end", "test_start", "test_end"):
        assert isinstance(first[column], str), (
            f"{column} serialized as {type(first[column]).__name__}, expected str"
        )
        # The string must round-trip back to a datetime.
        datetime.fromisoformat(first[column])


def test_walk_forward_combine_drops_overlapping_points():
    """Overlapping out-of-sample periods are combined into one time series.

    The combined curve is a time series, so a point that is not later than the
    last emitted one is dropped instead of putting the index out of order.
    """
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    optimizer = _walk_forward_optimizer()

    # The two windows share the 2024-03-15 bar, so their test periods overlap.
    eq1 = pd.Series(
        [100000.0, 110000.0, 105000.0],
        index=pd.to_datetime(["2024-02-01", "2024-02-15", "2024-03-15"]),
    )
    eq2 = pd.Series(
        [100000.0, 95000.0, 100000.0],
        index=pd.to_datetime(["2024-03-01", "2024-03-15", "2024-04-01"]),
    )
    windows = [
        WalkForwardWindow(
            train_start=WALK_FORWARD_START,
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=BacktestResult(
                equity_curve=eq1,
                trades=pd.DataFrame(),
                positions={},
                metrics=calculate_backtest_metrics(eq1),
                start_date=datetime(2024, 2, 1),
                end_date=datetime(2024, 3, 1),
                initial_capital=100000.0,
                final_value=eq1.iloc[-1],
                total_return=eq1.iloc[-1] - 100000.0,
                total_return_pct=(eq1.iloc[-1] / 100000.0 - 1) * 100,
            ),
        ),
        WalkForwardWindow(
            train_start=WALK_FORWARD_START,
            train_end=datetime(2024, 3, 1),
            test_start=datetime(2024, 3, 1),
            test_end=datetime(2024, 4, 1),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=BacktestResult(
                equity_curve=eq2,
                trades=pd.DataFrame(),
                positions={},
                metrics=calculate_backtest_metrics(eq2),
                start_date=datetime(2024, 3, 1),
                end_date=datetime(2024, 4, 1),
                initial_capital=100000.0,
                final_value=eq2.iloc[-1],
                total_return=eq2.iloc[-1] - 100000.0,
                total_return_pct=(eq2.iloc[-1] / 100000.0 - 1) * 100,
            ),
        ),
    ]

    combined = optimizer._combine_test_results(windows)
    assert combined is not None
    index = combined.equity_curve.index
    assert index.is_monotonic_increasing
    assert index.is_unique


def test_walk_forward_combine_window_with_no_new_points_does_not_update_cumulative():
    """A window whose every bar is already covered leaves cumulative_final unchanged.

    When a later window's test period is entirely contained in the previous
    windows' emitted range, every point is dropped by the ``timestamp <=
    last_timestamp`` filter and ``all_equity`` stays empty for that window, so
    the ``if all_equity:`` update at line 796 is skipped and the combined curve
    continues from the previous cumulative final.
    """
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    optimizer = _walk_forward_optimizer()

    eq1 = pd.Series(
        [100000.0, 110000.0, 105000.0],
        index=pd.to_datetime(["2024-02-01", "2024-02-15", "2024-03-15"]),
    )
    # The second window's bars are all at or before the last emitted bar
    # (2024-03-15), so none of them survive the overlap filter.
    eq2 = pd.Series(
        [100000.0, 95000.0, 100000.0],
        index=pd.to_datetime(["2024-03-01", "2024-03-10", "2024-03-15"]),
    )
    windows = [
        WalkForwardWindow(
            train_start=WALK_FORWARD_START,
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=BacktestResult(
                equity_curve=eq1,
                trades=pd.DataFrame(),
                positions={},
                metrics=calculate_backtest_metrics(eq1),
                start_date=datetime(2024, 2, 1),
                end_date=datetime(2024, 3, 1),
                initial_capital=100000.0,
                final_value=eq1.iloc[-1],
                total_return=eq1.iloc[-1] - 100000.0,
                total_return_pct=(eq1.iloc[-1] / 100000.0 - 1) * 100,
            ),
        ),
        WalkForwardWindow(
            train_start=WALK_FORWARD_START,
            train_end=datetime(2024, 3, 1),
            test_start=datetime(2024, 3, 1),
            test_end=datetime(2024, 4, 1),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=BacktestResult(
                equity_curve=eq2,
                trades=pd.DataFrame(),
                positions={},
                metrics=calculate_backtest_metrics(eq2),
                start_date=datetime(2024, 3, 1),
                end_date=datetime(2024, 4, 1),
                initial_capital=100000.0,
                final_value=eq2.iloc[-1],
                total_return=eq2.iloc[-1] - 100000.0,
                total_return_pct=(eq2.iloc[-1] / 100000.0 - 1) * 100,
            ),
        ),
    ]

    combined = optimizer._combine_test_results(windows)
    assert combined is not None
    # The second window contributes nothing, so the combined curve is just the
    # first window's bars and the cumulative final is 105000.0 (unchanged).
    assert [round(float(v), 2) for v in combined.equity_curve.values] == [
        100000.0,
        110000.0,
        105000.0,
    ]


def test_walk_forward_combine_skips_short_curve_before_valid_window():
    """A single-point window is skipped before a window that contributes data.

    The first window's equity curve has only one bar, so ``len(eq) < 2``
    triggers ``continue`` and ``all_equity`` stays empty; the ``if all_equity:``
    guard at line 796 then skips the ``cumulative_final`` update for that
    window. The second window seeds the combined curve from the initial
    capital instead of from a stale cumulative final.
    """
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    optimizer = _walk_forward_optimizer()

    # Single-point curve: skipped by the ``len(eq) < 2`` guard.
    eq_short = pd.Series(
        [100000.0],
        index=pd.to_datetime(["2024-02-01"]),
    )
    eq2 = pd.Series(
        [100000.0, 105000.0, 110000.0],
        index=pd.to_datetime(["2024-03-01", "2024-03-15", "2024-04-01"]),
    )
    windows = [
        WalkForwardWindow(
            train_start=WALK_FORWARD_START,
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=BacktestResult(
                equity_curve=eq_short,
                trades=pd.DataFrame(),
                positions={},
                metrics=calculate_backtest_metrics(eq_short),
                start_date=datetime(2024, 2, 1),
                end_date=datetime(2024, 3, 1),
                initial_capital=100000.0,
                final_value=100000.0,
                total_return=0.0,
                total_return_pct=0.0,
            ),
        ),
        WalkForwardWindow(
            train_start=WALK_FORWARD_START,
            train_end=datetime(2024, 3, 1),
            test_start=datetime(2024, 3, 1),
            test_end=datetime(2024, 4, 1),
            best_params={"fast_period": 5, "slow_period": 20},
            test_result=BacktestResult(
                equity_curve=eq2,
                trades=pd.DataFrame(),
                positions={},
                metrics=calculate_backtest_metrics(eq2),
                start_date=datetime(2024, 3, 1),
                end_date=datetime(2024, 4, 1),
                initial_capital=100000.0,
                final_value=eq2.iloc[-1],
                total_return=eq2.iloc[-1] - 100000.0,
                total_return_pct=(eq2.iloc[-1] / 100000.0 - 1) * 100,
            ),
        ),
    ]

    combined = optimizer._combine_test_results(windows)
    assert combined is not None
    # The short window is skipped, so the combined curve starts at the initial
    # capital and continues from the second window's bars (scale == 1.0).
    assert [round(float(v), 2) for v in combined.equity_curve.values] == [
        100000.0,
        105000.0,
        110000.0,
    ]


def test_walk_forward_verbose(capsys):
    """Test WalkForwardOptimizer verbose prints window progress."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=180),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=2,
        train_size=0.7,
        anchored=True,
        optimizer="grid",
        verbose=True,
    )

    optimizer.run()
    out = capsys.readouterr().out
    assert "WalkForwardOptimizer:" in out
    assert "Window 1/" in out
    assert "Train:" in out
    assert "Test:" in out
    assert "Best params" in out
    assert "Test return" in out
    assert "Test Sharpe" in out


def test_walk_forward_random_optimizer():
    """Test WalkForwardOptimizer with the RandomSearch optimizer branch."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=200)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=180),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=3,
        train_size=0.7,
        anchored=True,
        optimizer="random",
        optimizer_kwargs={"n_iter": 2, "random_state": 42},
        verbose=False,
    )

    result = optimizer.run()
    assert len(result.windows) == 3
    for window in result.windows:
        assert window.best_params is not None
        assert window.train_result is not None
        assert window.test_result is not None


def test_walk_forward_degenerate_break():
    """Test _generate_windows breaks when test_start >= test_end (empty testing window).

    With train_size=1.0, non-anchored, each window's testing period collapses to
    zero length (test_start == test_end), triggering the early break. The result
    is zero windows and a None combined result.
    """
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=60),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=3,
        train_size=1.0,
        anchored=False,
        optimizer="grid",
        verbose=False,
    )

    result = optimizer.run()
    assert result.windows == []
    assert result.combined_test_result is None


def test_convert_to_native():
    """Test _convert_to_native converts numpy/dict/list to native types."""
    from quant_trading.optimization.bayesian import _convert_to_native

    assert _convert_to_native(np.float64(1.5)) == 1.5
    assert _convert_to_native(np.array([1, 2, 3])) == [1, 2, 3]
    assert _convert_to_native([np.int64(1), np.float64(2.0)]) == [1, 2.0]
    assert _convert_to_native({"a": np.float64(3.0)}) == {"a": 3.0}
    assert _convert_to_native("scalar") == "scalar"


def test_bayesian_optimizer_import_error(monkeypatch):
    """Test BayesianOptimizer raises ImportError when scikit-optimize is missing."""
    import sys

    monkeypatch.setitem(sys.modules, "skopt", None)
    monkeypatch.setitem(sys.modules, "skopt.utils", None)
    with pytest.raises(ImportError, match="requires scikit-optimize"):
        BayesianOptimizer(
            strategy_cls=MovingAverageCrossover,
            param_grid=ParameterGrid(),
            objective=maximize_sharpe,
            symbols=["AAPL"],
            start=datetime(2026, 1, 15) - timedelta(days=10),
            end=datetime(2026, 1, 15),
            initial_capital=100000.0,
            data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
        )


@skip_if_no_skopt
def test_bayesian_optimizer_default_objective():
    """Test BayesianOptimizer defaults to maximize_sharpe when objective is None."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=None,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=2,
        n_calls=3,
        random_state=42,
        verbose=False,
    )
    assert optimizer.objective is maximize_sharpe


@skip_if_no_skopt
def test_bayesian_optimizer_log_prior():
    """Test BayesianOptimizer builds a log-uniform Real space for log distribution."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("scale", min_val=0.1, max_val=10.0, distribution="log"))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=2,
        n_calls=3,
        random_state=42,
        verbose=False,
    )
    # The log-distributed float space should produce a Real with log-uniform prior
    space = optimizer._space
    assert len(space) == 2
    scale_dim = next(d for d in space if d.name == "scale")
    assert scale_dim.prior == "log-uniform"


@skip_if_no_skopt
def test_bayesian_optimizer_verbose(capsys):
    """Test BayesianOptimizer verbose prints progress."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=1,
        n_calls=2,
        random_state=42,
        verbose=True,
    )

    optimizer.run()
    out = capsys.readouterr().out
    assert "BayesianOptimizer:" in out
    assert "BayesianOptimizer complete" in out


@skip_if_no_skopt
def test_bayesian_optimizer_error_handling(monkeypatch, capsys):
    """Test BayesianOptimizer handles errors from the optimizer gracefully."""
    import skopt

    def raise_error(*args, **kwargs):
        raise ValueError("simulated skopt failure")

    monkeypatch.setattr(skopt, "gp_minimize", raise_error)

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=1,
        n_calls=2,
        random_state=42,
        verbose=True,
    )

    result = optimizer.run()
    out = capsys.readouterr().out
    assert "Bayesian optimization error" in out
    assert result.best_score == float("-inf")
    assert result.best_params == {}


def test_walk_forward_result_to_dataframe_without_best_params():
    """WalkForwardResult.to_dataframe skips the param update when a window has no
    best_params (the `if w.best_params` False branch, 64->66)."""
    from quant_trading.optimization.walk_forward import WalkForwardResult, WalkForwardWindow

    window = WalkForwardWindow(
        train_start=datetime(2024, 1, 1),
        train_end=datetime(2024, 2, 1),
        test_start=datetime(2024, 2, 1),
        test_end=datetime(2024, 3, 1),
        best_params=None,
    )
    result = WalkForwardResult(windows=[window])
    df = result.to_dataframe()
    assert "window" in df.columns
    assert not any(c.startswith("param_") for c in df.columns)


def test_walk_forward_window_to_dict():
    """WalkForwardWindow.to_dict returns every field as JSON-safe values.

    The four date boundaries are serialized as ISO-8601 strings (consistent
    with every other ``to_dict`` in the codebase), so the result can be passed
    straight to ``json.dumps`` without a ``default`` hook.
    """
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    window = WalkForwardWindow(
        train_start=datetime(2024, 1, 1),
        train_end=datetime(2024, 2, 1),
        test_start=datetime(2024, 2, 1),
        test_end=datetime(2024, 3, 1),
        best_params={"fast_period": 5},
        train_result=None,
        test_result=None,
    )
    result = window.to_dict()
    assert result == {
        "train_start": "2024-01-01T00:00:00",
        "train_end": "2024-02-01T00:00:00",
        "test_start": "2024-02-01T00:00:00",
        "test_end": "2024-03-01T00:00:00",
        "best_params": {"fast_period": 5},
        "train_result": None,
        "test_result": None,
    }
    # The serialized form must be JSON-safe (no raw datetime objects).
    import json

    json.dumps(result)


def test_walk_forward_with_failing_strategy_skips_test():
    """When every window's optimization yields an empty best_params dict (the
    strategy raises during backtesting), the test backtest is skipped for every
    window (the `if window.best_params` False branch, 299->279)."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=100)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20], param_type=int))

    optimizer = WalkForwardOptimizer(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=90),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=2,
        train_size=0.5,
        verbose=False,
    )

    result = optimizer.run()
    assert len(result.windows) == 2
    for window in result.windows:
        assert window.best_params == {}
        assert window.test_result is None


def test_walk_forward_risk_free_rate_reaches_combined_metrics():
    """The configured risk-free rate must reach the combined test result's metrics.

    Regression test: the combined walk-forward result previously hardcoded
    ``risk_free_rate=0.02`` regardless of the configured value.
    """
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.optimization.walk_forward import WalkForwardWindow

    start_dt = datetime(2024, 1, 1)
    # Use equity curves with enough up/down moves that both Sharpe and
    # Sortino have non-zero denominators (a single downside bar yields 0.0).
    eq1 = pd.Series(
        [100000.0, 105000.0, 102000.0, 108000.0, 104000.0, 110000.0, 105000.0],
        index=pd.to_datetime(
            [
                "2024-02-01",
                "2024-02-06",
                "2024-02-11",
                "2024-02-16",
                "2024-02-21",
                "2024-02-26",
                "2024-03-01",
            ]
        ),
    )
    eq2 = pd.Series(
        [100000.0, 95000.0, 97000.0, 93000.0, 96000.0, 92000.0, 95000.0],
        index=pd.to_datetime(
            [
                "2024-03-01",
                "2024-03-06",
                "2024-03-11",
                "2024-03-16",
                "2024-03-21",
                "2024-03-26",
                "2024-04-01",
            ]
        ),
    )

    def build_optimizer(risk_free_rate: float) -> WalkForwardOptimizer:
        return WalkForwardOptimizer(
            strategy_cls=MovingAverageCrossover,
            param_grid=ParameterGrid(),
            objective=maximize_sharpe,
            symbols=["AAPL"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 4, 1),
            initial_capital=100000.0,
            risk_free_rate=risk_free_rate,
            data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 200)})]),  # type: ignore[list-item]
        )

    optimizer_default = build_optimizer(0.02)
    optimizer_high = build_optimizer(0.10)

    def make_windows(optimizer: WalkForwardOptimizer) -> list[WalkForwardWindow]:
        m1 = calculate_backtest_metrics(eq1)
        m2 = calculate_backtest_metrics(eq2)
        return [
            WalkForwardWindow(
                train_start=start_dt,
                train_end=datetime(2024, 2, 1),
                test_start=datetime(2024, 2, 1),
                test_end=datetime(2024, 3, 1),
                best_params={"fast_period": 5, "slow_period": 20},
                test_result=BacktestResult(
                    equity_curve=eq1,
                    trades=pd.DataFrame(),
                    positions={},
                    metrics=m1,
                    start_date=datetime(2024, 2, 1),
                    end_date=datetime(2024, 3, 1),
                    initial_capital=100000.0,
                    final_value=eq1.iloc[-1],
                    total_return=eq1.iloc[-1] - 100000.0,
                    total_return_pct=(eq1.iloc[-1] / 100000.0 - 1) * 100,
                ),
            ),
            WalkForwardWindow(
                train_start=start_dt,
                train_end=datetime(2024, 3, 1),
                test_start=datetime(2024, 3, 1),
                test_end=datetime(2024, 4, 1),
                best_params={"fast_period": 5, "slow_period": 20},
                test_result=BacktestResult(
                    equity_curve=eq2,
                    trades=pd.DataFrame(),
                    positions={},
                    metrics=m2,
                    start_date=datetime(2024, 3, 1),
                    end_date=datetime(2024, 4, 1),
                    initial_capital=100000.0,
                    final_value=eq2.iloc[-1],
                    total_return=eq2.iloc[-1] - 100000.0,
                    total_return_pct=(eq2.iloc[-1] / 100000.0 - 1) * 100,
                ),
            ),
        ]

    combined_default = optimizer_default._combine_test_results(make_windows(optimizer_default))
    combined_high = optimizer_high._combine_test_results(make_windows(optimizer_high))

    assert combined_default is not None
    assert combined_high is not None
    assert combined_default.metrics.sharpe_ratio != 0.0
    assert combined_default.metrics.sortino_ratio != 0.0
    assert combined_high.metrics.sharpe_ratio != pytest.approx(
        combined_default.metrics.sharpe_ratio
    )
    assert combined_high.metrics.sortino_ratio != pytest.approx(
        combined_default.metrics.sortino_ratio
    )


@skip_if_no_skopt
def test_bayesian_optimizer_error_handling_quiet(monkeypatch):
    """When skopt fails and verbose is False, the except branch runs without
    printing (the `if self.verbose` False branch, 206->209)."""
    import skopt

    def raise_error(*args, **kwargs):
        raise RuntimeError("simulated skopt failure")

    monkeypatch.setattr(skopt, "gp_minimize", raise_error)

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10]))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30]))

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=1,
        n_calls=2,
        random_state=42,
        verbose=False,
    )

    result = optimizer.run()
    assert result.best_score == float("-inf")
    assert result.best_params == {}


@skip_if_no_skopt
def test_bayesian_create_skopt_space_min_val_without_max():
    """A parameter space with min_val set but max_val None is skipped in
    _create_skopt_space (the `elif` fall-through, 119->115)."""
    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("slow", min_val=20, param_type=int))  # no max_val

    optimizer = BayesianOptimizer(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=["AAPL"],
        start=datetime(2026, 1, 15) - timedelta(days=10),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )

    space = optimizer._create_skopt_space()
    assert space == []


@skip_if_no_yfinance
def test_grid_search_parallel_verbose(capsys):
    """Test GridSearch parallel path prints progress and 'New best'."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=True,
        n_jobs=2,
    )

    result = optimizer.run()
    out = capsys.readouterr().out
    assert "GridSearch: Evaluating" in out
    assert "New best" in out
    assert "GridSearch complete" in out
    assert result.best_params is not None
    assert len(result.all_results) == 4


@skip_if_no_yfinance
def test_grid_search_parallel_error_handling(capsys):
    """Test GridSearch parallel path catches worker errors and prints them."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=True,
        n_jobs=2,
    )

    result = optimizer.run()
    out = capsys.readouterr().out
    assert "-> Error:" in out
    assert result.best_score == float("-inf")
    assert result.best_params == {}
    assert len(result.all_results) == 4


@skip_if_no_yfinance
def test_random_search_parallel_verbose(capsys):
    """Test RandomSearch parallel path prints progress and 'New best'."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=True,
        n_jobs=2,
        n_iter=4,
        random_state=42,
    )

    result = optimizer.run()
    out = capsys.readouterr().out
    assert "RandomSearch: Evaluating" in out
    assert "New best" in out
    assert "RandomSearch complete" in out
    assert result.best_params is not None
    assert len(result.all_results) == 4


@skip_if_no_yfinance
def test_random_search_parallel_error_handling(capsys):
    """Test RandomSearch parallel path catches worker errors and prints them."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=True,
        n_jobs=2,
        n_iter=4,
        random_state=42,
    )

    result = optimizer.run()
    out = capsys.readouterr().out
    assert "-> Error:" in out
    assert result.best_score == float("-inf")
    assert result.best_params == {}
    assert len(result.all_results) == 4


@skip_if_no_yfinance
def test_grid_search_parallel_error_handling_quiet():
    """Test GridSearch parallel path catches worker errors silently (verbose=False)."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
        n_jobs=2,
    )

    result = optimizer.run()
    assert result.best_score == float("-inf")
    assert result.best_params == {}
    assert len(result.all_results) == 4


def test_grid_search_parallel_with_config():
    """Test GridSearch parallel path unwraps a Config into its DataConfig (line 173)."""
    from quant_trading.config.settings import Config, DataConfig

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        config=Config(
            data=DataConfig(
                offline=True,
                provider="synthetic",
                synthetic_seed=42,
                synthetic_days=60,
            )
        ),
        verbose=False,
        n_jobs=2,
    )

    result = optimizer.run()
    assert result.best_params is not None
    assert len(result.all_results) == 4


@skip_if_no_yfinance
def test_random_search_parallel_error_handling_quiet():
    """Test RandomSearch parallel path catches worker errors silently (verbose=False)."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=RaisingStrategy,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
        n_jobs=2,
        n_iter=4,
        random_state=42,
    )

    result = optimizer.run()
    assert result.best_score == float("-inf")
    assert result.best_params == {}
    assert len(result.all_results) == 4


def test_random_search_parallel_with_config():
    """Test RandomSearch parallel path unwraps a Config into its DataConfig (line 185)."""
    from quant_trading.config.settings import Config, DataConfig

    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        config=Config(
            data=DataConfig(
                offline=True,
                provider="synthetic",
                synthetic_seed=42,
                synthetic_days=60,
            )
        ),
        verbose=False,
        n_jobs=2,
        n_iter=4,
        random_state=42,
    )

    result = optimizer.run()
    assert result.best_params is not None
    assert len(result.all_results) == 4


def test_evaluate_params_worker_grid():
    """Test grid_search._evaluate_params_worker with offline DataConfig (lines 30-62)."""
    from quant_trading.config.settings import DataConfig
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    data_config = DataConfig(offline=True, synthetic_seed=42, synthetic_days=60)
    params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert params == {"fast_period": 5, "slow_period": 20}
    assert result is not None
    assert result.metrics is not None


@patch("quant_trading.backtest.engine.get_default_data_manager")
def test_evaluate_params_worker_grid_none_config(mock_get_default):
    """Test grid_search._evaluate_params_worker with data_config=None (line 39 False branch)."""
    from quant_trading.data.providers import DataManager
    from quant_trading.data.synthetic import create_synthetic_provider
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    mock_get_default.return_value = DataManager(
        [create_synthetic_provider(["AAPL"], days=60, seed=42)]
    )

    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        None,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


def test_evaluate_params_worker_grid_config_branch():
    """Test grid_search._evaluate_params_worker with a Config instance (line 40-41 branch)."""
    from quant_trading.config.settings import Config, DataConfig
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    config = Config(
        data=DataConfig(
            offline=True,
            provider="synthetic",
            synthetic_seed=42,
            synthetic_days=60,
        )
    )
    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


def test_evaluate_params_worker_grid_fallthrough_branch():
    """Test grid_search._evaluate_params_worker with an unrecognized config object (fall-through branch)."""
    from types import SimpleNamespace

    from quant_trading.optimization.grid_search import _evaluate_params_worker

    data_config = SimpleNamespace(
        offline=True,
        provider="synthetic",
        synthetic_days=60,
        synthetic_seed=42,
    )
    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


@skip_if_no_yfinance
def test_evaluate_params_worker_grid_error():
    """Test grid_search._evaluate_params_worker propagates worker errors."""
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    with pytest.raises(ValueError, match="boom"):
        _evaluate_params_worker(
            RaisingStrategy,
            {},
            maximize_sharpe,
            ["AAPL"],
            datetime(2026, 1, 15) - timedelta(days=50),
            datetime(2026, 1, 15),
            100000.0,
            0.001,
            0.0005,
            "1d",
            None,
            {"fast_period": 5, "slow_period": 20},
        )


def test_evaluate_params_worker_random():
    """Test random_search._evaluate_params_worker with offline DataConfig (lines 32-64)."""
    from quant_trading.config.settings import DataConfig
    from quant_trading.optimization.random_search import _evaluate_params_worker

    data_config = DataConfig(offline=True, synthetic_seed=42, synthetic_days=60)
    params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert params == {"fast_period": 5, "slow_period": 20}
    assert result is not None


@patch("quant_trading.backtest.engine.get_default_data_manager")
def test_evaluate_params_worker_random_none_config(mock_get_default):
    """Test random_search._evaluate_params_worker with data_config=None (line 41 False branch)."""
    from quant_trading.data.providers import DataManager
    from quant_trading.data.synthetic import create_synthetic_provider
    from quant_trading.optimization.random_search import _evaluate_params_worker

    mock_get_default.return_value = DataManager(
        [create_synthetic_provider(["AAPL"], days=60, seed=42)]
    )

    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        None,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


def test_evaluate_params_worker_random_config_branch():
    """Test random_search._evaluate_params_worker with a Config instance (line 42-43 branch)."""
    from quant_trading.config.settings import Config, DataConfig
    from quant_trading.optimization.random_search import _evaluate_params_worker

    config = Config(
        data=DataConfig(
            offline=True,
            provider="synthetic",
            synthetic_seed=42,
            synthetic_days=60,
        )
    )
    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


def test_evaluate_params_worker_random_fallthrough_branch():
    """Test random_search._evaluate_params_worker with an unrecognized config object (fall-through branch)."""
    from types import SimpleNamespace

    from quant_trading.optimization.random_search import _evaluate_params_worker

    data_config = SimpleNamespace(
        offline=True,
        provider="synthetic",
        synthetic_days=60,
        synthetic_seed=42,
    )
    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime(2026, 1, 15) - timedelta(days=50),
        datetime(2026, 1, 15),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


@skip_if_no_yfinance
def test_evaluate_params_worker_random_error():
    """Test random_search._evaluate_params_worker propagates worker errors."""
    from quant_trading.optimization.random_search import _evaluate_params_worker

    with pytest.raises(ValueError, match="boom"):
        _evaluate_params_worker(
            RaisingStrategy,
            {},
            maximize_sharpe,
            ["AAPL"],
            datetime(2026, 1, 15) - timedelta(days=50),
            datetime(2026, 1, 15),
            100000.0,
            0.001,
            0.0005,
            "1d",
            None,
            {"fast_period": 5, "slow_period": 20},
        )


@skip_if_no_yfinance
def test_grid_search_parallel():
    """Test GridSearch optimization with parallel execution."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
        n_jobs=2,
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


class _WorkerDeathExecutor(ProcessPoolExecutor):
    """Executor whose workers die before running any task."""

    def submit(self, fn, *args, **kwargs):
        future = _base.Future()
        future.set_exception(BrokenProcessPool("worker died"))
        return future


class _PartialWorkerDeathExecutor(ProcessPoolExecutor):
    """Executor whose first task succeeds but whose workers then die."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._submitted = 0

    def submit(self, fn, *args, **kwargs):
        self._submitted += 1
        if self._submitted == 1:
            return super().submit(fn, *args, **kwargs)
        future = _base.Future()
        future.set_exception(BrokenProcessPool("worker died"))
        return future


def _make_parallel_optimizer(cls, n_iter=None, verbose=True):
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", values=[5, 10], param_type=int))
    param_grid.add(ParameterSpace("slow_period", values=[20, 30], param_type=int))

    kwargs = {}
    if n_iter is not None:
        kwargs["n_iter"] = n_iter
    kwargs["verbose"] = verbose

    return cls(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_jobs=2,
        **kwargs,
    )


@skip_if_no_yfinance
def test_random_search_parallel():
    """Test RandomSearch optimization with parallel execution."""
    symbols = ["AAPL"]
    mock_data = {"AAPL": create_test_data("AAPL", days=60)}
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    param_grid = ParameterGrid()
    param_grid.add(ParameterSpace("fast_period", min_val=5, max_val=15, param_type=int))
    param_grid.add(ParameterSpace("slow_period", min_val=20, max_val=30, param_type=int))

    optimizer = RandomSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=datetime(2026, 1, 15) - timedelta(days=50),
        end=datetime(2026, 1, 15),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
        n_jobs=2,
        n_iter=4,  # Ensure we have a fixed number of iterations
    )

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


def test_grid_search_parallel_worker_death_fallback(monkeypatch):
    """Test GridSearch falls back to sequential execution when all workers die."""
    import quant_trading.optimization.grid_search as grid_search_module

    optimizer = _make_parallel_optimizer(GridSearch)
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", _WorkerDeathExecutor)

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


def test_random_search_parallel_worker_death_fallback(monkeypatch):
    """Test RandomSearch falls back to sequential execution when all workers die."""
    import quant_trading.optimization.random_search as random_search_module

    optimizer = _make_parallel_optimizer(RandomSearch, n_iter=4)
    monkeypatch.setattr(random_search_module, "ProcessPoolExecutor", _WorkerDeathExecutor)

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


@skip_if_no_yfinance
def test_grid_search_parallel_partial_worker_death_fallback(monkeypatch):
    """Test GridSearch mixes successful parallel results with sequential retries."""
    import quant_trading.optimization.grid_search as grid_search_module

    optimizer = _make_parallel_optimizer(GridSearch)
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", _PartialWorkerDeathExecutor)

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


class _WorkerErrorExecutor(ProcessPoolExecutor):
    """Executor whose workers raise a regular error instead of dying."""

    def submit(self, fn, *args, **kwargs):
        future = _base.Future()
        future.set_exception(ValueError("worker error"))
        return future


def _raise_broken_as_completed(fs, *args, **kwargs):
    raise BrokenProcessPool("as_completed failed")


def test_grid_search_parallel_worker_error(monkeypatch, capsys):
    """Test GridSearch records worker errors (non-fatal) for every combination."""
    import quant_trading.optimization.grid_search as grid_search_module

    optimizer = _make_parallel_optimizer(GridSearch)
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", _WorkerErrorExecutor)

    result = optimizer.run()
    out = capsys.readouterr().out

    assert result.best_params == {}
    assert result.best_score == float("-inf")
    assert len(result.all_results) == 4
    assert "-> Error:" in out


def test_random_search_parallel_worker_error(monkeypatch, capsys):
    """Test RandomSearch records worker errors (non-fatal) for every combination."""
    import quant_trading.optimization.random_search as random_search_module

    optimizer = _make_parallel_optimizer(RandomSearch, n_iter=4)
    monkeypatch.setattr(random_search_module, "ProcessPoolExecutor", _WorkerErrorExecutor)

    result = optimizer.run()
    out = capsys.readouterr().out

    assert result.best_params == {}
    assert result.best_score == float("-inf")
    assert len(result.all_results) == 4
    assert "-> Error:" in out


def test_grid_search_parallel_as_completed_broken(monkeypatch):
    """Test GridSearch falls back sequentially when as_completed itself fails."""
    import quant_trading.optimization.grid_search as grid_search_module

    optimizer = _make_parallel_optimizer(GridSearch)
    monkeypatch.setattr(grid_search_module, "as_completed", _raise_broken_as_completed)

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


def test_random_search_parallel_as_completed_broken(monkeypatch):
    """Test RandomSearch falls back sequentially when as_completed itself fails."""
    import quant_trading.optimization.random_search as random_search_module

    optimizer = _make_parallel_optimizer(RandomSearch, n_iter=4)
    monkeypatch.setattr(random_search_module, "as_completed", _raise_broken_as_completed)

    result = optimizer.run()

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4


def _make_scripted_result(params, score=1.0):
    return (
        params,
        score,
        SimpleNamespace(
            total_return_pct=10.0,
            metrics=SimpleNamespace(
                sharpe_ratio=1.0,
                max_drawdown_pct=2.0,
                win_rate=0.5,
                profit_factor=1.5,
                num_trades=3,
            ),
        ),
    )


class _ScriptedExecutor:
    """Executor substitute that returns pre-scripted futures without a pool."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self._calls = 0

    def submit(self, fn, *args, **kwargs):
        kind, value = self._scripts[self._calls]
        self._calls += 1
        future = _base.Future()
        if kind == "result":
            future.set_result(value)
        else:
            future.set_exception(value)
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _scripted_results(params_list, scripts):
    """Zip params with scripts into (kind, value) pairs for the scripted executor."""
    results = []
    for params, script in zip(params_list, scripts):
        if script[0] == "result":
            score = script[2] if len(script) > 2 else 1.0
            results.append(("result", _make_scripted_result(params, score)))
        else:
            results.append(script)
    return results


def test_grid_search_parallel_scripted(monkeypatch):
    """Test GridSearch mixes parallel successes, worker errors, and worker deaths."""
    import quant_trading.optimization.grid_search as grid_search_module

    params_list = [
        {"fast_period": 5, "slow_period": 20},
        {"fast_period": 5, "slow_period": 30},
        {"fast_period": 10, "slow_period": 20},
        {"fast_period": 10, "slow_period": 30},
    ]
    scripts = [
        ("result", None, 1.0),
        ("error", ValueError("boom")),
        ("error", BrokenProcessPool("worker died")),
        ("result", None, 2.0),
    ]
    executor = _ScriptedExecutor(_scripted_results(params_list, scripts))
    optimizer = _make_parallel_optimizer(GridSearch)
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", lambda *a, **k: executor)
    monkeypatch.setattr(grid_search_module, "as_completed", lambda fs, *a, **k: list(fs))

    result = optimizer.run()

    assert result.best_params == {"fast_period": 10, "slow_period": 30}
    assert result.best_score == 2.0
    assert len(result.all_results) == 4


def test_grid_search_parallel_scripted_quiet(monkeypatch):
    """Test GridSearch parallel/error paths with verbose=False."""
    import quant_trading.optimization.grid_search as grid_search_module

    params_list = [
        {"fast_period": 5, "slow_period": 20},
        {"fast_period": 5, "slow_period": 30},
        {"fast_period": 10, "slow_period": 20},
        {"fast_period": 10, "slow_period": 30},
    ]
    scripts = [
        ("result", None, 1.0),
        ("error", ValueError("boom")),
        ("result", None, 3.0),
        ("error", ValueError("boom")),
    ]
    executor = _ScriptedExecutor(_scripted_results(params_list, scripts))
    optimizer = _make_parallel_optimizer(GridSearch, verbose=False)
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", lambda *a, **k: executor)
    monkeypatch.setattr(grid_search_module, "as_completed", lambda fs, *a, **k: list(fs))

    result = optimizer.run()

    assert result.best_params == {"fast_period": 10, "slow_period": 20}
    assert result.best_score == 3.0
    assert len(result.all_results) == 4


def test_random_search_parallel_scripted(monkeypatch):
    """Test RandomSearch mixes parallel successes, worker errors, and worker deaths."""
    import quant_trading.optimization.random_search as random_search_module

    params_list = [
        {"fast_period": 5, "slow_period": 20},
        {"fast_period": 5, "slow_period": 30},
        {"fast_period": 10, "slow_period": 20},
        {"fast_period": 10, "slow_period": 30},
    ]
    scripts = [
        ("result", None, 1.0),
        ("error", ValueError("boom")),
        ("error", BrokenProcessPool("worker died")),
        ("result", None, 2.0),
    ]
    executor = _ScriptedExecutor(_scripted_results(params_list, scripts))
    optimizer = _make_parallel_optimizer(RandomSearch, n_iter=4)
    monkeypatch.setattr(random_search_module, "ProcessPoolExecutor", lambda *a, **k: executor)
    monkeypatch.setattr(random_search_module, "as_completed", lambda fs, *a, **k: list(fs))

    result = optimizer.run()

    assert result.best_params == {"fast_period": 10, "slow_period": 30}
    assert result.best_score == 2.0
    assert len(result.all_results) == 4


def test_random_search_parallel_scripted_quiet(monkeypatch):
    """Test RandomSearch parallel/error paths with verbose=False."""
    import quant_trading.optimization.random_search as random_search_module

    params_list = [
        {"fast_period": 5, "slow_period": 20},
        {"fast_period": 10, "slow_period": 30},
    ]
    scripts = [("result", None, 1.0), ("error", ValueError("boom"))]
    executor = _ScriptedExecutor(_scripted_results(params_list, scripts))
    optimizer = _make_parallel_optimizer(RandomSearch, n_iter=2, verbose=False)
    monkeypatch.setattr(random_search_module, "ProcessPoolExecutor", lambda *a, **k: executor)
    monkeypatch.setattr(random_search_module, "as_completed", lambda fs, *a, **k: list(fs))

    result = optimizer.run()

    assert result.best_params == {"fast_period": 5, "slow_period": 20}
    assert len(result.all_results) == 2


def test_grid_search_parallel_worker_death_fallback_quiet(monkeypatch, capsys):
    """Test GridSearch silent fallback when all workers die (verbose=False).

    Exercises the verbose=False branches inside the BrokenProcessPool
    handler and the sequential retry loop.
    """
    import quant_trading.optimization.grid_search as grid_search_module

    optimizer = _make_parallel_optimizer(GridSearch, verbose=False)
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", _WorkerDeathExecutor)

    result = optimizer.run()
    out = capsys.readouterr().out

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4
    assert out == ""  # No output expected in quiet mode


def test_random_search_parallel_worker_death_fallback_quiet(monkeypatch, capsys):
    """Test RandomSearch silent fallback when all workers die (verbose=False).

    Exercises the verbose=False branches inside the BrokenProcessPool
    handler and the sequential retry loop.
    """
    import quant_trading.optimization.random_search as random_search_module

    optimizer = _make_parallel_optimizer(RandomSearch, n_iter=4, verbose=False)
    monkeypatch.setattr(random_search_module, "ProcessPoolExecutor", _WorkerDeathExecutor)

    result = optimizer.run()
    out = capsys.readouterr().out

    assert result.best_params is not None
    assert "fast_period" in result.best_params
    assert "slow_period" in result.best_params
    assert result.best_score != float("-inf")
    assert len(result.all_results) == 4
    assert out == ""  # No output expected in quiet mode


class TestWalkForwardSerialization:
    """Round-trip tests for WalkForwardWindow.to_dict / from_dict and
    WalkForwardResult.to_dict / from_dict.

    Commit ``8502777`` added the ``from_dict`` classmethods alongside the
    existing ``to_dict`` methods but shipped no tests for them. These tests
    guard the round trip so a future change to either direction is caught.
    """

    def test_walk_forward_window_round_trip(self):
        """from_dict(to_dict(window)) restores every field, including datetimes."""
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5, "slow_period": 20},
        )
        restored = WalkForwardWindow.from_dict(window.to_dict())

        assert restored.train_start == datetime(2024, 1, 1)
        assert restored.train_end == datetime(2024, 2, 1)
        assert restored.test_start == datetime(2024, 2, 1)
        assert restored.test_end == datetime(2024, 3, 1)
        assert restored.best_params == {"fast_period": 5, "slow_period": 20}

    def test_walk_forward_window_round_trip_with_string_datetimes(self):
        """from_dict accepts ISO-8601 strings, as JSON round-trips would emit.

        ``to_dict`` keeps the raw ``datetime`` objects rather than serializing
        them, so a consumer that round-trips through JSON (which emits ISO
        strings) must be handled by ``from_dict`` as well.
        """
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
        )
        data = {
            "train_start": window.train_start.isoformat(),
            "train_end": window.train_end.isoformat(),
            "test_start": window.test_start.isoformat(),
            "test_end": window.test_end.isoformat(),
            "best_params": None,
        }
        restored = WalkForwardWindow.from_dict(data)

        assert restored.train_start == datetime(2024, 1, 1)
        assert restored.test_end == datetime(2024, 3, 1)
        assert restored.best_params is None

    def test_walk_forward_window_from_dict_defaults_missing_fields(self):
        """from_dict tolerates a dict that omits optional fields."""
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        restored = WalkForwardWindow.from_dict(
            {
                "train_start": datetime(2024, 1, 1),
                "train_end": datetime(2024, 2, 1),
                "test_start": datetime(2024, 2, 1),
                "test_end": datetime(2024, 3, 1),
            }
        )
        assert restored.best_params is None
        assert restored.train_result is None
        assert restored.test_result is None

    def test_walk_forward_window_from_dict_passes_through_non_datetime_values(self):
        """from_dict passes non-datetime/non-string values through unchanged.

        ``_coerce_datetime`` only converts ``datetime`` and ``str`` inputs; any
        other value (including ``None`` from a missing key) is returned as-is so
        callers may apply their own defaults. This guards that passthrough.
        """
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        restored = WalkForwardWindow.from_dict(
            {
                "train_start": None,
                "train_end": None,
                "test_start": None,
                "test_end": None,
            }
        )
        assert restored.train_start is None
        assert restored.test_end is None

    def test_walk_forward_result_round_trip(self):
        """from_dict(to_dict(result)) restores windows and the anchored flag."""
        from quant_trading.optimization.walk_forward import (
            WalkForwardResult,
            WalkForwardWindow,
        )

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
            best_params={"fast_period": 5},
        )
        result = WalkForwardResult(windows=[window], combined_test_result=None, anchored=False)
        restored = WalkForwardResult.from_dict(result.to_dict())

        assert restored.anchored is False
        assert len(restored.windows) == 1
        assert restored.windows[0].train_start == datetime(2024, 1, 1)
        assert restored.windows[0].best_params == {"fast_period": 5}
        assert restored.combined_test_result is None

    def test_walk_forward_result_round_trip_empty(self):
        """from_dict(to_dict(result)) works for a result with no windows."""
        from quant_trading.optimization.walk_forward import WalkForwardResult

        result = WalkForwardResult(windows=[], combined_test_result=None, anchored=True)
        restored = WalkForwardResult.from_dict(result.to_dict())

        assert restored.windows == []
        assert restored.anchored is True
        assert restored.combined_test_result is None

    def test_walk_forward_result_from_dict_accepts_window_objects(self):
        """from_dict passes through WalkForwardWindow instances unchanged."""
        from quant_trading.optimization.walk_forward import (
            WalkForwardResult,
            WalkForwardWindow,
        )

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
        )
        restored = WalkForwardResult.from_dict({"windows": [window], "anchored": True})

        assert restored.windows[0] is window
        assert restored.anchored is True

    def test_walk_forward_result_from_dict_defaults_missing_fields(self):
        """from_dict tolerates a dict that omits optional fields."""
        from quant_trading.optimization.walk_forward import WalkForwardResult

        restored = WalkForwardResult.from_dict({})
        assert restored.windows == []
        assert restored.anchored is True
        assert restored.combined_test_result is None

    def test_walk_forward_result_from_dict_skips_non_window_entries(self):
        """from_dict ignores window entries that are neither dicts nor windows.

        A malformed ``windows`` list (e.g. one that round-tripped through a
        non-JSON serializer) must not raise; the bad entries are skipped and
        the valid ones are preserved.
        """
        from quant_trading.optimization.walk_forward import (
            WalkForwardResult,
            WalkForwardWindow,
        )

        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 3, 1),
        )
        restored = WalkForwardResult.from_dict(
            {"windows": ["not-a-window", window, 42], "anchored": False}
        )

        assert len(restored.windows) == 1
        assert restored.windows[0] is window
        assert restored.anchored is False


class TestOptimizationResultSerialization:
    """Round-trip tests for OptimizationResult.to_dict / from_dict.

    ``OptimizationResult`` shipped no ``to_dict``/``from_dict`` pair, so a
    consumer wanting to persist or transmit an optimization result through
    JSON had no supported path. These tests guard the round trip.
    """

    def test_to_dict_contains_all_fields(self):
        """to_dict exposes every OptimizationResult field."""
        start = datetime(2024, 1, 1, 9, 0, 0)
        end = datetime(2024, 1, 1, 10, 0, 0)
        result = OptimizationResult(
            best_params={"fast_period": 5},
            best_score=1.5,
            all_results=[{"params": {"fast_period": 5}, "score": 1.5}],
            start_time=start,
            end_time=end,
        )
        data = result.to_dict()

        assert data["best_params"] == {"fast_period": 5}
        assert data["best_score"] == 1.5
        assert data["all_results"] == [{"params": {"fast_period": 5}, "score": 1.5}]
        assert data["start_time"] == start.isoformat()
        assert data["end_time"] == end.isoformat()

    def test_to_dict_none_best_result(self):
        """to_dict emits None for best_result when absent."""
        result = OptimizationResult(best_params={"x": 1}, best_score=0.0)
        assert result.to_dict()["best_result"] is None

    def test_round_trip_restores_fields(self):
        """from_dict(to_dict(result)) restores every scalar field."""
        start = datetime(2024, 1, 1, 9, 0, 0)
        end = datetime(2024, 1, 1, 10, 0, 0)
        result = OptimizationResult(
            best_params={"fast_period": 5, "slow_period": 20},
            best_score=1.5,
            all_results=[{"params": {"fast_period": 5}, "score": 1.5}],
            start_time=start,
            end_time=end,
        )
        restored = OptimizationResult.from_dict(result.to_dict())

        assert restored.best_params == {"fast_period": 5, "slow_period": 20}
        assert restored.best_score == 1.5
        assert restored.all_results == [{"params": {"fast_period": 5}, "score": 1.5}]
        assert restored.start_time == start
        assert restored.end_time == end
        assert restored.duration_seconds == 3600.0

    def test_round_trip_json_safe(self):
        """to_dict output is JSON-serializable and from_dict accepts it."""
        result = OptimizationResult(
            best_params={"fast_period": 5},
            best_score=1.5,
            all_results=[{"params": {"fast_period": 5}, "score": 1.5}],
            start_time=datetime(2024, 1, 1, 9, 0, 0),
            end_time=datetime(2024, 1, 1, 10, 0, 0),
        )
        data = json.loads(json.dumps(result.to_dict()))
        restored = OptimizationResult.from_dict(data)

        assert restored.best_params == {"fast_period": 5}
        assert restored.best_score == 1.5
        assert restored.start_time == datetime(2024, 1, 1, 9, 0, 0)

    def test_from_dict_defaults_missing_fields(self):
        """from_dict tolerates a dict that omits optional fields."""
        restored = OptimizationResult.from_dict(
            {"best_params": {"x": 1}, "best_score": 0.5}
        )
        assert restored.best_params == {"x": 1}
        assert restored.best_score == 0.5
        assert restored.best_result is None
        assert restored.all_results == []
        assert restored.start_time is None
        assert restored.end_time is None
        assert restored.duration_seconds is None

    def test_from_dict_empty_dict(self):
        """from_dict({}) yields a fully-defaulted result."""
        restored = OptimizationResult.from_dict({})
        assert restored.best_params == {}
        assert restored.best_score == 0.0
        assert restored.best_result is None
        assert restored.all_results == []

    def test_from_dict_extra_keys_ignored(self):
        """from_dict ignores unknown keys."""
        restored = OptimizationResult.from_dict(
            {"best_params": {"x": 1}, "best_score": 0.5, "bogus": 99}
        )
        assert restored.best_params == {"x": 1}
        assert restored.best_score == 0.5

    def test_round_trip_with_best_result_dict(self):
        """A dict best_result is reconstructed via BacktestResult.from_dict."""
        result = OptimizationResult(
            best_params={"x": 1},
            best_score=0.5,
            all_results=[],
        )
        data = result.to_dict()
        data["best_result"] = {"total_return_pct": 5.0, "total_trades": 10}
        restored = OptimizationResult.from_dict(data)

        assert restored.best_result is not None
        assert restored.best_result.total_return_pct == 5.0
        assert restored.best_result.metrics.num_trades == 10

    def test_from_dict_passes_through_non_dict_best_result(self):
        """A non-dict best_result is passed through unchanged."""
        sentinel = object()
        restored = OptimizationResult.from_dict(
            {"best_params": {}, "best_score": 0.0, "best_result": sentinel}
        )
        assert restored.best_result is sentinel

    def test_round_trip_with_datetimes_as_strings(self):
        """from_dict accepts ISO-8601 strings, as JSON round-trips emit."""
        restored = OptimizationResult.from_dict(
            {
                "best_params": {"x": 1},
                "best_score": 0.5,
                "start_time": "2024-01-01T09:00:00",
                "end_time": "2024-01-01T10:00:00",
            }
        )
        assert restored.start_time == datetime(2024, 1, 1, 9, 0, 0)
        assert restored.end_time == datetime(2024, 1, 1, 10, 0, 0)

    def test_to_dict_copies_all_results(self):
        """to_dict copies all_results entries so mutations do not leak."""
        result = OptimizationResult(
            best_params={"x": 1},
            best_score=0.5,
            all_results=[{"params": {"x": 1}, "score": 0.5}],
        )
        data = result.to_dict()
        data["all_results"][0]["score"] = 999.0
        assert result.all_results[0]["score"] == 0.5


class TestBayesianOptimizerConfigSerialization:
    """Round-trip tests for BayesianOptimizerConfig.to_dict / from_dict.

    ``BayesianOptimizerConfig`` shipped no ``to_dict``/``from_dict`` pair, so a
    consumer wanting to persist a Bayesian optimizer setup (e.g. alongside an
    :class:`~quant_trading.optimization.OptimizationResult`) had no supported
    path. These tests guard the round trip.
    """

    def test_to_dict_contains_all_fields(self):
        """to_dict exposes every BayesianOptimizerConfig field."""
        cfg = BayesianOptimizerConfig(
            n_initial_points=5,
            n_calls=20,
            acq_func="PI",
            acq_optimizer="batch",
            random_state=42,
            noise=1e-5,
        )
        data = cfg.to_dict()

        assert data["n_initial_points"] == 5
        assert data["n_calls"] == 20
        assert data["acq_func"] == "PI"
        assert data["acq_optimizer"] == "batch"
        assert data["random_state"] == 42
        assert data["noise"] == 1e-5

    def test_to_dict_none_random_state(self):
        """to_dict emits None for random_state when absent."""
        cfg = BayesianOptimizerConfig()
        assert cfg.to_dict()["random_state"] is None

    def test_round_trip_restores_fields(self):
        """from_dict(to_dict(cfg)) restores every scalar field."""
        cfg = BayesianOptimizerConfig(
            n_initial_points=5,
            n_calls=20,
            acq_func="PI",
            acq_optimizer="batch",
            random_state=42,
            noise=1e-5,
        )
        restored = BayesianOptimizerConfig.from_dict(cfg.to_dict())

        assert restored.n_initial_points == 5
        assert restored.n_calls == 20
        assert restored.acq_func == "PI"
        assert restored.acq_optimizer == "batch"
        assert restored.random_state == 42
        assert restored.noise == 1e-5

    def test_round_trip_json_safe(self):
        """to_dict output is JSON-serializable and from_dict accepts it."""
        cfg = BayesianOptimizerConfig(n_calls=20, random_state=42, noise=1e-5)
        data = json.loads(json.dumps(cfg.to_dict()))
        restored = BayesianOptimizerConfig.from_dict(data)

        assert restored.n_calls == 20
        assert restored.random_state == 42
        assert restored.noise == 1e-5

    def test_from_dict_defaults_missing_fields(self):
        """from_dict tolerates a dict that omits optional fields."""
        restored = BayesianOptimizerConfig.from_dict({"n_calls": 20, "random_state": 42})
        assert restored.n_calls == 20
        assert restored.random_state == 42
        assert restored.n_initial_points == 10
        assert restored.acq_func == "EI"
        assert restored.acq_optimizer == "auto"
        assert restored.noise == 1e-6

    def test_from_dict_empty_dict(self):
        """from_dict({}) yields a fully-defaulted config."""
        restored = BayesianOptimizerConfig.from_dict({})
        assert restored.n_initial_points == 10
        assert restored.n_calls == 50
        assert restored.acq_func == "EI"
        assert restored.acq_optimizer == "auto"
        assert restored.random_state is None
        assert restored.noise == 1e-6

    def test_from_dict_extra_keys_ignored(self):
        """from_dict ignores unknown keys."""
        restored = BayesianOptimizerConfig.from_dict(
            {"n_calls": 20, "random_state": 42, "bogus": 99}
        )
        assert restored.n_calls == 20
        assert restored.random_state == 42

    def test_from_dict_random_state_none_explicit(self):
        """from_dict accepts an explicit None for random_state."""
        restored = BayesianOptimizerConfig.from_dict({"random_state": None})
        assert restored.random_state is None


@pytest.mark.skipif(not _HAS_SKOPT, reason="requires scikit-optimize")
class TestBayesianOptimizerNoise:
    """The ``noise`` field of :class:`BayesianOptimizerConfig` was defined,
    serialized, and round-tripped but never wired into :class:`BayesianOptimizer`
    itself: ``gp_minimize`` was called with a hardcoded ``noise=1e-6`` and the
    optimizer constructor rejected ``noise`` as an unexpected keyword
    argument. These tests guard the wiring so a configured noise value actually
    reaches the Gaussian Process kernel.
    """

    def _make_optimizer(self, **overrides):
        from quant_trading.data.synthetic import create_synthetic_provider

        provider = create_synthetic_provider(["AAPL"], days=60, seed=42)
        data_manager = DataManager([provider])
        param_grid = ParameterGrid()
        param_grid.add(ParameterSpace("fast_period", values=[5], param_type=int))
        param_grid.add(ParameterSpace("slow_period", values=[10], param_type=int))
        kwargs = {
            "strategy_cls": MovingAverageCrossover,
            "param_grid": param_grid,
            "objective": maximize_sharpe,
            "symbols": ["AAPL"],
            "start": datetime.now() - timedelta(days=50),
            "end": datetime.now(),
            "data_manager": data_manager,
            "random_state": 42,
            "n_initial_points": 2,
            "n_calls": 3,
        }
        kwargs.update(overrides)
        return BayesianOptimizer(**kwargs)

    def test_constructor_accepts_noise_kwarg(self):
        """BayesianOptimizer accepts a ``noise`` keyword argument."""
        optimizer = self._make_optimizer(noise=1e-3)
        assert optimizer.noise == 1e-3

    def test_default_noise_matches_config_default(self):
        """The optimizer's default noise mirrors BayesianOptimizerConfig."""
        optimizer = self._make_optimizer()
        assert optimizer.noise == BayesianOptimizerConfig().noise

    def test_configured_noise_reaches_gp_minimize(self, monkeypatch):
        """The configured ``noise`` value is forwarded to ``gp_minimize``.

        Regression test: previously ``gp_minimize`` was called with a hardcoded
        ``noise=1e-6`` regardless of the configured value, so a user setting
        ``noise=1e-3`` on the config had no effect.
        """
        captured: dict[str, Any] = {}

        def fake_gp_minimize(*args, **kwargs):
            captured.update(kwargs)
            # gp_minimize returns an OptimizeResult; the optimizer only reads
            # ``x``/``fun`` indirectly through the objective, so an empty stub
            # result is sufficient to let run() complete.
            return SimpleNamespace(
                x=[0],
                fun=0.0,
                x_iters=[[0]],
                fun_iters=[0.0],
                models=[],
            )

        # run() imports gp_minimize lazily via ``from skopt import gp_minimize``,
        # so patch the attribute on the skopt module namespace.
        import skopt

        monkeypatch.setattr(skopt, "gp_minimize", fake_gp_minimize)

        optimizer = self._make_optimizer(noise=1e-3)
        optimizer.run()

        assert captured.get("noise") == 1e-3, (
            f"gp_minimize received noise={captured.get('noise')!r}, "
            "expected the configured 1e-3"
        )

    def test_default_noise_reaches_gp_minimize(self, monkeypatch):
        """When unset, the optimizer's default noise is forwarded."""
        captured: dict[str, Any] = {}

        def fake_gp_minimize(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                x=[0],
                fun=0.0,
                x_iters=[[0]],
                fun_iters=[0.0],
                models=[],
            )

        import skopt

        monkeypatch.setattr(skopt, "gp_minimize", fake_gp_minimize)

        optimizer = self._make_optimizer()
        optimizer.run()

        assert captured.get("noise") == optimizer.noise == BayesianOptimizerConfig().noise


class TestBaseOptimizationUtilities:
    """Tests for internal utility functions in optimization.base."""

    def test_coerce_datetime_with_datetime(self):
        """_coerce_datetime returns datetime objects unchanged."""
        from quant_trading.optimization.base import _coerce_datetime

        dt = datetime(2024, 1, 1, 9, 0, 0)
        result = _coerce_datetime(dt)
        assert result is dt

    def test_coerce_datetime_with_string(self):
        """_coerce_datetime parses ISO-8601 strings."""
        from quant_trading.optimization.base import _coerce_datetime

        result = _coerce_datetime("2024-01-01T09:00:00")
        assert result == datetime(2024, 1, 1, 9, 0, 0)

    def test_coerce_datetime_with_none(self):
        """_coerce_datetime returns None for None input."""
        from quant_trading.optimization.base import _coerce_datetime

        result = _coerce_datetime(None)
        assert result is None

    def test_coerce_datetime_with_other_type(self):
        """_coerce_datetime returns None for unsupported types."""
        from quant_trading.optimization.base import _coerce_datetime

        result = _coerce_datetime(123)
        assert result is None

        result = _coerce_datetime([])
        assert result is None

        result = _coerce_datetime({})
        assert result is None


class TestWalkForwardWindowRestoreResult:
    """Tests for the _restore_result helper in WalkForwardWindow.from_dict."""

    def test_restore_result_with_none(self):
        """_restore_result returns None for None input."""
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        # Access the private helper via from_dict with a known structure
        window = WalkForwardWindow.from_dict(
            {
                "train_start": datetime(2024, 1, 1),
                "train_end": datetime(2024, 2, 1),
                "test_start": datetime(2024, 2, 1),
                "test_end": datetime(2024, 3, 1),
                "train_result": None,
                "test_result": None,
            }
        )
        assert window.train_result is None
        assert window.test_result is None

    def test_restore_result_with_backtest_result_instance(self):
        """_restore_result passes BacktestResult instances through unchanged."""
        from quant_trading.backtest.engine import BacktestResult
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        br = BacktestResult(
            equity_curve=pd.Series([100000, 101000]),
            trades=pd.DataFrame(),
            positions={},
            metrics=None,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            initial_capital=100000.0,
            final_value=101000.0,
            total_return=1000.0,
            total_return_pct=1.0,
        )
        window = WalkForwardWindow.from_dict(
            {
                "train_start": datetime(2024, 1, 1),
                "train_end": datetime(2024, 2, 1),
                "test_start": datetime(2024, 2, 1),
                "test_end": datetime(2024, 3, 1),
                "train_result": br,
                "test_result": br,
            }
        )
        assert window.train_result is br
        assert window.test_result is br

    def test_restore_result_with_dict(self):
        """_restore_result reconstructs BacktestResult from dict."""
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        window = WalkForwardWindow.from_dict(
            {
                "train_start": datetime(2024, 1, 1),
                "train_end": datetime(2024, 2, 1),
                "test_start": datetime(2024, 2, 1),
                "test_end": datetime(2024, 3, 1),
                "train_result": {"total_return_pct": 5.0},
                "test_result": {"total_return_pct": 3.0},
            }
        )
        assert window.train_result is not None
        assert window.train_result.total_return_pct == 5.0
        assert window.test_result is not None
        assert window.test_result.total_return_pct == 3.0

    def test_restore_result_with_other_type(self):
        """_restore_result returns None for unsupported types."""
        from quant_trading.optimization.walk_forward import WalkForwardWindow

        window = WalkForwardWindow.from_dict(
            {
                "train_start": datetime(2024, 1, 1),
                "train_end": datetime(2024, 2, 1),
                "test_start": datetime(2024, 2, 1),
                "test_end": datetime(2024, 3, 1),
                "train_result": "not-a-dict",
                "test_result": 123,
            }
        )
        assert window.train_result is None
        assert window.test_result is None


class TestWalkForwardResultCombinedRestore:
    """Tests for combined_test_result restoration in WalkForwardResult.from_dict."""

    def test_combined_result_with_dict(self):
        """from_dict reconstructs combined_test_result from dict."""
        from quant_trading.optimization.walk_forward import WalkForwardResult

        result = WalkForwardResult.from_dict(
            {
                "windows": [],
                "combined_test_result": {"total_return_pct": 10.0},
                "anchored": True,
            }
        )
        assert result.combined_test_result is not None
        assert result.combined_test_result.total_return_pct == 10.0

    def test_combined_result_with_backtest_result_instance(self):
        """from_dict passes BacktestResult instance through unchanged."""
        from quant_trading.backtest.engine import BacktestResult
        from quant_trading.optimization.walk_forward import WalkForwardResult

        br = BacktestResult(
            equity_curve=pd.Series([100000, 101000]),
            trades=pd.DataFrame(),
            positions={},
            metrics=None,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            initial_capital=100000.0,
            final_value=101000.0,
            total_return=1000.0,
            total_return_pct=1.0,
        )
        result = WalkForwardResult.from_dict(
            {
                "windows": [],
                "combined_test_result": br,
                "anchored": True,
            }
        )
        assert result.combined_test_result is br

    def test_combined_result_with_other_type(self):
        """from_dict sets combined_test_result to None for unsupported types."""
        from quant_trading.optimization.walk_forward import WalkForwardResult

        result = WalkForwardResult.from_dict(
            {
                "windows": [],
                "combined_test_result": "not-a-dict",
                "anchored": True,
            }
        )
        assert result.combined_test_result is None

        result = WalkForwardResult.from_dict(
            {
                "windows": [],
                "combined_test_result": 123,
                "anchored": True,
            }
        )
        assert result.combined_test_result is None
