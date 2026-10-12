"""Tests for the optimization module."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from quant_trading.data.providers import DataManager
from quant_trading.optimization import (
    BayesianOptimizer,
    GridSearch,
    ParameterGrid,
    ParameterSpace,
    RandomSearch,
    WalkForwardOptimizer,
    maximize_calmar,
    maximize_profit_factor,
    maximize_sharpe,
    maximize_total_return,
    maximize_win_rate,
    minimize_max_drawdown,
)
from quant_trading.strategies.examples import MovingAverageCrossover, RSIStrategy


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
                    fetched_at=datetime.now(),
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
    def _request_key(symbols: list, start: datetime | None, end: datetime | None, interval: str) -> str:
        symbols_str = ",".join(sorted(symbols))
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        return f"{symbols_str}|{start_str}|{end_str}|{interval}"


def create_test_data(symbol: str, days: int = 100) -> pd.DataFrame:
    """Create deterministic test price data."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    returns = np.random.normal(0.0005, 0.02, days)
    prices = 100 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
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
    metrics.num_trades = 3

    from quant_trading.backtest.engine import BacktestResult

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime.now() - timedelta(days=10),
        end_date=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
            start=datetime.now() - timedelta(days=50),
            end=datetime.now(),
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
        start=datetime.now() - timedelta(days=90),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_windows=2,
        train_size=0.5,
        anchored=True,
        verbose=False,
    )

    start_dt = datetime.now() - timedelta(days=90)
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
            start=datetime.now() - timedelta(days=50),
            end=datetime.now(),
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
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
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
