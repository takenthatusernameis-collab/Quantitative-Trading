"""Tests for the optimization module."""

from concurrent.futures import _base
from concurrent.futures.process import BrokenProcessPool, ProcessPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quant_trading.data.providers import DataManager
from quant_trading.optimization import (
    BayesianOptimizer,
    GridSearch,
    OptimizationResult,
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
from quant_trading.strategies.base import Signal, Strategy
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
    def _request_key(
        symbols: list, start: datetime | None, end: datetime | None, interval: str
    ) -> str:
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
    start = datetime.now()
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=data_manager,
        verbose=False,
    )

    _params, score, result = optimizer._evaluate_params({"fast_period": 5, "slow_period": 20})
    assert score == float("-inf")
    assert result is None


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=10),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
        verbose=False,
    )
    assert optimizer.n_combinations == 4


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=10),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=10),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )

    windows = [
        WalkForwardWindow(
            train_start=datetime.now() - timedelta(days=5),
            train_end=datetime.now() - timedelta(days=3),
            test_start=datetime.now() - timedelta(days=3),
            test_end=datetime.now(),
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
        start=datetime.now() - timedelta(days=10),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )

    # Create test result with single-point equity curve (no returns)
    metrics = BacktestMetrics()
    test_result = BacktestResult(
        equity_curve=pd.Series([100000.0], index=[datetime.now()]),
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=datetime.now() - timedelta(days=1),
        end_date=datetime.now(),
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )

    windows = [
        WalkForwardWindow(
            train_start=datetime.now() - timedelta(days=5),
            train_end=datetime.now() - timedelta(days=3),
            test_start=datetime.now() - timedelta(days=3),
            test_end=datetime.now(),
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
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=60),
        end=datetime.now(),
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
            start=datetime.now() - timedelta(days=10),
            end=datetime.now(),
            initial_capital=100000.0,
            data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
        )


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_initial_points=2,
        n_calls=3,
        random_state=42,
        verbose=False,
    )
    assert optimizer.objective is maximize_sharpe


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=90),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=10),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=DataManager([MockDataProvider({"AAPL": create_test_data("AAPL", 20)})]),
    )

    space = optimizer._create_skopt_space()
    assert space == []


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
    from quant_trading.config.settings import Config

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
        config=Config(),
        verbose=False,
        n_jobs=2,
    )

    result = optimizer.run()
    assert result.best_params is not None
    assert len(result.all_results) == 4


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
    from quant_trading.config.settings import Config

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
        config=Config(),
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
        datetime.now() - timedelta(days=50),
        datetime.now(),
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


def test_evaluate_params_worker_grid_none_config():
    """Test grid_search._evaluate_params_worker with data_config=None (line 39 False branch)."""
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime.now() - timedelta(days=50),
        datetime.now(),
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
    from quant_trading.config.settings import Config
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    config = Config()
    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime.now() - timedelta(days=50),
        datetime.now(),
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
        datetime.now() - timedelta(days=50),
        datetime.now(),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


def test_evaluate_params_worker_grid_error():
    """Test grid_search._evaluate_params_worker propagates worker errors."""
    from quant_trading.optimization.grid_search import _evaluate_params_worker

    with pytest.raises(ValueError, match="boom"):
        _evaluate_params_worker(
            RaisingStrategy,
            {},
            maximize_sharpe,
            ["AAPL"],
            datetime.now() - timedelta(days=50),
            datetime.now(),
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
        datetime.now() - timedelta(days=50),
        datetime.now(),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert params == {"fast_period": 5, "slow_period": 20}
    assert result is not None


def test_evaluate_params_worker_random_none_config():
    """Test random_search._evaluate_params_worker with data_config=None (line 41 False branch)."""
    from quant_trading.optimization.random_search import _evaluate_params_worker

    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime.now() - timedelta(days=50),
        datetime.now(),
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
    from quant_trading.config.settings import Config
    from quant_trading.optimization.random_search import _evaluate_params_worker

    config = Config()
    _params, _score, result = _evaluate_params_worker(
        MovingAverageCrossover,
        {},
        maximize_sharpe,
        ["AAPL"],
        datetime.now() - timedelta(days=50),
        datetime.now(),
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
        datetime.now() - timedelta(days=50),
        datetime.now(),
        100000.0,
        0.001,
        0.0005,
        "1d",
        data_config,
        {"fast_period": 5, "slow_period": 20},
    )
    assert result is not None


def test_evaluate_params_worker_random_error():
    """Test random_search._evaluate_params_worker propagates worker errors."""
    from quant_trading.optimization.random_search import _evaluate_params_worker

    with pytest.raises(ValueError, match="boom"):
        _evaluate_params_worker(
            RaisingStrategy,
            {},
            maximize_sharpe,
            ["AAPL"],
            datetime.now() - timedelta(days=50),
            datetime.now(),
            100000.0,
            0.001,
            0.0005,
            "1d",
            None,
            {"fast_period": 5, "slow_period": 20},
        )


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
        initial_capital=100000.0,
        data_manager=data_manager,
        n_jobs=2,
        **kwargs,
    )


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
        start=datetime.now() - timedelta(days=50),
        end=datetime.now(),
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
